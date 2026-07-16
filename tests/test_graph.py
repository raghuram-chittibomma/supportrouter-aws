"""Tests for LangGraph agent edges and outcomes."""

from supportrouter.graph import after_route, build_graph, run_agent
from supportrouter.state import AgentState


def test_after_route_branches():
    assert after_route({"session_id": "s", "message": "x", "task_type": "order_status"}) == "tools"
    assert after_route({"session_id": "s", "message": "x", "task_type": "faq_policy"}) == "retrieve"
    assert after_route({"session_id": "s", "message": "x", "task_type": "unknown"}) == "draft"


def test_order_status_resolves_with_tool():
    result = run_agent("Where is my order #VE-1001?")
    assert result["task_type"] == "order_status"
    assert result["model_id"] == "amazon.nova-micro"
    assert result["status"] == "resolved"
    assert result["tool_calls"][0]["name"] == "get_order_status"
    assert result["tool_calls"][0]["result"]["ok"] is True
    assert "shipped" in result["answer"].lower()
    assert "tools:get_order_status" in result["notes"]
    assert "hitl:resolved" in result["notes"]


def test_refund_above_threshold_pending_approval():
    # VE-1003 PowerDock Duo refund_amount_usd = 159.99
    result = run_agent("I want a refund for order VE-1003")
    assert result["task_type"] == "refund_request"
    assert result["status"] == "pending_approval"
    assert result["refund_amount_usd"] == 159.99
    assert result["hitl_reason"] is not None
    assert "100" in result["hitl_reason"]


def test_refund_below_threshold_resolves():
    # VE-1002 BoomBar 300 refund_amount_usd = 89.99
    result = run_agent("Please refund order VE-1002")
    assert result["task_type"] == "refund_request"
    assert result["status"] == "resolved"
    assert result["refund_amount_usd"] == 89.99


def test_return_request_initiates_rma():
    result = run_agent("I need to return order VE-1002")
    assert result["task_type"] == "return_request"
    assert result["tool_calls"][0]["name"] == "initiate_return"
    assert result["tool_calls"][0]["result"]["ok"] is True
    assert result["status"] == "resolved"


def test_product_question_uses_retrieve():
    result = run_agent("Will this dock work with my laptop? PowerDock Duo compatibility")
    assert result["task_type"] == "product_question"
    assert result["status"] == "resolved"
    assert len(result["citations"]) >= 1
    assert result["citations"][0]["doc_id"] == "faq-powerdock-001"
    assert "retrieve:" in "".join(result["notes"])


def test_unknown_escalates_on_low_confidence():
    result = run_agent("asdf qwerty zxcv")
    assert result["task_type"] == "unknown"
    assert result["status"] == "escalated"
    assert result["confidence"] < 0.55


def test_graph_compiles():
    app = build_graph()
    assert app is not None


def test_empty_message_rejected():
    result = run_agent("   ")
    assert result["status"] == "rejected"
    assert result["confidence"] == 0.0
