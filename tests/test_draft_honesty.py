"""Tests for refund/return draft execution honesty (#73)."""

from __future__ import annotations

import json

from supportrouter.draft_honesty import (
    enforce_execution_honesty,
    overclaims_execution,
)
from supportrouter.graph import run_agent


def test_overclaims_execution_detects_bank_timeline():
    assert overclaims_execution(
        "Your refund has been processed. Allow 3-5 business days."
    )
    assert not overclaims_execution(
        "Refund of $89.99 prepared (synthetic); no payment was executed"
    )


def test_overclaims_skips_honest_negations_and_policy_windows():
    assert not overclaims_execution(
        "No confirmation email will be sent until a supervisor approves."
    )
    assert not overclaims_execution(
        "Eligible returns are accepted within 30 business days of delivery."
    )
    assert not overclaims_execution(
        "Prepared only; if later executed, funds would use the original payment method."
    )


def test_enforce_does_not_rewrite_honest_tool_aligned_draft():
    tool_calls = [
        {
            "name": "issue_refund",
            "args": {"order_id": "VE-1002"},
            "result": {
                "ok": True,
                "execution_status": "not_executed",
                "message": "Refund of $89.99 prepared (synthetic); no payment was executed",
            },
        }
    ]
    text = (
        "I prepared a synthetic refund of $89.99 for VE-1002. "
        "No payment was executed. No confirmation email will be sent in this demo."
    )
    answer, rewritten = enforce_execution_honesty(text, tool_calls)
    assert rewritten is False
    assert answer == text


def test_enforce_rewrites_overclaim_to_tool_message():
    tool_calls = [
        {
            "name": "issue_refund",
            "args": {"order_id": "VE-1002"},
            "result": {
                "ok": True,
                "execution_status": "not_executed",
                "message": "Refund of $89.99 prepared (synthetic); no payment was executed",
            },
        }
    ]
    answer, rewritten = enforce_execution_honesty(
        "Your refund has been processed and funds will appear in 3-5 business days.",
        tool_calls,
    )
    assert rewritten is True
    assert "prepared" in answer.lower()
    assert "not executed" in answer.lower() or "no payment was executed" in answer.lower()
    assert not overclaims_execution(answer)


def test_local_refund_draft_stays_honest():
    result = run_agent("Please refund order #VE-1002", runtime_mode="local")
    assert result["status"] == "resolved"
    answer = result.get("answer") or ""
    assert "prepared" in answer.lower() or "no payment was executed" in answer.lower()
    assert not overclaims_execution(answer)


def test_aws_draft_honesty_rewrite_when_model_overclaims(monkeypatch):
    monkeypatch.setenv("SUPPORTROUTER_GUARDRAIL_ID", "gr-test")
    monkeypatch.setenv("SUPPORTROUTER_GUARDRAIL_VERSION", "1")

    class FakeGuardrailClient:
        def apply_guardrail(self, **kwargs):
            return {"action": "NONE", "assessments": []}

    monkeypatch.setattr(
        "supportrouter.bedrock_guardrails._client",
        lambda client=None: FakeGuardrailClient(),
    )
    class FakeLambda:
        def invoke(self, **kwargs):
            body = json.dumps(
                {
                    "ok": True,
                    "order_id": "VE-1002",
                    "refund_id": "REFUND-VE-1002",
                    "amount_usd": 89.99,
                    "requires_approval": False,
                    "status": "prepared",
                    "execution_status": "not_executed",
                    "message": (
                        "Refund of $89.99 prepared (synthetic); "
                        "no payment was executed"
                    ),
                }
            ).encode("utf-8")

            class _Payload:
                def read(self_inner):
                    return body

            return {"Payload": _Payload()}

    monkeypatch.setenv(
        "GET_ORDER_STATUS_FUNCTION_NAME", "supportrouter-get-order-status"
    )
    monkeypatch.setenv(
        "ISSUE_REFUND_FUNCTION_NAME", "supportrouter-issue-refund"
    )
    monkeypatch.setattr(
        "supportrouter.tools_aws._client", lambda client=None: FakeLambda()
    )
    monkeypatch.setattr(
        "supportrouter.graph.converse_text",
        lambda **kwargs: {
            "text": (
                "Your refund has been processed. Please allow 3-5 business days "
                "for funds to appear in your original payment method. "
                "We will send a confirmation email."
            ),
            "usage": {
                "input_tokens": 40,
                "output_tokens": 30,
                "total_tokens": 70,
            },
            "stop_reason": "end_turn",
            "model_id": kwargs["model_id"],
        },
    )

    result = run_agent("Please refund order #VE-1002", runtime_mode="aws")
    assert result["status"] == "resolved"
    answer = result.get("answer") or ""
    assert "draft:honesty_rewrite" in result["notes"]
    assert "prepared" in answer.lower()
    assert "no payment was executed" in answer.lower()
    assert not overclaims_execution(answer)
