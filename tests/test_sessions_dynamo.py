"""Unit tests for DynamoDB HITL session/approval persistence (#16)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from supportrouter.graph import run_agent
from supportrouter.sessions_dynamo import (
    clear_sessions,
    decide_hitl,
    get_approval_request,
    get_session,
    list_sessions,
    save_session,
)


class FakeDynamoDB:
    """Minimal DynamoDB client for conditional Put / Scan / TransactWrite."""

    class ConditionalCheckFailedException(Exception):
        pass

    class TransactionCanceledException(Exception):
        pass

    class exceptions:  # noqa: N801 — mirrors boto3 client.exceptions
        ConditionalCheckFailedException = None  # set after class body
        TransactionCanceledException = None

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = {}
        type(self).exceptions.ConditionalCheckFailedException = (
            self.ConditionalCheckFailedException
        )
        type(self).exceptions.TransactionCanceledException = (
            self.TransactionCanceledException
        )

    def _table(self, name: str) -> dict[str, dict[str, Any]]:
        return self.tables.setdefault(name, {})

    def _key_value(self, key: dict[str, Any]) -> str:
        ((_, attr),) = key.items()
        return attr["S"]

    def get_item(self, *, TableName: str, Key: dict, ConsistentRead: bool = False):
        del ConsistentRead
        item = self._table(TableName).get(self._key_value(Key))
        return {"Item": deepcopy(item)} if item is not None else {}

    def put_item(
        self,
        *,
        TableName: str,
        Item: dict,
        ConditionExpression: str | None = None,
        ExpressionAttributeNames: dict | None = None,
        ExpressionAttributeValues: dict | None = None,
    ):
        table = self._table(TableName)
        key_name = next(iter(Item))
        key = Item[key_name]["S"]
        existing = table.get(key)
        if ConditionExpression == "attribute_not_exists(approval_id)" and existing:
            raise self.ConditionalCheckFailedException()
        if ConditionExpression and "#st = :pending" in ConditionExpression:
            names = ExpressionAttributeNames or {}
            values = ExpressionAttributeValues or {}
            status_attr = names.get("#st", "status")
            expected = values[":pending"]["S"]
            if existing is None or existing.get(status_attr, {}).get("S") != expected:
                raise self.ConditionalCheckFailedException()
        table[key] = deepcopy(Item)
        return {}

    def delete_item(self, *, TableName: str, Key: dict):
        self._table(TableName).pop(self._key_value(Key), None)
        return {}

    def scan(self, **kwargs):
        table = self._table(kwargs["TableName"])
        items = list(table.values())
        filter_expr = kwargs.get("FilterExpression")
        if filter_expr:
            names = kwargs.get("ExpressionAttributeNames") or {}
            values = kwargs.get("ExpressionAttributeValues") or {}
            status_attr = names.get("#st", "status")
            allowed = {v["S"] for v in values.values()}
            items = [
                item
                for item in items
                if item.get(status_attr, {}).get("S") in allowed
            ]
        projection = kwargs.get("ProjectionExpression")
        if projection:
            projected = []
            for item in items:
                projected.append({projection: item[projection]})
            items = projected
        return {"Items": deepcopy(items)}

    def transact_write_items(self, *, TransactItems: list[dict]):
        # Validate all conditions first, then apply (atomic-enough for unit tests).
        staged: list[tuple[str, dict]] = []
        try:
            for entry in TransactItems:
                put = entry["Put"]
                table = self._table(put["TableName"])
                item = put["Item"]
                key_name = next(iter(item))
                key = item[key_name]["S"]
                existing = table.get(key)
                condition = put.get("ConditionExpression")
                if condition and "#st = :pending" in condition:
                    names = put.get("ExpressionAttributeNames") or {}
                    values = put.get("ExpressionAttributeValues") or {}
                    status_attr = names.get("#st", "status")
                    expected = values[":pending"]["S"]
                    if (
                        existing is None
                        or existing.get(status_attr, {}).get("S") != expected
                    ):
                        raise self.TransactionCanceledException()
                staged.append((put["TableName"], item))
        except self.TransactionCanceledException:
            raise
        for table_name, item in staged:
            key_name = next(iter(item))
            self._table(table_name)[item[key_name]["S"]] = deepcopy(item)
        return {}


@pytest.fixture
def dynamo_env(monkeypatch):
    monkeypatch.setenv("SESSIONS_TABLE_NAME", "supportrouter-sessions")
    monkeypatch.setenv("APPROVALS_TABLE_NAME", "supportrouter-approvalrequests")
    client = FakeDynamoDB()
    return client


def test_dynamo_save_creates_pending_approval(dynamo_env):
    client = dynamo_env
    result = save_session(
        run_agent("I want a refund for order VE-1003"),
        client=client,
    )

    assert result["status"] == "pending_approval"
    assert result["approval_id"] == f"approval-{result['session_id']}"
    approval = get_approval_request(result["approval_id"], client=client)
    assert approval is not None
    assert approval["status"] == "pending"
    assert approval["amount_usd"] == 159.99
    assert approval["execution_status"] == "not_executed"
    assert get_session(result["session_id"], client=client)["approval_status"] == "pending"


def test_dynamo_decide_approve_is_transactional_and_idempotent(dynamo_env):
    client = dynamo_env
    result = save_session(
        run_agent("I want a refund for order VE-1003"),
        client=client,
    )

    updated = decide_hitl(
        result["session_id"],
        "approve",
        note="ok",
        decided_by="unit-test",
        client=client,
    )
    assert updated["status"] == "resolved"
    assert updated["approval_status"] == "approved"
    assert "No refund was executed" in updated["answer"]

    approval = get_approval_request(result["approval_id"], client=client)
    assert approval is not None
    assert approval["status"] == "approved"
    assert approval["version"] == 2
    assert approval["execution_status"] == "not_executed"

    again = decide_hitl(
        result["session_id"], "approve", client=client, decided_by="unit-test"
    )
    assert again["status"] == "resolved"
    assert list_sessions(statuses={"pending_approval"}, client=client) == []


def test_dynamo_conflicting_decision_rejected(dynamo_env):
    client = dynamo_env
    result = save_session(
        run_agent("I want a refund for order VE-1003"),
        client=client,
    )
    decide_hitl(result["session_id"], "approve", client=client)

    with pytest.raises(ValueError, match="already approved"):
        decide_hitl(result["session_id"], "reject", client=client)


def test_dynamo_clear_sessions(dynamo_env):
    client = dynamo_env
    save_session(run_agent("I want a refund for order VE-1003"), client=client)
    clear_sessions(client=client)
    assert list_sessions(client=client) == []
