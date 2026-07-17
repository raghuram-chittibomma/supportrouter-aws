"""Local observability emitter with CloudWatch-compatible event shape.

Token and cost fields are always present. Until Bedrock is wired they remain
null / not_measured rather than invented values.
"""

from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

from supportrouter.prompt_cache import unavailable_cache_usage

LOGGER = logging.getLogger("supportrouter.observability")

AGENT_STEPS = (
    "validate",
    "classify",
    "route",
    "retrieve",
    "tools",
    "draft",
    "confidence",
    "hitl",
)

PLANE_RUNTIME = "runtime"
PLANE_EVAL = "eval"


class TraceSink(Protocol):
    def emit(self, event: dict[str, Any]) -> None:
        """Persist or forward one structured observability event."""


class InMemoryTraceSink:
    """Process-local sink used by tests and the local demo."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(deepcopy(event))

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class LoggingTraceSink:
    """Emit one JSON object per line for CloudWatch Logs Insights."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or LOGGER

    def emit(self, event: dict[str, Any]) -> None:
        self._logger.info(json.dumps(event, sort_keys=True, default=str))


_DEFAULT_SINK = InMemoryTraceSink()
_ACTIVE_SINK: TraceSink = _DEFAULT_SINK


def get_trace_sink() -> TraceSink:
    return _ACTIVE_SINK


def set_trace_sink(sink: TraceSink | None) -> TraceSink:
    """Replace the active sink; pass None to restore the default in-memory sink."""
    global _ACTIVE_SINK
    _ACTIVE_SINK = sink or _DEFAULT_SINK
    return _ACTIVE_SINK


def clear_traces() -> None:
    sink = _ACTIVE_SINK
    clear = getattr(sink, "clear", None)
    if callable(clear):
        clear()


def list_traces() -> list[dict[str, Any]]:
    sink = _ACTIVE_SINK
    events = getattr(sink, "events", None)
    if callable(events):
        return events()
    return []


def new_correlation_id() -> str:
    return str(uuid4())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(
    *,
    event_type: str,
    session_id: str,
    correlation_id: str,
    step: str | None = None,
    plane: str = PLANE_RUNTIME,
    status: str | None = None,
    duration_ms: float | None = None,
    attributes: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a CloudWatch-compatible structured event."""
    token_usage = {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        **unavailable_cache_usage(),
        **(usage or {}),
    }
    return {
        "schema_version": "v0.1",
        "event_type": event_type,
        "timestamp": _utc_now(),
        "plane": plane,
        "correlation_id": correlation_id,
        "session_id": session_id,
        "step": step,
        "status": status,
        "duration_ms": duration_ms,
        "usage": token_usage,
        "cost_usd": None,
        "cost_status": "not_measured",
        "attributes": attributes or {},
    }


def emit_event(**kwargs: Any) -> dict[str, Any]:
    event = build_event(**kwargs)
    get_trace_sink().emit(event)
    return event


def instrument_node(step_name: str, node_fn):
    """Wrap a LangGraph node so each step emits a structured trace event."""

    def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        session_id = str(state.get("session_id") or "unknown")
        correlation_id = str(state.get("correlation_id") or session_id)
        plane = str(state.get("plane") or PLANE_RUNTIME)
        was_short_circuited = bool(state.get("error"))
        started = time.perf_counter()
        try:
            result = node_fn(state)
        except Exception as exc:  # pragma: no cover - defensive path
            emit_event(
                event_type="agent.step",
                session_id=session_id,
                correlation_id=correlation_id,
                step=step_name,
                plane=plane,
                status="error",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                attributes={"error_type": type(exc).__name__},
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        notes = list(result.get("notes") or state.get("notes") or [])
        conversation_status = result.get("status") or state.get("status")
        emit_event(
            event_type="agent.step",
            session_id=str(result.get("session_id") or session_id),
            correlation_id=correlation_id,
            step=step_name,
            plane=plane,
            status="skipped" if was_short_circuited else "ok",
            duration_ms=duration_ms,
            attributes={
                "task_type": result.get("task_type") or state.get("task_type"),
                "model_id": result.get("model_id") or state.get("model_id"),
                "note": notes[-1] if notes else None,
                "conversation_status": conversation_status,
                "has_error": bool(result.get("error") or state.get("error")),
            },
        )
        return result

    wrapped.__name__ = getattr(node_fn, "__name__", step_name)
    wrapped.__qualname__ = getattr(node_fn, "__qualname__", step_name)
    return wrapped


def emit_conversation_start(
    *,
    session_id: str,
    correlation_id: str,
    message: str,
    plane: str = PLANE_RUNTIME,
) -> dict[str, Any]:
    return emit_event(
        event_type="conversation.start",
        session_id=session_id,
        correlation_id=correlation_id,
        plane=plane,
        status="open",
        attributes={"message_chars": len(message or "")},
    )


def emit_conversation_end(
    *,
    session_id: str,
    correlation_id: str,
    result: dict[str, Any],
    duration_ms: float,
    plane: str = PLANE_RUNTIME,
    error_type: str | None = None,
) -> dict[str, Any]:
    return emit_event(
        event_type="conversation.end",
        session_id=session_id,
        correlation_id=correlation_id,
        plane=plane,
        status=str(result.get("status") or "unknown"),
        duration_ms=duration_ms,
        usage=result.get("usage"),
        attributes={
            "task_type": result.get("task_type"),
            "model_id": result.get("model_id"),
            "confidence": result.get("confidence"),
            "tool_count": len(result.get("tool_calls") or []),
            "citation_count": len(result.get("citations") or []),
            "approval_id": result.get("approval_id"),
            "error_type": error_type,
        },
    )


def emit_hitl_decision(
    *,
    session_id: str,
    correlation_id: str,
    decision: str,
    status: str,
    approval_id: str | None,
    plane: str = PLANE_RUNTIME,
) -> dict[str, Any]:
    return emit_event(
        event_type="hitl.decision",
        session_id=session_id,
        correlation_id=correlation_id,
        step="hitl_decision",
        plane=plane,
        status=status,
        attributes={
            "decision": decision,
            "approval_id": approval_id,
        },
    )
