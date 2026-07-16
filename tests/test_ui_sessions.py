"""Tests for local session store / HITL decisions used by the demo UI."""

from supportrouter.graph import run_agent
from supportrouter.sessions import clear_sessions, decide_hitl, list_sessions, save_session
from supportrouter.ui import (
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
    detail, rows, cleared = supervisor_decide(result["session_id"], "reject", "no")
    assert "rejected" in detail
    assert rows == []
    assert cleared == ""


def test_session_id_from_row_value():
    sid = "abc-123-session"

    class _Evt:
        row_value = [sid, "pending_approval", "refund_request"]
        index = (0, 1)
        value = "pending_approval"

    assert session_id_from_select_event(_Evt()) == sid


def test_on_queue_select_fills_session_and_detail():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    sid = result["session_id"]

    class _Evt:
        row_value = [sid, "pending_approval", "refund_request", "159.99", "over", "msg"]
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
