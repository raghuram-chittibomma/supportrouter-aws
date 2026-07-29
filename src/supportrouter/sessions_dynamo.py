"""DynamoDB session and approval repositories (ADR-010 / #16).

Selected when ``SESSIONS_TABLE_NAME`` and ``APPROVALS_TABLE_NAME`` are set.
Uses conditional writes and a transaction for decide so concurrent supervisors
cannot double-apply conflicting terminal decisions.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from supportrouter.observability import emit_hitl_decision
from supportrouter.schemas import ApprovalRequest

SESSIONS_ENV = "SESSIONS_TABLE_NAME"
APPROVALS_ENV = "APPROVALS_TABLE_NAME"


def _is_conditional_failure(exc: Exception) -> bool:
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code")
        return code in {
            "ConditionalCheckFailedException",
            "TransactionCanceledException",
        }
    name = type(exc).__name__
    return name in {
        "ConditionalCheckFailedException",
        "TransactionCanceledException",
    }


def dynamo_enabled() -> bool:
    return bool(os.environ.get(SESSIONS_ENV) and os.environ.get(APPROVALS_ENV))


def _client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    import boto3

    return boto3.client("dynamodb")


def _sessions_table() -> str:
    name = os.environ.get(SESSIONS_ENV)
    if not name:
        raise RuntimeError(f"{SESSIONS_ENV} is required for DynamoDB sessions")
    return name


def _approvals_table() -> str:
    name = os.environ.get(APPROVALS_ENV)
    if not name:
        raise RuntimeError(f"{APPROVALS_ENV} is required for DynamoDB approvals")
    return name


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_attr(value: Any) -> dict[str, Any]:
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, (int, float, Decimal)):
        return {"N": str(value)}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, dict):
        return {"M": {k: _to_attr(v) for k, v in value.items()}}
    if isinstance(value, list):
        return {"L": [_to_attr(v) for v in value]}
    raise TypeError(f"unsupported DynamoDB value type: {type(value)!r}")


def _from_attr(attr: dict[str, Any]) -> Any:
    if "NULL" in attr:
        return None
    if "BOOL" in attr:
        return attr["BOOL"]
    if "N" in attr:
        number = Decimal(attr["N"])
        if number % 1 == 0:
            return int(number)
        return float(number)
    if "S" in attr:
        return attr["S"]
    if "M" in attr:
        return {k: _from_attr(v) for k, v in attr["M"].items()}
    if "L" in attr:
        return [_from_attr(v) for v in attr["L"]]
    raise TypeError(f"unsupported DynamoDB attribute: {attr!r}")


def _item_from_record(record: dict[str, Any], *, key_name: str) -> dict[str, Any]:
    """Store queryable keys as attributes; full payload as JSON for fidelity."""
    key = str(record[key_name])
    item = {
        key_name: {"S": key},
        "status": {"S": str(record.get("status") or "")},
        "payload": {"S": json.dumps(record, separators=(",", ":"))},
    }
    if "version" in record:
        item["version"] = {"N": str(int(record["version"]))}
    if record.get("session_id") and key_name != "session_id":
        item["session_id"] = {"S": str(record["session_id"])}
    if record.get("approval_id") and key_name != "approval_id":
        item["approval_id"] = {"S": str(record["approval_id"])}
    return item


def _record_from_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    payload = item.get("payload", {}).get("S")
    if not payload:
        return None
    record = json.loads(payload)
    return record if isinstance(record, dict) else None


def _refund_order_id(record: dict[str, Any]) -> str:
    for call in record.get("tool_calls") or []:
        if call.get("name") != "issue_refund":
            continue
        result = call.get("result") or {}
        args = call.get("args") or {}
        return str(result.get("order_id") or args.get("order_id") or "")
    return ""


def _new_approval_request(record: dict[str, Any]) -> ApprovalRequest:
    session_id = str(record["session_id"])
    order_id = _refund_order_id(record)
    amount = record.get("refund_amount_usd")
    if not order_id or amount is None:
        raise ValueError("pending refund approval requires order_id and amount")
    now = _utc_now()
    return {
        "approval_id": f"approval-{session_id}",
        "session_id": session_id,
        "order_id": order_id,
        "amount_usd": float(amount),
        "status": "pending",
        "reason": str(record.get("hitl_reason") or ""),
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "decided_by": None,
        "decision_note": "",
        "version": 1,
        "execution_status": "not_executed",
    }


def get_session(session_id: str, *, client: Any | None = None) -> dict[str, Any] | None:
    response = _client(client).get_item(
        TableName=_sessions_table(),
        Key={"session_id": {"S": session_id}},
        ConsistentRead=True,
    )
    return _record_from_item(response.get("Item"))


def get_approval_request(
    approval_id: str, *, client: Any | None = None
) -> ApprovalRequest | None:
    response = _client(client).get_item(
        TableName=_approvals_table(),
        Key={"approval_id": {"S": approval_id}},
        ConsistentRead=True,
    )
    record = _record_from_item(response.get("Item"))
    return record  # type: ignore[return-value]


def list_sessions(
    *, statuses: set[str] | None = None, client: Any | None = None
) -> list[dict[str, Any]]:
    ddb = _client(client)
    kwargs: dict[str, Any] = {"TableName": _sessions_table()}
    if statuses:
        # Scan is acceptable for the dormancy-safe demo volume.
        values = {f":s{i}": {"S": status} for i, status in enumerate(sorted(statuses))}
        kwargs["FilterExpression"] = " OR ".join(f"#st = {name}" for name in values)
        kwargs["ExpressionAttributeNames"] = {"#st": "status"}
        kwargs["ExpressionAttributeValues"] = values
    items: list[dict[str, Any]] = []
    while True:
        response = ddb.scan(**kwargs)
        for item in response.get("Items") or []:
            record = _record_from_item(item)
            if record is not None:
                items.append(record)
        token = response.get("LastEvaluatedKey")
        if not token:
            break
        kwargs["ExclusiveStartKey"] = token
    items.sort(key=lambda s: s.get("session_id") or "")
    return items


def list_approval_requests(
    *, statuses: set[str] | None = None, client: Any | None = None
) -> list[ApprovalRequest]:
    ddb = _client(client)
    kwargs: dict[str, Any] = {"TableName": _approvals_table()}
    if statuses:
        values = {f":s{i}": {"S": status} for i, status in enumerate(sorted(statuses))}
        kwargs["FilterExpression"] = " OR ".join(f"#st = {name}" for name in values)
        kwargs["ExpressionAttributeNames"] = {"#st": "status"}
        kwargs["ExpressionAttributeValues"] = values
    items: list[ApprovalRequest] = []
    while True:
        response = ddb.scan(**kwargs)
        for item in response.get("Items") or []:
            record = _record_from_item(item)
            if record is not None:
                items.append(record)  # type: ignore[arg-type]
        token = response.get("LastEvaluatedKey")
        if not token:
            break
        kwargs["ExclusiveStartKey"] = token
    items.sort(key=lambda approval: approval["approval_id"])
    return items


def save_session(result: dict[str, Any], *, client: Any | None = None) -> dict[str, Any]:
    session_id = result.get("session_id")
    if not session_id:
        raise ValueError("session_id required")
    ddb = _client(client)
    record = deepcopy(result)
    if not record.get("correlation_id"):
        record["correlation_id"] = record["session_id"]

    approval_id = f"approval-{session_id}"
    existing = get_session(session_id, client=ddb)
    existing_approval = get_approval_request(approval_id, client=ddb)
    if existing is not None and existing_approval is not None:
        return deepcopy(existing)

    if (
        record.get("status") == "pending_approval"
        and record.get("task_type") == "refund_request"
    ):
        if existing_approval is None:
            approval = _new_approval_request(record)
            try:
                ddb.put_item(
                    TableName=_approvals_table(),
                    Item=_item_from_record(approval, key_name="approval_id"),
                    ConditionExpression="attribute_not_exists(approval_id)",
                )
            except Exception as exc:  # noqa: BLE001 — backend-specific conditional errors
                if not _is_conditional_failure(exc):
                    raise
                approval = get_approval_request(approval_id, client=ddb)
                if approval is None:
                    raise
        else:
            approval = existing_approval
        record["approval_id"] = approval_id
        record["approval_status"] = approval["status"]

    ddb.put_item(
        TableName=_sessions_table(),
        Item=_item_from_record(record, key_name="session_id"),
    )
    return deepcopy(record)


def decide_hitl(
    session_id: str,
    decision: str,
    note: str = "",
    *,
    decided_by: str = "local-supervisor",
    client: Any | None = None,
) -> dict[str, Any]:
    decision_norm = (decision or "").strip().lower()
    if decision_norm not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    ddb = _client(client)
    record = get_session(session_id, client=ddb)
    if record is None:
        raise KeyError(f"Unknown session_id: {session_id}")
    approval_id = record.get("approval_id")
    approval = get_approval_request(str(approval_id), client=ddb) if approval_id else None
    if approval is None:
        raise ValueError(
            f"Session {session_id} is not a pending refund approval "
            f"(status={record.get('status')})"
        )

    desired_status = "approved" if decision_norm == "approve" else "rejected"
    if approval["status"] == desired_status:
        return deepcopy(record)
    if approval["status"] != "pending":
        raise ValueError(
            f"Approval {approval_id} is already {approval['status']}; "
            f"cannot {decision_norm}"
        )
    if record.get("status") != "pending_approval":
        raise ValueError(
            f"Session {session_id} is not awaiting approval "
            f"(status={record.get('status')})"
        )

    now = _utc_now()
    updated_approval = deepcopy(approval)
    updated_approval["status"] = desired_status
    updated_approval["updated_at"] = now
    updated_approval["decided_at"] = now
    updated_approval["decided_by"] = decided_by
    updated_approval["decision_note"] = note
    updated_approval["version"] = int(approval["version"]) + 1

    updated_session = deepcopy(record)
    updated_session["approval_status"] = desired_status
    updated_session["hitl_decision"] = decision_norm
    updated_session["hitl_note"] = note
    if decision_norm == "approve":
        updated_session["status"] = "resolved"
        updated_session["answer"] = (
            f"{record.get('answer') or ''}\n\n"
            "_(Supervisor approved the synthetic request. "
            "No refund was executed in this demo."
            f"{f' Note: {note}' if note else ''})_"
        ).strip()
    else:
        updated_session["status"] = "rejected"
        updated_session["answer"] = (
            f"{record.get('answer') or ''}\n\n"
            "_(Supervisor rejected the synthetic request. "
            "No refund was executed in this demo."
            f"{f' Note: {note}' if note else ''})_"
        ).strip()

    try:
        ddb.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": _approvals_table(),
                        "Item": _item_from_record(
                            updated_approval, key_name="approval_id"
                        ),
                        "ConditionExpression": "#st = :pending",
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": {":pending": {"S": "pending"}},
                    }
                },
                {
                    "Put": {
                        "TableName": _sessions_table(),
                        "Item": _item_from_record(
                            updated_session, key_name="session_id"
                        ),
                        "ConditionExpression": "#st = :pending",
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": {
                            ":pending": {"S": "pending_approval"}
                        },
                    }
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001 — backend-specific transaction errors
        if not _is_conditional_failure(exc):
            raise
        # Concurrent decide — re-read and treat matching terminal as idempotent.
        current_approval = get_approval_request(str(approval_id), client=ddb)
        current_session = get_session(session_id, client=ddb)
        if (
            current_approval is not None
            and current_session is not None
            and current_approval["status"] == desired_status
        ):
            return deepcopy(current_session)
        raise ValueError(
            f"Approval {approval_id} could not be transitioned to {desired_status}"
        ) from None

    emit_hitl_decision(
        session_id=session_id,
        correlation_id=str(updated_session.get("correlation_id") or session_id),
        decision=decision_norm,
        status=str(updated_session["status"]),
        approval_id=str(approval_id) if approval_id else None,
        plane=str(updated_session.get("plane") or "runtime"),
    )
    return deepcopy(updated_session)


def clear_sessions(*, client: Any | None = None) -> None:
    """Delete all session/approval items (test helper only)."""
    ddb = _client(client)
    for table, key_name in (
        (_sessions_table(), "session_id"),
        (_approvals_table(), "approval_id"),
    ):
        kwargs: dict[str, Any] = {
            "TableName": table,
            "ProjectionExpression": key_name,
        }
        while True:
            response = ddb.scan(**kwargs)
            for item in response.get("Items") or []:
                ddb.delete_item(TableName=table, Key={key_name: item[key_name]})
            token = response.get("LastEvaluatedKey")
            if not token:
                break
            kwargs["ExclusiveStartKey"] = token
