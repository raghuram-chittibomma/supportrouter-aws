"""AWS Lambda tool adapters for SupportRouter runtime mode=aws."""

from __future__ import annotations

import json
import os
from typing import Any

TOOL_ENV = {
    "get_order_status": "GET_ORDER_STATUS_FUNCTION_NAME",
    "initiate_return": "INITIATE_RETURN_FUNCTION_NAME",
    "issue_refund": "ISSUE_REFUND_FUNCTION_NAME",
}


def _client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    import boto3

    return boto3.client("lambda")


def _function_name(tool: str) -> str:
    env_key = TOOL_ENV[tool]
    name = os.environ.get(env_key, "").strip()
    if not name:
        raise RuntimeError(
            f"{env_key} is required for AWS tool '{tool}'. "
            "Deploy SupportRouter-Tools and set the function name env var."
        )
    return name


def invoke_tool(
    tool: str,
    *,
    order_id: str,
    client: Any | None = None,
) -> dict[str, Any]:
    """Invoke an isolated Tools Lambda and return its JSON payload."""
    if tool not in TOOL_ENV:
        raise ValueError(f"Unknown AWS tool '{tool}'")
    response = _client(client).invoke(
        FunctionName=_function_name(tool),
        InvocationType="RequestResponse",
        Payload=json.dumps({"order_id": order_id}).encode("utf-8"),
    )
    raw = response.get("Payload")
    body = raw.read() if hasattr(raw, "read") else raw
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    if response.get("FunctionError"):
        raise RuntimeError(f"Lambda {tool} failed: {body}")
    payload = json.loads(body or "{}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Lambda {tool} returned a non-object payload")
    return payload
