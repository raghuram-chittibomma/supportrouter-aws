"""LangGraph runtime agent for SupportRouter (local default; AWS mode optional)."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from supportrouter.bedrock_converse import converse_text
from supportrouter.bedrock_models import estimate_cost_usd, resolve_inference_profile
from supportrouter.classifier import classify
from supportrouter.decision import hitl_decision, score_confidence
from supportrouter.guardrails import (
    GUARDRAIL_REDACTED_MESSAGE,
    LOCAL_GUARDRAIL_IDENTIFIER,
    LOCAL_GUARDRAIL_VERSION,
    assess,
    blocked_message,
    skipped_assessment,
)
from supportrouter.observability import (
    PLANE_EVAL,
    PLANE_RUNTIME,
    emit_conversation_end,
    emit_conversation_start,
    instrument_node,
    new_correlation_id,
)
from supportrouter.draft_honesty import (
    HONEST_DRAFT_INSTRUCTIONS,
    enforce_execution_honesty,
)
from supportrouter.prompt_cache import (
    agent_cacheable_prefix,
    converse_system_with_cache_point,
    unavailable_cache_usage,
)
from supportrouter.retrieve import retrieve
from supportrouter.router import route
from supportrouter.runtime_mode import RuntimeMode, normalize_runtime_mode
from supportrouter.state import AgentState
from supportrouter.tools_aws import invoke_tool
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


def input_guardrail_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {"guardrail_input": skipped_assessment(stage="input").as_dict()}
    mode = state.get("runtime_mode") or "local"
    assessment = assess(
        state.get("message") or "",
        stage="input",
        runtime_mode=mode,
    )
    result: dict[str, Any] = {
        "guardrail_input": assessment.as_dict(),
        "notes": _notes(state) + [f"guardrail_input:{assessment.action}"],
    }
    if assessment.action == "blocked":
        result.update(
            {
                "error": "guardrail_input_blocked",
                "message": GUARDRAIL_REDACTED_MESSAGE,
                "status": "rejected",
                "answer": blocked_message(
                    stage="input",
                    categories=assessment.categories,
                ),
                "confidence": 0.0,
            }
        )
    return result


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
    mode = state.get("runtime_mode") or "local"
    notes = _notes(state)
    if mode == "aws" and os.environ.get("SUPPORTROUTER_KB_ID", "").strip():
        citations = retrieve(
            state["message"], task_type, provider="bedrock"
        )
        provider = "bedrock"
        notes = notes + [f"retrieve:bedrock:{len(citations)}"]
    else:
        citations = retrieve(state["message"], task_type, provider="local")
        provider = "local"
        if mode == "aws":
            provider = "local_fallback"
            notes = notes + [f"retrieve:aws_fallback_local:{len(citations)}"]
        else:
            notes = notes + [f"retrieve:local:{len(citations)}"]
    if not citations:
        notes = notes + ["retrieve:relevance_empty"]
    return {
        "citations": citations,
        "retrieve_provider": provider,
        "notes": notes,
    }


def tools_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    task_type = state.get("task_type") or "unknown"
    order_id = extract_order_id(state["message"])
    calls: list[dict[str, Any]] = []
    refund_amount: float | None = None
    mode = state.get("runtime_mode") or "local"

    def _call_tool(name: str, oid: str) -> dict[str, Any]:
        if mode == "aws":
            return invoke_tool(name, order_id=oid)
        if name == "get_order_status":
            return get_order_status(oid)
        if name == "initiate_return":
            return initiate_return(oid)
        if name == "issue_refund":
            return issue_refund(oid)
        raise ValueError(f"Unknown tool {name}")

    if order_id is None:
        calls.append(
            {
                "name": "missing_order_id",
                "args": {},
                "result": {"ok": False, "error": "No order ID (VE-####) found in message"},
            }
        )
    elif task_type == "order_status":
        result = _call_tool("get_order_status", order_id)
        calls.append({"name": "get_order_status", "args": {"order_id": order_id}, "result": result})
    elif task_type == "return_request":
        result = _call_tool("initiate_return", order_id)
        calls.append({"name": "initiate_return", "args": {"order_id": order_id}, "result": result})
    elif task_type == "refund_request":
        result = _call_tool("issue_refund", order_id)
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
        "notes": _notes(state)
        + [f"tools:{mode}:{calls[0]['name'] if calls else 'none'}"],
    }


def _draft_local_answer(state: AgentState) -> str:
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
    return (
        f"{answer}\n\n_(Routed model: {model_id}; drafting is local stub — "
        "no Bedrock call.)_"
    )


def draft_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    mode = state.get("runtime_mode") or "local"
    tool_calls = list(state.get("tool_calls") or [])
    if mode != "aws":
        answer, rewritten = enforce_execution_honesty(
            _draft_local_answer(state), tool_calls
        )
        notes = _notes(state) + ["draft:local"]
        if rewritten:
            notes = notes + ["draft:honesty_rewrite"]
        return {
            "answer": answer,
            "draft_usage": None,
            "draft_cost_usd": None,
            "actual_model_id": state.get("model_id"),
            "notes": notes,
        }

    routed = state.get("model_id") or "amazon.nova-micro"
    profile_id = resolve_inference_profile(routed)
    user_payload = {
        "customer_message": state.get("message"),
        "task_type": state.get("task_type"),
        "citations": state.get("citations") or [],
        "tool_calls": tool_calls,
        "instructions": HONEST_DRAFT_INSTRUCTIONS,
    }
    agent_prefix = agent_cacheable_prefix()
    draft = converse_text(
        model_id=profile_id,
        system=converse_system_with_cache_point(agent_prefix),
        user=json.dumps(user_payload, indent=2),
        max_tokens=400,
        temperature=0.0,
        prompt_cache=True,
    )
    text = draft["text"].strip()
    if not text:
        text = (
            "I could not draft a Bedrock response for this turn. "
            "Please try again or switch to Local mode."
        )
    text, rewritten = enforce_execution_honesty(text, tool_calls)
    usage = draft["usage"]
    notes = _notes(state) + [f"draft:aws:{profile_id}"]
    if rewritten:
        notes = notes + ["draft:honesty_rewrite"]
    return {
        "answer": text,
        "draft_usage": usage,
        "draft_cost_usd": estimate_cost_usd(profile_id, usage),
        "actual_model_id": profile_id,
        "notes": notes,
    }


def output_guardrail_node(state: AgentState) -> dict[str, Any]:
    if state.get("error"):
        return {"guardrail_output": skipped_assessment(stage="output").as_dict()}
    mode = state.get("runtime_mode") or "local"
    assessment = assess(
        state.get("answer") or "",
        stage="output",
        runtime_mode=mode,
    )
    result: dict[str, Any] = {
        "guardrail_output": assessment.as_dict(),
        "notes": _notes(state) + [f"guardrail_output:{assessment.action}"],
    }
    if assessment.action == "blocked":
        result.update(
            {
                "error": "guardrail_output_blocked",
                "status": "rejected",
                "answer": blocked_message(
                    stage="output",
                    categories=assessment.categories,
                ),
                "confidence": 0.0,
            }
        )
    return result


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
    graph.add_node(
        "guardrail_input",
        instrument_node("guardrail_input", input_guardrail_node),
    )
    graph.add_node("classify", instrument_node("classify", classify_node))
    graph.add_node("route", instrument_node("route", route_node))
    graph.add_node("retrieve", instrument_node("retrieve", retrieve_node))
    graph.add_node("tools", instrument_node("tools", tools_node))
    graph.add_node("draft", instrument_node("draft", draft_node))
    graph.add_node(
        "guardrail_output",
        instrument_node("guardrail_output", output_guardrail_node),
    )
    graph.add_node("confidence", instrument_node("confidence", confidence_node))
    graph.add_node("hitl", instrument_node("hitl", hitl_node))

    graph.add_edge(START, "validate")
    graph.add_edge("validate", "guardrail_input")
    graph.add_edge("guardrail_input", "classify")
    graph.add_edge("classify", "route")
    graph.add_conditional_edges(
        "route",
        after_route,
        {"retrieve": "retrieve", "tools": "tools", "draft": "draft"},
    )
    graph.add_edge("retrieve", "draft")
    graph.add_edge("tools", "draft")
    graph.add_edge("draft", "guardrail_output")
    graph.add_edge("guardrail_output", "confidence")
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
    plane: str = PLANE_RUNTIME,
    runtime_mode: str | None = None,
) -> dict[str, Any]:
    """Execute the SupportRouter graph and return a JSON-serializable result."""
    if plane not in {PLANE_RUNTIME, PLANE_EVAL}:
        raise ValueError("plane must be 'runtime' or 'eval'")
    mode: RuntimeMode = normalize_runtime_mode(runtime_mode)
    app = get_app()
    resolved_session_id = session_id or str(uuid.uuid4())
    resolved_correlation_id = correlation_id or new_correlation_id()
    emit_conversation_start(
        session_id=resolved_session_id,
        correlation_id=resolved_correlation_id,
        message=message,
        plane=plane,
    )
    started = time.perf_counter()
    try:
        final: AgentState = app.invoke(
            {
                "session_id": resolved_session_id,
                "correlation_id": resolved_correlation_id,
                "plane": plane,
                "runtime_mode": mode,
                "message": message,
            }
        )
    except Exception as exc:
        emit_conversation_end(
            session_id=resolved_session_id,
            correlation_id=resolved_correlation_id,
            result={"status": "error"},
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            plane=plane,
            error_type=type(exc).__name__,
        )
        raise
    agent_prefix = agent_cacheable_prefix()
    draft_usage = final.get("draft_usage")
    draft_cost = final.get("draft_cost_usd")
    cost_measured = mode == "aws" and draft_cost is not None
    guardrail_input = final.get("guardrail_input") or {}
    guardrail_output = final.get("guardrail_output") or {}
    guardrail_provider = (
        guardrail_input.get("provider")
        or guardrail_output.get("provider")
        or "local_deterministic"
    )
    guardrail_identifier = (
        guardrail_input.get("guardrail_identifier")
        or guardrail_output.get("guardrail_identifier")
        or LOCAL_GUARDRAIL_IDENTIFIER
    )
    guardrail_version = (
        guardrail_input.get("guardrail_version")
        or guardrail_output.get("guardrail_version")
        or LOCAL_GUARDRAIL_VERSION
    )
    result = {
        "session_id": final.get("session_id") or resolved_session_id,
        "correlation_id": resolved_correlation_id,
        "plane": plane,
        "runtime_mode": mode,
        "retrieve_provider": final.get("retrieve_provider") or "skipped",
        "task_type": final.get("task_type"),
        "model_id": final.get("model_id"),
        "actual_model_id": final.get("actual_model_id") or final.get("model_id"),
        "routing_table_version": final.get("routing_table_version"),
        "classifier_rationale": final.get("classifier_rationale"),
        "answer": final.get("answer"),
        "citations": final.get("citations") or [],
        "tool_calls": final.get("tool_calls") or [],
        "confidence": final.get("confidence"),
        "status": final.get("status"),
        "hitl_reason": final.get("hitl_reason"),
        "refund_amount_usd": final.get("refund_amount_usd"),
        "guardrail": {
            "identifier": guardrail_identifier,
            "version": guardrail_version,
            "provider": guardrail_provider,
            "input": guardrail_input or None,
            "output": guardrail_output or None,
        },
        "notes": final.get("notes") or [],
        "usage": {
            "input_tokens": (draft_usage or {}).get("input_tokens"),
            "output_tokens": (draft_usage or {}).get("output_tokens"),
            "total_tokens": (draft_usage or {}).get("total_tokens"),
            **(
                {
                    "cache_enabled": bool((draft_usage or {}).get("cache_enabled")),
                    "cache_status": (draft_usage or {}).get("cache_status")
                    or "not_configured",
                    "cache_read_tokens": (draft_usage or {}).get("cache_read_tokens"),
                    "cache_write_tokens": (draft_usage or {}).get("cache_write_tokens"),
                }
                if draft_usage and draft_usage.get("cache_enabled")
                else unavailable_cache_usage()
            ),
        },
        "cost_usd": draft_cost if cost_measured else None,
        "cost_status": "measured" if cost_measured else "not_measured",
        "cost_note": (
            "tokens × published on-demand rates incl. cache read/write when present "
            "(draft only; Guardrails API not measured)"
            if cost_measured
            else "not measured (local stubs or missing Bedrock usage)"
        ),
        "prompt_cache": {
            "prefix_name": agent_prefix.name,
            "prefix_version": agent_prefix.version,
            "prefix_sha256": agent_prefix.sha256,
        },
    }
    emit_conversation_end(
        session_id=str(result["session_id"]),
        correlation_id=resolved_correlation_id,
        result=result,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        plane=plane,
    )
    return result
