"""Local unit tests for the three synthetic Lambda tool handlers."""

from __future__ import annotations

import json
import importlib
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from supportrouter import tools_local
from tools import _shared, get_order_status, initiate_return, issue_refund

ROOT = Path(__file__).resolve().parents[1]


class ConditionalWriteFailed(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    def __init__(self, key_name: str, items: list[dict] | None = None):
        self.key_name = key_name
        self.items = {
            item[key_name]: deepcopy(item)
            for item in (items or [])
        }
        self.get_calls: list[dict] = []
        self.put_calls: list[dict] = []

    def get_item(self, *, Key, **kwargs):
        self.get_calls.append({"Key": deepcopy(Key), **deepcopy(kwargs)})
        item = self.items.get(Key[self.key_name])
        return {"Item": deepcopy(item)} if item is not None else {}

    def put_item(self, *, Item, ConditionExpression, ExpressionAttributeNames):
        assert ConditionExpression == "attribute_not_exists(#pk)"
        assert ExpressionAttributeNames == {"#pk": self.key_name}
        self.put_calls.append(deepcopy(Item))
        key = Item[self.key_name]
        if key in self.items:
            raise ConditionalWriteFailed()
        self.items[key] = deepcopy(Item)
        return {}


@pytest.fixture
def tables(monkeypatch):
    orders = FakeTable(
        "order_id",
        [
            {
                "order_id": "VE-1001",
                "status": "shipped",
                "tracking_number": "VETRACK-90821",
                "items": [
                    {
                        "sku": "VE-CC-4K",
                        "qty": Decimal("1"),
                        "line_total_usd": Decimal("99.99"),
                    }
                ],
                "refund_eligible": False,
                "refund_amount_usd": Decimal("0"),
            },
            {
                "order_id": "VE-1002",
                "status": "delivered",
                "tracking_number": "VETRACK-90855",
                "items": [],
                "refund_eligible": True,
                "refund_amount_usd": Decimal("89.99"),
            },
            {
                "order_id": "VE-1003",
                "status": "delivered",
                "tracking_number": "VETRACK-90901",
                "items": [],
                "refund_eligible": True,
                "refund_amount_usd": Decimal("159.99"),
            },
            {
                "order_id": "VE-1004",
                "status": "delivered",
                "tracking_number": "VETRACK-90902",
                "items": [],
                "refund_eligible": True,
                "refund_amount_usd": Decimal("100.00"),
            },
        ],
    )
    returns = FakeTable("return_id")
    refunds = FakeTable("refund_id")
    mapping = {
        "ORDERS_TABLE_NAME": orders,
        "RETURNS_TABLE_NAME": returns,
        "REFUNDS_TABLE_NAME": refunds,
    }
    monkeypatch.setattr(_shared, "table_from_env", mapping.__getitem__)
    monkeypatch.setattr(_shared, "utc_now", lambda: "2026-07-17T00:00:00+00:00")
    return mapping


@pytest.mark.parametrize(
    "event",
    [
        None,
        {},
        {"order_id": 1001},
        {"order_id": "1001"},
        {"order_id": "VE-1"},
    ],
)
def test_handlers_reject_invalid_order_id_without_table_access(event, monkeypatch):
    monkeypatch.setattr(
        _shared,
        "table_from_env",
        lambda name: pytest.fail(f"unexpected table access: {name}"),
    )

    for module in (get_order_status, initiate_return, issue_refund):
        assert module.handler(event, None) == {
            "ok": False,
            "error": (
                "event must be an object"
                if event is None
                else "order_id must match VE-####"
            ),
        }


def test_get_order_status_is_read_only_and_json_safe(tables):
    result = get_order_status.handler({"order_id": "ve-1001"}, None)

    assert result == {
        "ok": True,
        "order_id": "VE-1001",
        "status": "shipped",
        "tracking_number": "VETRACK-90821",
        "items": [{"sku": "VE-CC-4K", "qty": 1, "line_total_usd": 99.99}],
    }
    assert tables["RETURNS_TABLE_NAME"].put_calls == []
    assert tables["REFUNDS_TABLE_NAME"].put_calls == []
    order_read = tables["ORDERS_TABLE_NAME"].get_calls[0]
    assert order_read["ConsistentRead"] is True
    assert "shipping_address" not in order_read["ProjectionExpression"]
    assert "customer_id" not in order_read["ProjectionExpression"]
    assert "#items" in order_read["ProjectionExpression"]
    assert order_read["ExpressionAttributeNames"]["#items"] == "items"
    json.dumps(result)


def test_order_not_found_contract_is_shared(tables):
    expected = {"ok": False, "error": "Order VE-9999 not found"}
    for module in (get_order_status, initiate_return, issue_refund):
        assert module.handler({"order_id": "VE-9999"}, None) == expected


def test_initiate_return_is_idempotent_and_writes_only_returns(tables):
    first = initiate_return.handler({"order_id": "VE-1002"}, None)
    second = initiate_return.handler({"order_id": "VE-1002"}, None)

    assert first == {
        "ok": True,
        "order_id": "VE-1002",
        "rma_id": "RMA-VE-1002",
        "status": "initiated",
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": "Return initiated (synthetic). Ship unused item within 30 days.",
    }
    assert second == {**first, "idempotent_replay": True}
    assert len(tables["RETURNS_TABLE_NAME"].put_calls) == 2
    assert tables["RETURNS_TABLE_NAME"].get_calls[-1]["ConsistentRead"] is True
    assert tables["REFUNDS_TABLE_NAME"].put_calls == []


def test_refund_below_threshold_is_prepared_not_executed(tables):
    result = issue_refund.handler({"order_id": "VE-1002"}, None)

    assert result == {
        "ok": True,
        "order_id": "VE-1002",
        "refund_id": "REFUND-VE-1002",
        "amount_usd": 89.99,
        "requires_approval": False,
        "status": "prepared",
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": (
            "Refund of $89.99 prepared (synthetic); no payment was executed"
        ),
    }
    assert tables["RETURNS_TABLE_NAME"].put_calls == []


def test_refund_above_threshold_is_pending_and_idempotent(tables):
    first = issue_refund.handler({"order_id": "VE-1003"}, None)
    second = issue_refund.handler({"order_id": "VE-1003"}, None)

    assert first["amount_usd"] == 159.99
    assert first["requires_approval"] is True
    assert first["status"] == "pending_approval"
    assert first["execution_status"] == "not_executed"
    assert first["idempotent_replay"] is False
    assert first["message"] == (
        "Refund of $159.99 prepared (synthetic); requires supervisor "
        "approval; no payment was executed"
    )
    assert second == {**first, "idempotent_replay": True}
    assert tables["REFUNDS_TABLE_NAME"].get_calls[-1]["ConsistentRead"] is True


def test_refund_never_writes_ineligible_order(tables):
    result = issue_refund.handler({"order_id": "VE-1001"}, None)

    assert result == {
        "ok": False,
        "error": "Order VE-1001 is not refund-eligible",
    }
    assert tables["REFUNDS_TABLE_NAME"].put_calls == []


def test_refund_at_threshold_does_not_require_approval(tables):
    result = issue_refund.handler({"order_id": "VE-1004"}, None)

    assert result["amount_usd"] == 100.0
    assert result["requires_approval"] is False
    assert result["status"] == "prepared"
    assert result["execution_status"] == "not_executed"


@pytest.mark.parametrize(
    ("table_name", "key_name", "order_id", "item", "handler", "expected_error"),
    [
        (
            "RETURNS_TABLE_NAME",
            "return_id",
            "VE-1002",
            {
                "return_id": "RMA-VE-1002",
                "order_id": "VE-1002",
                "status": "initiated",
                "execution_status": "executed",
            },
            initiate_return.handler,
            "Stored return request failed integrity validation",
        ),
        (
            "REFUNDS_TABLE_NAME",
            "refund_id",
            "VE-1003",
            {
                "refund_id": "REFUND-VE-1003",
                "order_id": "VE-1003",
                "amount_usd": Decimal("159.99"),
                "requires_approval": True,
                "status": "pending_approval",
                "execution_status": "executed",
            },
            issue_refund.handler,
            "Stored refund request failed integrity validation",
        ),
    ],
)
def test_corrupt_idempotent_replay_fails_closed(
    tables,
    table_name,
    key_name,
    order_id,
    item,
    handler,
    expected_error,
):
    table = tables[table_name]
    assert table.key_name == key_name
    table.items[item[key_name]] = deepcopy(item)

    assert handler({"order_id": order_id}, None) == {
        "ok": False,
        "error": expected_error,
    }


def test_first_lambda_results_match_local_tool_contracts(tables):
    assert get_order_status.handler(
        {"order_id": "VE-1001"}, None
    ) == tools_local.get_order_status("VE-1001")
    assert initiate_return.handler(
        {"order_id": "VE-1002"}, None
    ) == tools_local.initiate_return("VE-1002")
    assert issue_refund.handler(
        {"order_id": "VE-1003"}, None
    ) == tools_local.issue_refund("VE-1003")


def test_handlers_import_from_lambda_asset_root(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    for module_name in ("get_order_status", "initiate_return", "issue_refund"):
        sys.modules.pop(module_name, None)
        module = importlib.import_module(module_name)
        assert callable(module.handler)
        assert module.handler({"order_id": "invalid"}, None) == {
            "ok": False,
            "error": "order_id must match VE-####",
        }
