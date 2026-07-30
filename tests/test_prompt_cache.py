"""Tests for stable prompt-cache checkpoints (#18 / #72)."""

from __future__ import annotations

import json

import pytest

from evals.loader import ALLOWED_TOOLS
from evals.prompt_cache import judge_cacheable_prefix
from supportrouter import tools_local
from supportrouter.bedrock_converse import converse_text
from supportrouter.bedrock_models import (
    estimate_cost_usd,
    estimate_uncached_equivalent_cost_usd,
)
from supportrouter.graph import run_agent
from supportrouter.prompt_cache import (
    AGENT_TOOL_SCHEMAS,
    agent_cacheable_prefix,
    build_cacheable_prefix,
    cache_usage_from_bedrock,
    converse_system_with_cache_point,
    derive_cache_status,
    unavailable_cache_usage,
)


def test_agent_prefix_is_stable_versioned_and_ordered():
    first = agent_cacheable_prefix()
    second = agent_cacheable_prefix()

    assert first == second
    assert first.name == "agent-system-tools"
    assert first.version == "agent-prefix-v0.3"
    assert len(first.sha256) == 64
    assert [block["kind"] for block in first.blocks] == [
        "system",
        "tool_schemas",
        "cache_padding",
    ]
    assert all(block["cache_checkpoint"] is True for block in first.blocks)
    with pytest.raises(TypeError):
        first.blocks[0]["content"] = "mutated"


def test_agent_tool_prefix_contains_only_fixed_tool_contracts():
    prefix = agent_cacheable_prefix()
    schemas = json.loads(prefix.blocks[1]["content"])

    assert schemas == list(AGENT_TOOL_SCHEMAS)
    assert [schema["name"] for schema in schemas] == [
        "get_order_status",
        "initiate_return",
        "issue_refund",
    ]
    assert all(callable(getattr(tools_local, schema["name"])) for schema in schemas)
    assert {schema["name"] for schema in schemas} == set(ALLOWED_TOOLS)
    serialized = json.dumps(prefix.as_dict())
    assert "session_id" not in serialized
    assert "correlation_id" not in serialized
    assert "VE-1001" not in serialized


def test_judge_prefix_is_stable_and_excludes_scenario_inputs():
    first = judge_cacheable_prefix()
    second = judge_cacheable_prefix()

    assert first == second
    assert first.name == "eval-judge-rubric"
    assert first.version == "v0.1-haiku-4.5"
    assert [block["kind"] for block in first.blocks] == [
        "judge_system",
        "judge_rubric",
        "cache_padding",
    ]
    rubric = json.loads(first.blocks[1]["content"])
    assert set(rubric["dimensions"]) == {
        "faithfulness",
        "helpfulness",
        "policy_adherence",
    }
    assert "Where is my order" not in json.dumps(first.as_dict())
    assert len(first.stable_text()) >= 20000


def test_cacheable_prefix_requires_stable_metadata_and_blocks():
    with pytest.raises(ValueError, match="requires name, version, and blocks"):
        build_cacheable_prefix(name="", version="v1", blocks=({"kind": "x"},))
    with pytest.raises(ValueError, match="requires name, version, and blocks"):
        build_cacheable_prefix(name="x", version="", blocks=({"kind": "x"},))
    with pytest.raises(ValueError, match="requires name, version, and blocks"):
        build_cacheable_prefix(name="x", version="v1", blocks=())


def test_local_cache_usage_is_explicitly_unavailable():
    assert unavailable_cache_usage() == {
        "cache_enabled": False,
        "cache_status": "not_configured",
        "cache_read_tokens": None,
        "cache_write_tokens": None,
    }

    result = run_agent("Where is my order VE-1001?")
    assert result["usage"]["cache_enabled"] is False
    assert result["usage"]["cache_status"] == "not_configured"
    assert result["usage"]["cache_read_tokens"] is None
    assert result["usage"]["cache_write_tokens"] is None
    assert result["prompt_cache"]["prefix_name"] == "agent-system-tools"
    assert result["prompt_cache"]["prefix_version"] == "agent-prefix-v0.3"
    assert len(result["prompt_cache"]["prefix_sha256"]) == 64


def test_converse_system_includes_cache_point():
    system = converse_system_with_cache_point(agent_cacheable_prefix())
    assert system[0]["text"]
    assert system[1] == {"cachePoint": {"type": "default"}}


def test_derive_cache_status_and_bedrock_mapping():
    assert derive_cache_status(
        cache_enabled=True, cache_read_tokens=100, cache_write_tokens=0
    ) == "hit"
    assert derive_cache_status(
        cache_enabled=True, cache_read_tokens=0, cache_write_tokens=50
    ) == "write"
    assert derive_cache_status(
        cache_enabled=True, cache_read_tokens=0, cache_write_tokens=0
    ) == "below_minimum"
    mapped = cache_usage_from_bedrock(
        {"cacheReadInputTokens": 10, "cacheWriteInputTokens": 0},
        cache_enabled=True,
    )
    assert mapped == {
        "cache_enabled": True,
        "cache_status": "hit",
        "cache_read_tokens": 10,
        "cache_write_tokens": 0,
    }


def test_converse_text_maps_cache_tokens_when_enabled():
    class FakeClient:
        def converse(self, **kwargs):
            assert any("cachePoint" in block for block in kwargs["system"])
            return {
                "output": {"message": {"content": [{"text": "ok"}]}},
                "usage": {
                    "inputTokens": 20,
                    "outputTokens": 5,
                    "totalTokens": 25,
                    "cacheReadInputTokens": 4000,
                    "cacheWriteInputTokens": 0,
                },
                "stopReason": "end_turn",
            }

    result = converse_text(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        system="stable",
        user="q",
        client=FakeClient(),
        prompt_cache=True,
    )
    assert result["usage"]["cache_enabled"] is True
    assert result["usage"]["cache_status"] == "hit"
    assert result["usage"]["cache_read_tokens"] == 4000
    assert result["usage"]["cache_write_tokens"] == 0


def test_estimate_cost_prices_cache_read_cheaper_than_uncached():
    model = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_tokens": 4000,
        "cache_write_tokens": 0,
    }
    measured = estimate_cost_usd(model, usage)
    uncached = estimate_uncached_equivalent_cost_usd(model, usage)
    assert measured is not None and uncached is not None
    assert measured < uncached
