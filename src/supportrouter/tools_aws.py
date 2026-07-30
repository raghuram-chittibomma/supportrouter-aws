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

# CDK ToolsStack names (PROJECT_NAME=supportrouter). Used when env is unset so
# local Gradio/CLI aws mode works without copying Lambda env vars by hand.
DEFAULT_FUNCTION_NAMES = {
    "get_order_status": "supportrouter-get-order-status",
    "initiate_return": "supportrouter-initiate-return",
    "issue_refund": "supportrouter-issue-refund",
}


def _client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    import boto3

    return boto3.client("lambda")


def _function_name(tool: str) -> str:
    env_key = TOOL_ENV[tool]
    name = os.environ.get(env_key, "").strip()
    if name:
        return name
    return DEFAULT_FUNCTION_NAMES[tool]


def invoke_tool(
    tool: str,
    *,
    order_id: str,
    client: Any | None = None,
) -> dict[str, Any]:
    """Invoke an isolated Tools Lambda and return its JSON payload."""
    if tool not in TOOL_ENV:
        raise ValueError(f"Unknown AWS tool '{tool}'")
    function_name = _function_name(tool)
    response = _client(client).invoke(
        FunctionName=function_name,
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
