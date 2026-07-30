"""Shared Bedrock model ID mapping and token cost estimates."""

from __future__ import annotations

from typing import Any

# Account/region-resolved inference profiles (#24 / #25).
ROUTING_TO_INFERENCE_PROFILE = {
    "amazon.nova-micro": "us.amazon.nova-micro-v1:0",
    "amazon.nova-lite": "us.amazon.nova-lite-v1:0",
    "anthropic.claude-haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "logical:nova-micro": "us.amazon.nova-micro-v1:0",
    "logical:nova-lite": "us.amazon.nova-lite-v1:0",
    "logical:claude-haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}

_USD_PER_1K_TOKENS = {
    "us.amazon.nova-micro-v1:0": {"input": 0.000035, "output": 0.00014},
    "us.amazon.nova-lite-v1:0": {"input": 0.00006, "output": 0.00024},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {
        "input": 0.001,
        "output": 0.005,
    },
}


def resolve_inference_profile(model_id: str) -> str:
    key = (model_id or "").strip()
    if not key:
        raise ValueError("model_id is required")
    if key in ROUTING_TO_INFERENCE_PROFILE:
        return ROUTING_TO_INFERENCE_PROFILE[key]
    if key.startswith(("us.", "global.", "amazon.", "anthropic.")):
        return key
    raise ValueError(
        f"Unknown model_id '{model_id}'. Expected a routing-table ID, "
        f"logical candidate, or Bedrock inference profile."
    )


def estimate_cost_usd(model_id: str, usage: dict[str, Any] | None) -> float | None:
    if not usage:
        return None
    rates = _USD_PER_1K_TOKENS.get(model_id)
    if rates is None:
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    return round(
        (int(input_tokens) / 1000.0) * rates["input"]
        + (int(output_tokens) / 1000.0) * rates["output"],
        8,
    )
