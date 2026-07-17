"""LangGraph runtime agent for SupportRouter (local stubs; no Bedrock yet)."""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from supportrouter.classifier import classify
from supportrouter.decision import hitl_decision, score_confidence
from supportrouter.observability import (
    emit_conversation_end,
    emit_conversation_start,
    instrument_node,
    new_correlation_id,
)
from supportrouter.retrieve import retrieve
from supportrouter.router import route
from supportrouter.state import AgentState
from supportrouter.tools_local import (
    extract_order_id,
    get_order_status,
    initiate_return,
    issue_refund,
)


def _notes(state: AgentState) -> list[str]:
    return list(state.get("notes") or [])


def validate_node(state: AgentState) -> dict[str, Any]:
    message = (state.get("message") or "").strip()
    if not message:
        return {
            "error": "Empty message",
            "status": "rejected",
            "answer": "Please provide a support question.",
            "confidence": 0.0,
            "notes": _notes(state) + ["validate:rejected_empty"],
        }
    return {
        "session_id": state.get("session_id") or str(uuid.uuid4()),
        "message": message,
        "citations": [],
        "tool_calls": [],
        "notes": _notes(state) + ["validate:ok"],
        "error": None,
        "status": "open",
    }


def classify_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    result = classify(state["message"])
    return {
        "task_type": result.task_type,
        "classifier_confidence": result.confidence,
        "classifier_rationale": result.rationale,
        "notes": _notes(state) + [f"classify:{result.task_type}"],
    }


def route_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    task_type = state.get("task_type") or "unknown"
    decision = route(task_type)
    return {
        "model_id": decision.model_id,
        "routing_table_version": decision.routing_table_version,
        "notes": _notes(state) + [f"route:{decision.model_id}"],
    }


def retrieve_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    task_type = state.get("task_type") or "unknown"
    citations = retrieve(state["message"], task_type)
    return {
        "citations": citations,
        "notes": _notes(state) + [f"retrieve:{len(citations)}"],
    }


def tools_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    task_type = state.get("task_type") or "unknown"
    order_id = extract_order_id(state["message"])
    calls: list[dict[str, Any]] = []
    refund_amount: float | None = None

    if order_id is None:
        calls.append(
            {
                "name": "missing_order_id",
                "args": {},
                "result": {"ok": False, "error": "No order ID (VE-####) found in message"},
            }
        )
    elif task_type == "order_status":
        result = get_order_status(order_id)
        calls.append({"name": "get_order_status", "args": {"order_id": order_id}, "result": result})
    elif task_type == "return_request":
        result = initiate_return(order_id)
        calls.append({"name": "initiate_return", "args": {"order_id": order_id}, "result": result})
    elif task_type == "refund_request":
        result = issue_refund(order_id)
        calls.append({"name": "issue_refund", "args": {"order_id": order_id}, "result": result})
        if result.get("ok"):
            refund_amount = float(result["amount_usd"])
    else:
        calls.append(
            {
                "name": "noop",
                "args": {},
                "result": {"ok": True, "message": "No tool required for task type"},
            }
        )

    return {
        "tool_calls": calls,
        "refund_amount_usd": refund_amount,
        "notes": _notes(state) + [f"tools:{calls[0]['name'] if calls else 'none'}"],
    }


def draft_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    task_type = state.get("task_type") or "unknown"
    model_id = state.get("model_id") or "unknown"
    citations = state.get("citations") or []
    tool_calls = state.get("tool_calls") or []

    if task_type == "order_status" and tool_calls:
        result = tool_calls[0].get("result", {})
        if result.get("ok"):
            answer = (
                f"Order {result['order_id']} is currently **{result['status']}**. "
                f"Tracking: {result.get('tracking_number') or 'n/a'}."
            )
        else:
            answer = f"I could not look up that order: {result.get('error')}"
    elif task_type == "return_request" and tool_calls:
        result = tool_calls[0].get("result", {})
        answer = result.get("message") or result.get("error") or "Return could not be processed."
    elif task_type == "refund_request" and tool_calls:
        result = tool_calls[0].get("result", {})
        answer = result.get("message") or result.get("error") or "Refund could not be processed."
    elif citations:
        top = citations[0]
        answer = (
            f"Based on VoltEdge policy `{top['doc_id']}` ({top['title']}): {top['excerpt']}"
        )
    elif task_type == "unknown":
        answer = (
            "I'm not sure how to help with that yet. "
            "A support specialist can take a closer look."
        )
    else:
        answer = (
            "I understood your request but need more detail "
            "(include order ID VE-#### when asking about an order)."
        )

    answer = f"{answer}\n\n_(Routed model: {model_id}; drafting is local stub — no Bedrock call.)_"
    return {
        "answer": answer,
        "notes": _notes(state) + ["draft:ok"],
    }


def confidence_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    confidence = score_confidence(
        classifier_confidence=float(state.get("classifier_confidence") or 0.0),
        task_type=state.get("task_type") or "unknown",
        citations=list(state.get("citations") or []),
        tool_calls=list(state.get("tool_calls") or []),
    )
    return {
        "confidence": confidence,
        "notes": _notes(state) + [f"confidence:{confidence}"],
    }


def hitl_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {"status": state.get("status") or "rejected"}
    status, reason = hitl_decision(
        task_type=state.get("task_type") or "unknown",
        confidence=float(state.get("confidence") or 0.0),
        refund_amount_usd=state.get("refund_amount_usd"),
    )
    return {
        "status": status,
        "hitl_reason": reason,
        "notes": _notes(state) + [f"hitl:{status}"],
    }


def after_route(
    state: AgentState,
) -> Literal["retrieve", "tools", "draft"]:
    if state.get("error"):
        return "draft"
    task_type = state.get("task_type") or "unknown"
    if task_type in ("order_status", "return_request", "refund_request"):
        return "tools"
    if task_type in ("faq_policy", "product_question"):
        return "retrieve"
    return "draft"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("validate", instrument_node("validate", validate_node))
    graph.add_node("classify", instrument_node("classify", classify_node))
    graph.add_node("route", instrument_node("route", route_node))
    graph.add_node("retrieve", instrument_node("retrieve", retrieve_node))
    graph.add_node("tools", instrument_node("tools", tools_node))
    graph.add_node("draft", instrument_node("draft", draft_node))
    graph.add_node("confidence", instrument_node("confidence", confidence_node))
    graph.add_node("hitl", instrument_node("hitl", hitl_node))

    graph.add_edge(START, "validate")
    graph.add_edge("validate", "classify")
    graph.add_edge("classify", "route")
    graph.add_conditional_edges(
        "route",
        after_route,
        {"retrieve": "retrieve", "tools": "tools", "draft": "draft"},
    )
    graph.add_edge("retrieve", "draft")
    graph.add_edge("tools", "draft")
    graph.add_edge("draft", "confidence")
    graph.add_edge("confidence", "hitl")
    graph.add_edge("hitl", END)
    return graph.compile()


_APP = None


def get_app():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP


def run_agent(
    message: str,
    session_id: str | None = None,
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Execute the SupportRouter graph and return a JSON-serializable result."""
    app = get_app()
    resolved_session_id = session_id or str(uuid.uuid4())
    resolved_correlation_id = correlation_id or new_correlation_id()
    emit_conversation_start(
        session_id=resolved_session_id,
        correlation_id=resolved_correlation_id,
        message=message,
    )
    started = time.perf_counter()
    final: AgentState = app.invoke(
        {
            "session_id": resolved_session_id,
            "correlation_id": resolved_correlation_id,
            "message": message,
        }
    )
    result = {
        "session_id": final.get("session_id") or resolved_session_id,
        "correlation_id": resolved_correlation_id,
        "task_type": final.get("task_type"),
        "model_id": final.get("model_id"),
        "routing_table_version": final.get("routing_table_version"),
        "classifier_rationale": final.get("classifier_rationale"),
        "answer": final.get("answer"),
        "citations": final.get("citations") or [],
        "tool_calls": final.get("tool_calls") or [],
        "confidence": final.get("confidence"),
        "status": final.get("status"),
        "hitl_reason": final.get("hitl_reason"),
        "refund_amount_usd": final.get("refund_amount_usd"),
        "notes": final.get("notes") or [],
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cache_enabled": False,
        },
        "cost_usd": None,
        "cost_status": "not_measured",
        "cost_note": "not measured (local stubs; no Bedrock invocation)",
    }
    emit_conversation_end(
        session_id=str(result["session_id"]),
        correlation_id=resolved_correlation_id,
        result=result,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
    )
    return result
