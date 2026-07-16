"""In-memory session store for local demo UI / HITL queue."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any

_LOCK = Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}


def save_session(result: dict[str, Any]) -> dict[str, Any]:
    """Persist a run_agent result; return the stored copy."""
    session_id = result.get("session_id")
    if not session_id:
        raise ValueError("session_id required")
    record = deepcopy(result)
    with _LOCK:
        _SESSIONS[session_id] = record
    return deepcopy(record)


def get_session(session_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = _SESSIONS.get(session_id)
        return deepcopy(record) if record else None


def list_sessions(*, statuses: set[str] | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        values = list(_SESSIONS.values())
    if statuses is not None:
        values = [s for s in values if s.get("status") in statuses]
    values.sort(key=lambda s: s.get("session_id") or "")
    return [deepcopy(s) for s in values]


def decide_hitl(session_id: str, decision: str, note: str = "") -> dict[str, Any]:
    """Approve or reject a pending_approval / escalated session (local stub)."""
    decision_norm = (decision or "").strip().lower()
    if decision_norm not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    with _LOCK:
        record = _SESSIONS.get(session_id)
        if record is None:
            raise KeyError(f"Unknown session_id: {session_id}")
        status = record.get("status")
        if status not in {"pending_approval", "escalated"}:
            raise ValueError(f"Session {session_id} is not awaiting HITL (status={status})")

        if decision_norm == "approve":
            record["status"] = "resolved"
            record["hitl_decision"] = "approve"
            record["answer"] = (
                f"{record.get('answer') or ''}\n\n"
                f"_(Supervisor approved. {note or 'Proceeding with action (synthetic).'})_"
            ).strip()
        else:
            record["status"] = "rejected"
            record["hitl_decision"] = "reject"
            record["answer"] = (
                f"{record.get('answer') or ''}\n\n"
                f"_(Supervisor rejected. {note or 'No further automated action.'})_"
            ).strip()
        record["hitl_note"] = note
        return deepcopy(record)


def clear_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()
