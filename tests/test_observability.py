"""Tests for local structured observability (#19)."""

from __future__ import annotations

import json
import logging

from supportrouter.graph import run_agent
from supportrouter.observability import (
    AGENT_STEPS,
    InMemoryTraceSink,
    LoggingTraceSink,
    clear_traces,
    list_traces,
    set_trace_sink,
)
from supportrouter.sessions import clear_sessions, decide_hitl, save_session


def setup_function():
    clear_sessions()
    set_trace_sink(InMemoryTraceSink())
    clear_traces()


def test_conversation_emits_correlated_step_traces():
    result = run_agent("Where is my order #VE-1001?", correlation_id="corr-order-1")

    events = list_traces()
    assert result["correlation_id"] == "corr-order-1"
    assert result["session_id"]
    assert events[0]["event_type"] == "conversation.start"
    assert events[-1]["event_type"] == "conversation.end"

    step_names = [event["step"] for event in events if event["event_type"] == "agent.step"]
    assert step_names == [
        "validate",
        "classify",
        "route",
        "tools",
        "draft",
        "confidence",
        "hitl",
    ]
    for event in events:
        assert event["correlation_id"] == "corr-order-1"
        assert event["session_id"] == result["session_id"]
        assert event["plane"] == "runtime"


def test_token_and_cost_fields_are_explicitly_unmeasured():
    result = run_agent(
        "What is the VoltEdge policy for unused items still in original packaging within 30 days?"
    )

    assert result["usage"] == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cache_enabled": False,
    }
    assert result["cost_usd"] is None
    assert result["cost_status"] == "not_measured"

    for event in list_traces():
        assert event["cost_usd"] is None
        assert event["cost_status"] == "not_measured"
        assert event["usage"]["input_tokens"] is None
        assert event["usage"]["output_tokens"] is None
        assert event["usage"]["total_tokens"] is None
        assert event["usage"]["cache_enabled"] is False


def test_hitl_decision_emits_trace_event():
    result = save_session(run_agent("I want a refund for order VE-1003"))
    clear_traces()

    updated = decide_hitl(result["session_id"], "approve", note="ok")
    events = list_traces()

    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "hitl.decision"
    assert event["session_id"] == result["session_id"]
    assert event["correlation_id"] == result["correlation_id"]
    assert event["attributes"]["decision"] == "approve"
    assert event["attributes"]["approval_id"] == result["approval_id"]
    assert event["status"] == updated["status"]
    assert event["cost_status"] == "not_measured"


def test_logging_sink_emits_cloudwatch_compatible_json(caplog):
    sink = LoggingTraceSink()
    set_trace_sink(sink)

    with caplog.at_level(logging.INFO, logger="supportrouter.observability"):
        run_agent("Where is my order #VE-1001?", correlation_id="corr-log-1")

    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "supportrouter.observability"
    ]
    assert payloads
    assert payloads[0]["event_type"] == "conversation.start"
    assert payloads[0]["correlation_id"] == "corr-log-1"
    assert payloads[-1]["event_type"] == "conversation.end"
    assert {"schema_version", "usage", "cost_usd", "cost_status", "plane"} <= set(
        payloads[0]
    )


def test_agent_step_catalog_covers_runtime_nodes():
    assert AGENT_STEPS == (
        "validate",
        "classify",
        "route",
        "retrieve",
        "tools",
        "draft",
        "confidence",
        "hitl",
    )
