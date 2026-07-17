"""Tests for stable prompt-cache checkpoints (#18)."""

from __future__ import annotations

import json

import pytest

from evals.loader import ALLOWED_TOOLS
from evals.prompt_cache import judge_cacheable_prefix
from supportrouter import tools_local
from supportrouter.graph import run_agent
from supportrouter.prompt_cache import (
    AGENT_TOOL_SCHEMAS,
    agent_cacheable_prefix,
    build_cacheable_prefix,
    unavailable_cache_usage,
)


def test_agent_prefix_is_stable_versioned_and_ordered():
    first = agent_cacheable_prefix()
    second = agent_cacheable_prefix()

    assert first == second
    assert first.name == "agent-system-tools"
    assert first.version == "agent-prefix-v0.1"
    assert len(first.sha256) == 64
    assert [block["kind"] for block in first.blocks] == [
        "system",
        "tool_schemas",
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
    assert first.version == "v0.1-rubric-draft"
    assert [block["kind"] for block in first.blocks] == [
        "judge_system",
        "judge_rubric",
    ]
    rubric = json.loads(first.blocks[1]["content"])
    assert set(rubric["dimensions"]) == {
        "faithfulness",
        "helpfulness",
        "policy_adherence",
    }
    assert "Where is my order" not in json.dumps(first.as_dict())


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
    assert result["prompt_cache"]["prefix_version"] == "agent-prefix-v0.1"
    assert len(result["prompt_cache"]["prefix_sha256"]) == 64
