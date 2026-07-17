"""Tests for local session store / HITL decisions used by the demo UI."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from supportrouter.graph import run_agent
from supportrouter.sessions import (
    clear_sessions,
    decide_hitl,
    get_approval_request,
    get_session,
    list_approval_requests,
    list_sessions,
    save_session,
)
from supportrouter.ui import (
    _escalation_rows,
    format_customer_reply,
    on_queue_select,
    refresh_queue,
    session_id_from_select_event,
    supervisor_decide,
)


def setup_function():
    clear_sessions()


def test_save_and_list_pending_refund():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    assert result["status"] == "pending_approval"
    assert result["approval_id"] == f"approval-{result['session_id']}"
    assert result["approval_status"] == "pending"
    queue = list_sessions(statuses={"pending_approval", "escalated"})
    assert len(queue) == 1
    assert queue[0]["session_id"] == result["session_id"]


def test_pending_refund_creates_explicit_approval_request():
    result = save_session(run_agent("I want a refund for order VE-1003"))

    approval = get_approval_request(result["approval_id"])

    assert approval is not None
    assert approval["session_id"] == result["session_id"]
    assert approval["order_id"] == "VE-1003"
    assert approval["amount_usd"] == 159.99
    assert approval["status"] == "pending"
    assert approval["reason"] == "Refund $159.99 exceeds $100 threshold"
    assert approval["decided_at"] is None
    assert approval["decided_by"] is None
    assert approval["decision_note"] == ""
    assert approval["version"] == 1
    assert approval["execution_status"] == "not_executed"
    assert approval["created_at"] == approval["updated_at"]


def test_supervisor_approve():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    updated = decide_hitl(result["session_id"], "approve", note="ok")
    assert updated["status"] == "resolved"
    assert updated["hitl_decision"] == "approve"
    assert updated["approval_status"] == "approved"
    assert "No refund was executed" in updated["answer"]
    approval = get_approval_request(result["approval_id"])
    assert approval is not None
    assert approval["status"] == "approved"
    assert approval["decision_note"] == "ok"
    assert approval["decided_by"] == "local-supervisor"
    assert approval["decided_at"] is not None
    assert approval["version"] == 2
    assert approval["execution_status"] == "not_executed"
    assert list_sessions(statuses={"pending_approval"}) == []


def test_format_customer_reply_includes_status():
    result = save_session(run_agent("Where is my order #VE-1001?"))
    text = format_customer_reply(result)
    assert "resolved" in text
    assert "amazon.nova-micro" in text


def test_supervisor_decide_ui_helper():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    detail, rows, cleared = supervisor_decide(result["session_id"], "reject", "no")
    assert "rejected" in detail
    assert rows == []
    assert cleared == ""


def test_session_id_from_row_value():
    sid = "abc-123-session"

    class _Evt:
        row_value = [
            sid,
            "pending_approval",
            "refund_request",
            "159.99",
            f"approval-{sid}",
            "pending",
            "over",
            "msg",
        ]
        index = (0, 1)
        value = "pending_approval"

    assert session_id_from_select_event(_Evt()) == sid


def test_on_queue_select_fills_session_and_detail():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    sid = result["session_id"]

    class _Evt:
        row_value = [
            sid,
            "pending_approval",
            "refund_request",
            "159.99",
            f"approval-{sid}",
            "pending",
            "over",
            "msg",
        ]
        index = (0, 0)
        value = sid

    filled_sid, detail = on_queue_select(_Evt())
    assert filled_sid == sid
    assert sid in detail
    assert "pending_approval" in detail


def test_refresh_queue_clears_stale_selection():
    save_session(run_agent("I want a refund for order VE-1003"))
    rows, sid, detail = refresh_queue()
    assert len(rows) == 1
    assert sid == ""
    assert "Click a queue row" in detail


def test_repeated_same_decision_is_idempotent():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    first = decide_hitl(result["session_id"], "approve", note="first")
    first_approval = get_approval_request(result["approval_id"])

    second = decide_hitl(result["session_id"], "approve", note="ignored retry")
    second_approval = get_approval_request(result["approval_id"])

    assert second == first
    assert second_approval == first_approval


def test_conflicting_terminal_decision_is_rejected():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    decide_hitl(result["session_id"], "approve")

    with pytest.raises(ValueError, match="already approved; cannot reject"):
        decide_hitl(result["session_id"], "reject")

    approval = get_approval_request(result["approval_id"])
    assert approval is not None
    assert approval["status"] == "approved"


def test_escalation_cannot_use_refund_approval_transition():
    result = save_session(run_agent("blorp zizzle qux"))
    assert result["status"] == "escalated"
    assert "approval_id" not in result

    with pytest.raises(ValueError, match="not a pending refund approval"):
        decide_hitl(result["session_id"], "approve")

    assert list_approval_requests() == []


def test_stale_pending_save_cannot_revert_terminal_decision():
    pending_result = run_agent("I want a refund for order VE-1003")
    stored = save_session(pending_result)
    decide_hitl(stored["session_id"], "reject", note="policy")

    stale_save = save_session(pending_result)

    assert stale_save["status"] == "rejected"
    assert stale_save["hitl_decision"] == "reject"
    assert get_session(stored["session_id"]) == stale_save
    approval = get_approval_request(stored["approval_id"])
    assert approval is not None
    assert approval["status"] == "rejected"


def test_pending_resave_cannot_desynchronize_approval_identity():
    pending_result = run_agent("I want a refund for order VE-1003")
    original = save_session(pending_result)
    original_approval = get_approval_request(original["approval_id"])
    changed = deepcopy(pending_result)
    changed["refund_amount_usd"] = 1.0
    changed["hitl_reason"] = "stale changed reason"
    changed["tool_calls"][0]["result"]["order_id"] = "VE-1002"

    repeated = save_session(changed)

    assert repeated == original
    assert get_approval_request(original["approval_id"]) == original_approval


def test_concurrent_conflicting_decisions_allow_one_terminal_transition():
    result = save_session(run_agent("I want a refund for order VE-1003"))

    def decide(decision):
        try:
            return decide_hitl(result["session_id"], decision)
        except ValueError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide, ["approve", "reject"]))

    successes = [outcome for outcome in outcomes if isinstance(outcome, dict)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, ValueError)]
    assert len(successes) == 1
    assert len(failures) == 1
    approval = get_approval_request(result["approval_id"])
    assert approval is not None
    assert approval["status"] in {"approved", "rejected"}
    assert approval["version"] == 2


def test_repository_returns_deep_copies():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    sessions = list_sessions()
    approvals = list_approval_requests()
    sessions[0]["status"] = "corrupted"
    approvals[0]["status"] = "rejected"

    assert get_session(result["session_id"])["status"] == "pending_approval"
    assert get_approval_request(result["approval_id"])["status"] == "pending"


def test_escalations_are_separate_from_actionable_approval_queue():
    result = save_session(run_agent("blorp zizzle qux"))
    rows, _, _ = refresh_queue()

    assert rows == []
    assert _escalation_rows() == [
        [
            result["session_id"],
            "unknown",
            "0.4",
            "Confidence 0.40 below 0.55",
            "",
        ]
    ]
