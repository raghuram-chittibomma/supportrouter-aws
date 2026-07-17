"""In-memory session and approval repositories for the local demo."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from supportrouter.schemas import ApprovalRequest

_LOCK = Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}
_APPROVALS: dict[str, ApprovalRequest] = {}


def save_session(result: dict[str, Any]) -> dict[str, Any]:
    """Persist a run result and create a local refund approval when required."""
    session_id = result.get("session_id")
    if not session_id:
        raise ValueError("session_id required")
    record = deepcopy(result)
    with _LOCK:
        existing = _SESSIONS.get(session_id)
        approval_id = f"approval-{session_id}"
        existing_approval = _APPROVALS.get(approval_id)
        if existing is not None and existing_approval is not None:
            # Approval identity fields are immutable. Re-saves are idempotent
            # and cannot desynchronize or revert the session/approval pair.
            return deepcopy(existing)

        if (
            record.get("status") == "pending_approval"
            and record.get("task_type") == "refund_request"
        ):
            if existing_approval is None:
                existing_approval = _new_approval_request(record)
                _APPROVALS[approval_id] = existing_approval
            record["approval_id"] = approval_id
            record["approval_status"] = existing_approval["status"]
        _SESSIONS[session_id] = record
    return deepcopy(record)


def get_session(session_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = _SESSIONS.get(session_id)
        return deepcopy(record) if record else None


def list_sessions(*, statuses: set[str] | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        values = deepcopy(list(_SESSIONS.values()))
    if statuses is not None:
        values = [s for s in values if s.get("status") in statuses]
    values.sort(key=lambda s: s.get("session_id") or "")
    return values


def get_approval_request(approval_id: str) -> ApprovalRequest | None:
    with _LOCK:
        record = _APPROVALS.get(approval_id)
        return deepcopy(record) if record else None


def list_approval_requests(
    *, statuses: set[str] | None = None
) -> list[ApprovalRequest]:
    with _LOCK:
        values = deepcopy(list(_APPROVALS.values()))
    if statuses is not None:
        values = [approval for approval in values if approval["status"] in statuses]
    values.sort(key=lambda approval: approval["approval_id"])
    return values


def decide_hitl(
    session_id: str,
    decision: str,
    note: str = "",
    *,
    decided_by: str = "local-supervisor",
) -> dict[str, Any]:
    """Transition a pending refund approval; retries are idempotent."""
    decision_norm = (decision or "").strip().lower()
    if decision_norm not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    with _LOCK:
        record = _SESSIONS.get(session_id)
        if record is None:
            raise KeyError(f"Unknown session_id: {session_id}")
        approval_id = record.get("approval_id")
        approval = _APPROVALS.get(approval_id) if approval_id else None
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
        approval["status"] = desired_status
        approval["updated_at"] = now
        approval["decided_at"] = now
        approval["decided_by"] = decided_by
        approval["decision_note"] = note
        approval["version"] += 1
        record["approval_status"] = desired_status
        record["hitl_decision"] = decision_norm
        record["hitl_note"] = note

        if decision_norm == "approve":
            record["status"] = "resolved"
            record["answer"] = (
                f"{record.get('answer') or ''}\n\n"
                "_(Supervisor approved the synthetic request. "
                "No refund was executed in this local demo."
                f"{f' Note: {note}' if note else ''})_"
            ).strip()
        else:
            record["status"] = "rejected"
            record["answer"] = (
                f"{record.get('answer') or ''}\n\n"
                "_(Supervisor rejected the synthetic request. "
                "No refund was executed in this local demo."
                f"{f' Note: {note}' if note else ''})_"
            ).strip()
        return deepcopy(record)


def clear_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()
        _APPROVALS.clear()


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


def _refund_order_id(record: dict[str, Any]) -> str:
    for call in record.get("tool_calls") or []:
        if call.get("name") != "issue_refund":
            continue
        result = call.get("result") or {}
        args = call.get("args") or {}
        return str(result.get("order_id") or args.get("order_id") or "")
    return ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
