"""HTTP adapter that exposes the SupportRouter agent over API Gateway.

Parses an API Gateway HTTP API (payload format 2.0) proxy event, runs the agent
in ``local`` (default) or ``aws`` runtime mode (#66), persists session/approval
when DynamoDB tables are configured, and returns a curated proxy response.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from supportrouter.graph import run_agent
from supportrouter.observability import PLANE_RUNTIME, new_correlation_id
from supportrouter.runtime_mode import normalize_runtime_mode
from supportrouter.sessions import save_session

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4000
MAX_SESSION_ID_CHARS = 200
MAX_BODY_BYTES = 16 * 1024
JSON_HEADERS = {"content-type": "application/json"}

# Fields returned to HTTP clients. Internal aids (notes, classifier rationale,
# prompt-cache digests) stay out of the public edge response.
_PUBLIC_FIELDS = (
    "session_id",
    "correlation_id",
    "runtime_mode",
    "task_type",
    "model_id",
    "actual_model_id",
    "answer",
    "citations",
    "confidence",
    "status",
    "hitl_reason",
    "refund_amount_usd",
    "approval_id",
    "approval_status",
    "guardrail",
    "cost_status",
    "cost_usd",
    "cost_note",
)


class BadRequest(Exception):
    """Raised when the incoming request cannot be turned into an agent call."""


def _decode_body(event: dict[str, Any]) -> str:
    body = event.get("body")
    if body is None:
        raise BadRequest("Request body is required")
    if not isinstance(body, str):
        raise BadRequest("Request body must be a JSON string")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise BadRequest("Request body is not valid base64 UTF-8") from exc
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise BadRequest(f"Request body exceeds {MAX_BODY_BYTES} bytes")
    return body


def parse_request(event: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Extract and validate ``message``, optional ``session_id``, ``runtime_mode``."""
    if not isinstance(event, dict):
        raise BadRequest("Event must be an object")

    body = _decode_body(event)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BadRequest("Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise BadRequest("Request body must be a JSON object")

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise BadRequest("Field 'message' is required and must be a non-empty string")
    if len(message) > MAX_MESSAGE_CHARS:
        raise BadRequest(f"Field 'message' exceeds {MAX_MESSAGE_CHARS} characters")

    session_id = payload.get("session_id")
    if session_id is not None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise BadRequest(
                "Field 'session_id' must be a non-empty string when provided"
            )
        if len(session_id) > MAX_SESSION_ID_CHARS:
            raise BadRequest(
                f"Field 'session_id' exceeds {MAX_SESSION_ID_CHARS} characters"
            )

    runtime_mode = payload.get("runtime_mode")
    if runtime_mode is not None:
        if not isinstance(runtime_mode, str) or not runtime_mode.strip():
            raise BadRequest(
                "Field 'runtime_mode' must be a non-empty string when provided"
            )
        try:
            normalize_runtime_mode(runtime_mode)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc

    return (
        message.strip(),
        session_id.strip() if isinstance(session_id, str) else None,
        runtime_mode.strip() if isinstance(runtime_mode, str) else None,
    )


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result.get(field) for field in _PUBLIC_FIELDS}


def _response(
    status_code: int,
    body: dict[str, Any],
    *,
    correlation_id: str,
) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {**JSON_HEADERS, "x-correlation-id": correlation_id},
        "body": json.dumps(body),
    }


def handle_chat_request(
    event: dict[str, Any],
    context: Any = None,
) -> dict[str, Any]:
    """Run the agent for one HTTP chat request and return a proxy response."""
    del context
    correlation_id = new_correlation_id()
    try:
        message, session_id, runtime_mode = parse_request(event)
    except BadRequest as exc:
        return _response(
            400,
            {"error": str(exc), "correlation_id": correlation_id},
            correlation_id=correlation_id,
        )

    try:
        result = run_agent(
            message,
            session_id=session_id,
            correlation_id=correlation_id,
            plane=PLANE_RUNTIME,
            runtime_mode=runtime_mode,
        )
        result = save_session(result)
    except Exception:  # noqa: BLE001 — edge must not leak internals to callers
        logger.exception(
            "chat handler failed", extra={"correlation_id": correlation_id}
        )
        return _response(
            500,
            {
                "error": "Internal error handling support request",
                "correlation_id": correlation_id,
            },
            correlation_id=correlation_id,
        )

    resolved_correlation_id = result.get("correlation_id") or correlation_id
    status_code = 200 if result.get("status") != "rejected" else 422
    return _response(
        status_code,
        _public_result(result),
        correlation_id=resolved_correlation_id,
    )


handler = handle_chat_request
