"""HTTP adapter that exposes the SupportRouter agent over API Gateway.

This module is a thin, deterministic edge over :func:`run_agent`. It parses an
API Gateway HTTP API (payload format 2.0) proxy event, runs the local agent, and
returns a proxy-shaped response. It performs no AWS calls itself; the agent still
uses local stubs, so a live deploy stays honest about being unmeasured.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from supportrouter.graph import run_agent
from supportrouter.observability import PLANE_RUNTIME, new_correlation_id

MAX_MESSAGE_CHARS = 4000
JSON_HEADERS = {"content-type": "application/json"}


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
            body = base64.b64decode(body).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise BadRequest("Request body is not valid base64 UTF-8") from exc
    return body


def parse_request(event: dict[str, Any]) -> tuple[str, str | None]:
    """Extract and validate ``message`` and optional ``session_id``."""
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
    if session_id is not None and (
        not isinstance(session_id, str) or not session_id.strip()
    ):
        raise BadRequest("Field 'session_id' must be a non-empty string when provided")

    return message, (session_id.strip() if isinstance(session_id, str) else None)


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
        message, session_id = parse_request(event)
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
        )
    except Exception:  # noqa: BLE001 — edge must not leak internals to callers
        return _response(
            500,
            {
                "error": "Internal error handling support request",
                "correlation_id": correlation_id,
            },
            correlation_id=correlation_id,
        )

    status_code = 200 if result.get("status") != "rejected" else 422
    return _response(status_code, result, correlation_id=result["correlation_id"])


handler = handle_chat_request
