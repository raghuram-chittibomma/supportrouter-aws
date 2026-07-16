"""Tests for local session store / HITL decisions used by the demo UI."""

from supportrouter.graph import run_agent
from supportrouter.sessions import clear_sessions, decide_hitl, list_sessions, save_session
from supportrouter.ui import format_customer_reply, refresh_queue, supervisor_decide


def setup_function():
    clear_sessions()


def test_save_and_list_pending_refund():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    assert result["status"] == "pending_approval"
    queue = list_sessions(statuses={"pending_approval", "escalated"})
    assert len(queue) == 1
    assert queue[0]["session_id"] == result["session_id"]


def test_supervisor_approve():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    updated = decide_hitl(result["session_id"], "approve", note="ok")
    assert updated["status"] == "resolved"
    assert updated["hitl_decision"] == "approve"
    assert list_sessions(statuses={"pending_approval"}) == []


def test_format_customer_reply_includes_status():
    result = save_session(run_agent("Where is my order #VE-1001?"))
    text = format_customer_reply(result)
    assert "resolved" in text
    assert "amazon.nova-micro" in text


def test_supervisor_decide_ui_helper():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    detail, rows = supervisor_decide(result["session_id"], "reject", "no")
    assert "rejected" in detail
    assert rows == []
    assert refresh_queue() == []
