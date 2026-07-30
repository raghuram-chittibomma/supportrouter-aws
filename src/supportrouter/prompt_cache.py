"""Stable prompt-prefix checkpoints for Bedrock prompt caching (ADR-005 / ADR-021)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

AGENT_PROMPT_VERSION = "agent-prefix-v0.3"

# Haiku 4.5 requires >=4096 tokens per checkpoint; Nova Micro/Lite ~1536.
# Claude tokenizes ~4–4.5 chars/token on this padding; size with headroom.
AGENT_CACHE_MIN_TOKENS = 2000
JUDGE_CACHE_MIN_TOKENS = 5510
_CHARS_PER_TOKEN_ESTIMATE = 4

AGENT_SYSTEM_INSTRUCTIONS = (
    "You are the VoltEdge Electronics support agent. All company, customer, "
    "order, product, and policy data is synthetic.",
    "Use deterministic routing and tool results as authoritative. Cite the "
    "provided synthetic knowledge documents for policy and product claims.",
    "Never claim a refund or return payment was processed, emailed, or funded "
    "when tool results report execution_status=not_executed. Prefer prepared / "
    "initiated / pending approval language from the tool message. Escalate when "
    "required evidence is absent.",
)

AGENT_TOOL_SCHEMAS: tuple[dict[str, Any], ...] = (
    {
        "name": "get_order_status",
        "description": "Read status and tracking for one synthetic VoltEdge order.",
        "input": {"type": "object", "required": ["order_id"], "properties": {"order_id": {"type": "string"}}},
    },
    {
        "name": "initiate_return",
        "description": "Create a synthetic return authorization for an eligible order.",
        "input": {"type": "object", "required": ["order_id"], "properties": {"order_id": {"type": "string"}}},
    },
    {
        "name": "issue_refund",
        "description": "Prepare a synthetic eligible refund and report whether approval is required.",
        "input": {"type": "object", "required": ["order_id"], "properties": {"order_id": {"type": "string"}}},
    },
)

DEFAULT_CACHE_POINT: dict[str, Any] = {"cachePoint": {"type": "default"}}


@dataclass(frozen=True)
class CacheablePrefix:
    """Versioned, immutable prefix; request-specific content is appended later."""

    name: str
    version: str
    blocks: tuple[Mapping[str, Any], ...]
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "blocks": [dict(block) for block in self.blocks],
            "sha256": self.sha256,
        }

    def stable_text(self) -> str:
        """Concatenate text content blocks in cache order."""
        parts: list[str] = []
        for block in self.blocks:
            content = block.get("content")
            if isinstance(content, str) and content:
                parts.append(content)
        return "\n\n".join(parts)


def build_cacheable_prefix(
    *,
    name: str,
    version: str,
    blocks: tuple[dict[str, Any], ...],
) -> CacheablePrefix:
    if not name or not version or not blocks:
        raise ValueError("cacheable prefix requires name, version, and blocks")
    canonical = json.dumps(
        {"name": name, "version": version, "blocks": blocks},
        sort_keys=True,
        separators=(",", ":"),
    )
    immutable_blocks = tuple(
        MappingProxyType(
            json.loads(json.dumps(block, sort_keys=True, separators=(",", ":")))
        )
        for block in blocks
    )
    return CacheablePrefix(
        name=name,
        version=version,
        blocks=immutable_blocks,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def deterministic_cache_padding(*, label: str, min_tokens: int) -> str:
    """Byte-stable filler so prefixes meet Bedrock per-checkpoint minima."""
    if min_tokens < 1:
        raise ValueError("min_tokens must be >= 1")
    unit = (
        f"[{label}] Synthetic VoltEdge Electronics cache-prefix padding. "
        "This text is fictional retail policy and catalog context used only to "
        "meet Bedrock prompt-cache minimum token thresholds. It must remain "
        "byte-stable across requests. Orders use VE-#### identifiers. Eligible "
        "returns are accepted within 30 days of delivery when unused and in "
        "original packaging. Refunds at or below 100 USD may auto-issue after "
        "eligibility checks; amounts above 100 USD require supervisor approval. "
        "PowerDock Mini is a portable USB-C battery accessory. Support answers "
        "must cite synthetic knowledge documents and never invent order facts. "
    )
    target_chars = min_tokens * _CHARS_PER_TOKEN_ESTIMATE
    repeats = max(1, (target_chars + len(unit) - 1) // len(unit))
    padded = unit * repeats
    return padded[: max(target_chars, len(unit))]


def agent_cacheable_prefix() -> CacheablePrefix:
    """Static system, tool-schema, and padding blocks in deterministic cache order."""
    return build_cacheable_prefix(
        name="agent-system-tools",
        version=AGENT_PROMPT_VERSION,
        blocks=(
            {
                "kind": "system",
                "content": "\n".join(AGENT_SYSTEM_INSTRUCTIONS),
                "cache_checkpoint": True,
            },
            {
                "kind": "tool_schemas",
                "content": json.dumps(
                    AGENT_TOOL_SCHEMAS,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "cache_checkpoint": True,
            },
            {
                "kind": "cache_padding",
                "content": deterministic_cache_padding(
                    label="agent-system-tools",
                    min_tokens=AGENT_CACHE_MIN_TOKENS,
                ),
                "cache_checkpoint": True,
            },
        ),
    )


def converse_system_with_cache_point(
    prefix: CacheablePrefix,
    *,
    ttl: str | None = None,
) -> list[dict[str, Any]]:
    """Build Converse ``system`` blocks with a trailing ``cachePoint``."""
    cache_point: dict[str, Any] = {"type": "default"}
    if ttl is not None:
        cache_point["ttl"] = ttl
    return [
        {"text": prefix.stable_text()},
        {"cachePoint": cache_point},
    ]


def unavailable_cache_usage() -> dict[str, Any]:
    """Honest default when caching is not enabled for the request."""
    return {
        "cache_enabled": False,
        "cache_status": "not_configured",
        "cache_read_tokens": None,
        "cache_write_tokens": None,
    }


def derive_cache_status(
    *,
    cache_enabled: bool,
    cache_read_tokens: int | None,
    cache_write_tokens: int | None,
) -> str:
    if not cache_enabled:
        return "not_configured"
    read = int(cache_read_tokens or 0)
    write = int(cache_write_tokens or 0)
    if read > 0:
        return "hit"
    if write > 0:
        return "write"
    return "below_minimum"


def cache_usage_from_bedrock(
    usage: Mapping[str, Any] | None,
    *,
    cache_enabled: bool,
) -> dict[str, Any]:
    """Map Bedrock Converse usage fields into SupportRouter cache usage."""
    if not cache_enabled:
        return unavailable_cache_usage()
    raw = usage or {}
    read = raw.get("cacheReadInputTokens")
    write = raw.get("cacheWriteInputTokens")
    read_tokens = int(read) if read is not None else 0
    write_tokens = int(write) if write is not None else 0
    return {
        "cache_enabled": True,
        "cache_status": derive_cache_status(
            cache_enabled=True,
            cache_read_tokens=read_tokens,
            cache_write_tokens=write_tokens,
        ),
        "cache_read_tokens": read_tokens,
        "cache_write_tokens": write_tokens,
    }


def normalize_system_blocks(
    system: str | Sequence[Mapping[str, Any]],
    *,
    prompt_cache: bool,
) -> list[dict[str, Any]]:
    """Normalize system prompt into Converse blocks; optionally add cachePoint."""
    if isinstance(system, str):
        blocks: list[dict[str, Any]] = [{"text": system}]
    else:
        blocks = [dict(block) for block in system]
    if not prompt_cache:
        return blocks
    if any("cachePoint" in block for block in blocks):
        return blocks
    return [*blocks, dict(DEFAULT_CACHE_POINT)]
