"""Map AgentCore Runtime payloads onto ``run_agent`` (ADR-024).

Keeps domain seams unchanged; only host-adapter concerns live here.
"""

from __future__ import annotations

import logging
from typing import Any

from supportrouter.api import MAX_MESSAGE_CHARS, MAX_SESSION_ID_CHARS, _PUBLIC_FIELDS
from supportrouter.graph import run_agent
from supportrouter.observability import PLANE_RUNTIME, new_correlation_id
from supportrouter.runtime_mode import normalize_runtime_mode
from supportrouter.sessions import save_session

logger = logging.getLogger(__name__)


class AgentCoreBadRequest(ValueError):
    """Invalid AgentCore invocation payload."""


def parse_agentcore_payload(payload: dict[str, Any] | None) -> tuple[str, str | None, str | None]:
    """Extract ``message``/``prompt``, optional ``session_id``, ``runtime_mode``."""
    if not isinstance(payload, dict):
        raise AgentCoreBadRequest("Payload must be a JSON object")

    raw_message = payload.get("message", payload.get("prompt"))
    if not isinstance(raw_message, str) or not raw_message.strip():
        raise AgentCoreBadRequest(
            "Field 'message' or 'prompt' is required and must be a non-empty string"
        )
    message = raw_message.strip()
    if len(message) > MAX_MESSAGE_CHARS:
        raise AgentCoreBadRequest(
            f"Field 'message'/'prompt' exceeds {MAX_MESSAGE_CHARS} characters"
        )

    session_id = payload.get("session_id")
    if session_id is not None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise AgentCoreBadRequest(
                "Field 'session_id' must be a non-empty string when provided"
            )
        if len(session_id) > MAX_SESSION_ID_CHARS:
            raise AgentCoreBadRequest(
                f"Field 'session_id' exceeds {MAX_SESSION_ID_CHARS} characters"
            )
        session_id = session_id.strip()

    runtime_mode = payload.get("runtime_mode")
    if runtime_mode is not None:
        if not isinstance(runtime_mode, str) or not runtime_mode.strip():
            raise AgentCoreBadRequest(
                "Field 'runtime_mode' must be a non-empty string when provided"
            )
        try:
            normalize_runtime_mode(runtime_mode)
        except ValueError as exc:
            raise AgentCoreBadRequest(str(exc)) from exc
        runtime_mode = runtime_mode.strip()

    return message, session_id, runtime_mode


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result.get(field) for field in _PUBLIC_FIELDS}


def handle_agentcore_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Run the agent for one AgentCore invocation and return a public result dict."""
    correlation_id = new_correlation_id()
    try:
        message, session_id, runtime_mode = parse_agentcore_payload(payload)
    except AgentCoreBadRequest as exc:
        return {
            "error": str(exc),
            "correlation_id": correlation_id,
            "status": "rejected",
        }

    try:
        result = run_agent(
            message,
            session_id=session_id,
            correlation_id=correlation_id,
            plane=PLANE_RUNTIME,
            runtime_mode=runtime_mode,
        )
        result = save_session(result)
    except Exception:  # noqa: BLE001 — host must not leak internals
        logger.exception(
            "agentcore handler failed",
            extra={"correlation_id": correlation_id},
        )
        return {
            "error": "Internal error handling support request",
            "correlation_id": correlation_id,
            "status": "error",
        }

    public = _public_result(result)
    public["correlation_id"] = result.get("correlation_id") or correlation_id
    return public
