"""Tests for AgentCore payload adapter (ADR-024)."""

from __future__ import annotations

from supportrouter.agentcore_adapter import (
    AgentCoreBadRequest,
    handle_agentcore_payload,
    parse_agentcore_payload,
)


def test_parse_accepts_message_or_prompt():
    assert parse_agentcore_payload({"message": "Where is order ORD-1?"})[0].startswith(
        "Where is"
    )
    assert parse_agentcore_payload({"prompt": "Hello"})[0] == "Hello"


def test_parse_rejects_empty_payload():
    try:
        parse_agentcore_payload({})
        raise AssertionError("expected AgentCoreBadRequest")
    except AgentCoreBadRequest:
        pass


def test_handle_agentcore_payload_local_happy_path():
    result = handle_agentcore_payload(
        {"message": "What is your return policy?", "runtime_mode": "local"}
    )
    assert "error" not in result
    assert result.get("answer")
    assert result.get("session_id")
    assert result.get("status") in {
        "resolved",
        "escalated",
        "pending_approval",
        "rejected",
    }
