"""Tests for local vs AWS runtime mode switch (#66 / ADR-018)."""

from __future__ import annotations

import json

import pytest

from supportrouter.graph import run_agent
from supportrouter.runtime_mode import normalize_runtime_mode
from supportrouter.tools_aws import invoke_tool


def test_normalize_runtime_mode_defaults_local(monkeypatch):
    monkeypatch.delenv("SUPPORTROUTER_RUNTIME_MODE", raising=False)
    assert normalize_runtime_mode(None) == "local"
    assert normalize_runtime_mode("AWS") == "aws"
    with pytest.raises(ValueError):
        normalize_runtime_mode("hybrid")


def test_local_mode_keeps_stub_draft_and_unmeasured_cost():
    result = run_agent("Where is my order #VE-1001?", runtime_mode="local")
    assert result["runtime_mode"] == "local"
    assert result["status"] == "resolved"
    assert "local stub" in (result.get("answer") or "")
    assert result["cost_status"] == "not_measured"
    assert any(note.startswith("draft:local") for note in result["notes"])


def test_aws_mode_uses_converse_and_lambda_tools(monkeypatch):
    class FakeLambda:
        def invoke(self, **kwargs):
            payload = json.loads(kwargs["Payload"].decode("utf-8"))
            assert payload["order_id"] == "VE-1001"
            body = json.dumps(
                {
                    "ok": True,
                    "order_id": "VE-1001",
                    "status": "shipped",
                    "tracking_number": "1Z999",
                    "items": [],
                }
            ).encode("utf-8")

            class _Payload:
                def read(self_inner):
                    return body

            return {"Payload": _Payload()}

    monkeypatch.setenv(
        "GET_ORDER_STATUS_FUNCTION_NAME", "supportrouter-get-order-status"
    )
    monkeypatch.setattr(
        "supportrouter.tools_aws._client", lambda client=None: FakeLambda()
    )
    monkeypatch.setattr(
        "supportrouter.graph.converse_text",
        lambda **kwargs: {
            "text": "Order VE-1001 is shipped. Tracking 1Z999.",
            "usage": {
                "input_tokens": 40,
                "output_tokens": 20,
                "total_tokens": 60,
            },
            "stop_reason": "end_turn",
            "model_id": kwargs["model_id"],
        },
    )

    result = run_agent("Where is my order #VE-1001?", runtime_mode="aws")
    assert result["runtime_mode"] == "aws"
    assert result["retrieve_provider"] == "skipped"
    assert result["status"] == "resolved"
    assert "1Z999" in (result.get("answer") or "")
    assert "local stub" not in (result.get("answer") or "")
    assert result["cost_status"] == "measured"
    assert result["cost_usd"] is not None
    assert any(note.startswith("draft:aws:") for note in result["notes"])
    assert any(note.startswith("tools:aws:") for note in result["notes"])


def test_aws_faq_reports_local_retrieve_fallback(monkeypatch):
    monkeypatch.delenv("SUPPORTROUTER_KB_ID", raising=False)
    monkeypatch.setattr(
        "supportrouter.graph.converse_text",
        lambda **kwargs: {
            "text": "Unused items in original packaging may be returned within 30 days.",
            "usage": {
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
            },
            "stop_reason": "end_turn",
            "model_id": kwargs["model_id"],
        },
    )
    result = run_agent(
        "What is the VoltEdge policy for unused items still in original packaging within 30 days?",
        runtime_mode="aws",
    )
    assert result["task_type"] == "faq_policy"
    assert result["runtime_mode"] == "aws"
    assert result["retrieve_provider"] == "local_fallback"
    assert any(
        note.startswith("retrieve:aws_fallback_local:") for note in result["notes"]
    )


def test_invoke_tool_requires_function_env(monkeypatch):
    monkeypatch.delenv("GET_ORDER_STATUS_FUNCTION_NAME", raising=False)
    with pytest.raises(RuntimeError, match="GET_ORDER_STATUS_FUNCTION_NAME"):
        invoke_tool("get_order_status", order_id="VE-1001")
