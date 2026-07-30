"""Thin Bedrock Runtime Converse helper for eval and drafting adapters."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from supportrouter.prompt_cache import (
    cache_usage_from_bedrock,
    normalize_system_blocks,
    unavailable_cache_usage,
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def converse_text(
    *,
    model_id: str,
    system: str | Sequence[Mapping[str, Any]],
    user: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
    client: Any | None = None,
    prompt_cache: bool = False,
) -> dict[str, Any]:
    """Invoke Bedrock Converse and return text plus usage.

    When ``prompt_cache`` is True, a Converse ``cachePoint`` is appended to the
    system blocks (unless one is already present). Usage includes
    ``cache_enabled``, ``cache_status``, and cache read/write token fields.

    Returns:
        ``{"text": str, "usage": {...}, "stop_reason": str | None, "model_id": str}``
    """
    if client is None:
        import boto3

        client = boto3.client("bedrock-runtime")

    system_blocks = normalize_system_blocks(system, prompt_cache=prompt_cache)
    response = client.converse(
        modelId=model_id,
        system=system_blocks,
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    )
    text_parts: list[str] = []
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
    usage = response.get("usage") or {}
    input_tokens = usage.get("inputTokens")
    output_tokens = usage.get("outputTokens")
    total_tokens = usage.get("totalTokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = int(input_tokens) + int(output_tokens)
    cache_fields = (
        cache_usage_from_bedrock(usage, cache_enabled=True)
        if prompt_cache
        else unavailable_cache_usage()
    )
    return {
        "text": "".join(text_parts).strip(),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            **cache_fields,
        },
        "stop_reason": response.get("stopReason"),
        "model_id": model_id,
    }


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model response, tolerating fenced wrappers."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = _JSON_OBJECT.search(cleaned)
        if not match:
            raise ValueError("response did not contain a JSON object") from None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload
