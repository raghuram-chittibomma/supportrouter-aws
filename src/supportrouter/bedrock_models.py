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

# Published on-demand USD per 1K tokens (Bedrock pricing page at measurement time).
# Cache write/read multipliers follow Anthropic Claude on Bedrock (1.25x / 0.1x)
# and Nova explicit cache read discount (0.1x); write priced at standard input.
_USD_PER_1K_TOKENS = {
    "us.amazon.nova-micro-v1:0": {
        "input": 0.000035,
        "output": 0.00014,
        "cache_write": 0.000035,
        "cache_read": 0.0000035,
    },
    "us.amazon.nova-lite-v1:0": {
        "input": 0.00006,
        "output": 0.00024,
        "cache_write": 0.00006,
        "cache_read": 0.000006,
    },
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {
        "input": 0.001,
        "output": 0.005,
        "cache_write": 0.00125,
        "cache_read": 0.0001,
    },
}

# Map logical candidates / inference profiles back to routing-table model IDs.
_INFERENCE_TO_ROUTING = {
    profile: routing
    for routing, profile in ROUTING_TO_INFERENCE_PROFILE.items()
    if not routing.startswith("logical:")
}
_LOGICAL_TO_ROUTING = {
    "logical:nova-micro": "amazon.nova-micro",
    "logical:nova-lite": "amazon.nova-lite",
    "logical:claude-haiku": "anthropic.claude-haiku",
}


def to_routing_model_id(model_id: str) -> str:
    """Normalize logical / inference / routing IDs to routing-table ``model_id``."""
    key = (model_id or "").strip()
    if not key:
        raise ValueError("model_id is required")
    if key in _LOGICAL_TO_ROUTING:
        return _LOGICAL_TO_ROUTING[key]
    if key in _INFERENCE_TO_ROUTING:
        return _INFERENCE_TO_ROUTING[key]
    if key in ROUTING_TO_INFERENCE_PROFILE and not key.startswith("logical:"):
        return key
    raise ValueError(f"Cannot map model_id '{model_id}' to a routing-table ID")


def published_input_cost_per_1k(model_id: str) -> float | None:
    """Published on-demand input USD per 1K tokens for a routing or profile ID."""
    profile = resolve_inference_profile(model_id)
    rates = _USD_PER_1K_TOKENS.get(profile)
    if rates is None:
        return None
    return rates["input"]


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
    """Estimate USD from token usage, including cache read/write when present.

    When Bedrock returns cache fields, ``input_tokens`` is the uncached input
    portion; cache read/write tokens are billed at their respective rates.
    """
    if not usage:
        return None
    rates = _USD_PER_1K_TOKENS.get(model_id)
    if rates is None:
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    cache_read = int(usage.get("cache_read_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or 0)
    return round(
        (int(input_tokens) / 1000.0) * rates["input"]
        + (cache_write / 1000.0) * rates["cache_write"]
        + (cache_read / 1000.0) * rates["cache_read"]
        + (int(output_tokens) / 1000.0) * rates["output"],
        8,
    )


def estimate_uncached_equivalent_cost_usd(
    model_id: str,
    usage: dict[str, Any] | None,
) -> float | None:
    """Price the same token mix as if every input token paid the full input rate."""
    if not usage:
        return None
    rates = _USD_PER_1K_TOKENS.get(model_id)
    if rates is None:
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    cache_read = int(usage.get("cache_read_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or 0)
    total_input = int(input_tokens) + cache_read + cache_write
    return round(
        (total_input / 1000.0) * rates["input"]
        + (int(output_tokens) / 1000.0) * rates["output"],
        8,
    )
