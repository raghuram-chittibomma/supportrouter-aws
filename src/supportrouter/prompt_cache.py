"""Stable prompt-prefix checkpoints for future Bedrock prompt caching."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

AGENT_PROMPT_VERSION = "agent-prefix-v0.1"

AGENT_SYSTEM_INSTRUCTIONS = (
    "You are the VoltEdge Electronics support agent. All company, customer, "
    "order, product, and policy data is synthetic.",
    "Use deterministic routing and tool results as authoritative. Cite the "
    "provided synthetic knowledge documents for policy and product claims.",
    "Never claim a refund was executed when the workflow only prepared or "
    "approved a synthetic request. Escalate when required evidence is absent.",
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


def agent_cacheable_prefix() -> CacheablePrefix:
    """Static system and tool-schema blocks in deterministic cache order."""
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
        ),
    )


def unavailable_cache_usage() -> dict[str, Any]:
    """Honest default until a supported model/region returns cache metrics."""
    return {
        "cache_enabled": False,
        "cache_status": "not_configured",
        "cache_read_tokens": None,
        "cache_write_tokens": None,
    }
