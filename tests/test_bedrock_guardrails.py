"""Tests for Bedrock ApplyGuardrail adapter and aws-mode wiring (#70)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from supportrouter.bedrock_guardrails import apply_guardrail
from supportrouter.graph import run_agent
from supportrouter.guardrails import assess
from supportrouter_infra.api_stack import ApiStack


def test_assess_local_mode_stays_deterministic():
    assessment = assess(
        "Email me at synthetic.customer@example.test",
        stage="input",
        runtime_mode="local",
    )
    assert assessment.provider == "local_deterministic"
    assert assessment.action == "blocked"
    assert "pii_email" in assessment.categories


def test_apply_guardrail_allow_and_block(monkeypatch):
    monkeypatch.setenv("SUPPORTROUTER_GUARDRAIL_ID", "gr-test")
    monkeypatch.setenv("SUPPORTROUTER_GUARDRAIL_VERSION", "1")

    class FakeClient:
        def __init__(self, action: str, assessments: list):
            self._action = action
            self._assessments = assessments
            self.calls = []

        def apply_guardrail(self, **kwargs):
            self.calls.append(kwargs)
            return {"action": self._action, "assessments": self._assessments}

    allow_client = FakeClient("NONE", [])
    allowed = apply_guardrail(
        "Where is order VE-1001?",
        stage="input",
        client=allow_client,
    )
    assert allowed.action == "allowed"
    assert allowed.provider == "bedrock"
    assert allowed.guardrail_identifier == "gr-test"
    assert allow_client.calls[0]["source"] == "INPUT"

    block_client = FakeClient(
        "GUARDRAIL_INTERVENED",
        [
            {
                "topicPolicy": {
                    "topics": [
                        {
                            "name": "FinancialAdvice",
                            "action": "BLOCKED",
                            "detected": True,
                        }
                    ]
                }
            }
        ],
    )
    blocked = apply_guardrail(
        "Should I buy this stock?",
        stage="output",
        client=block_client,
    )
    assert blocked.action == "blocked"
    assert "topic:financialadvice" in blocked.categories
    assert block_client.calls[0]["source"] == "OUTPUT"


def test_aws_mode_missing_guardrail_env_fails_closed(monkeypatch):
    monkeypatch.delenv("SUPPORTROUTER_GUARDRAIL_ID", raising=False)
    monkeypatch.delenv("SUPPORTROUTER_GUARDRAIL_VERSION", raising=False)
    assessment = assess("hello", stage="input", runtime_mode="aws")
    assert assessment.provider == "bedrock"
    assert assessment.action == "blocked"
    assert "guardrail_misconfigured" in assessment.categories


def test_aws_mode_run_agent_uses_bedrock_guardrail_metadata(monkeypatch):
    monkeypatch.setenv("SUPPORTROUTER_GUARDRAIL_ID", "gr-live")
    monkeypatch.setenv("SUPPORTROUTER_GUARDRAIL_VERSION", "3")

    class FakeClient:
        def apply_guardrail(self, **kwargs):
            return {"action": "NONE", "assessments": []}

    monkeypatch.setattr(
        "supportrouter.bedrock_guardrails._client",
        lambda client=None: FakeClient(),
    )
    monkeypatch.setattr(
        "supportrouter.graph.converse_text",
        lambda **kwargs: {
            "text": "Order VE-1001 is shipped.",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            },
            "stop_reason": "end_turn",
            "model_id": kwargs["model_id"],
        },
    )
    monkeypatch.setenv(
        "GET_ORDER_STATUS_FUNCTION_NAME", "supportrouter-get-order-status"
    )

    class FakeLambda:
        def invoke(self, **kwargs):
            import json

            body = json.dumps(
                {
                    "ok": True,
                    "order_id": "VE-1001",
                    "status": "shipped",
                    "tracking_number": "VETRACK-90821",
                    "items": [],
                }
            ).encode("utf-8")

            class _Payload:
                def read(self_inner):
                    return body

            return {"Payload": _Payload()}

    monkeypatch.setattr(
        "supportrouter.tools_aws._client", lambda client=None: FakeLambda()
    )

    result = run_agent("Where is my order #VE-1001?", runtime_mode="aws")
    assert result["status"] == "resolved"
    assert result["guardrail"]["provider"] == "bedrock"
    assert result["guardrail"]["identifier"] == "gr-live"
    assert result["guardrail"]["version"] == "3"
    assert result["guardrail"]["input"]["provider"] == "bedrock"
    assert result["guardrail"]["output"]["provider"] == "bedrock"


def test_api_stack_wires_apply_guardrail_when_ids_provided() -> None:
    app = cdk.App()
    stack = ApiStack(
        app,
        "ApiWithGuardrail",
        env=cdk.Environment(account="111111111111", region="us-east-1"),
        guardrail_id="3hkym9cgw048",
        guardrail_version="1",
    )
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "SUPPORTROUTER_GUARDRAIL_ID": "3hkym9cgw048",
                        "SUPPORTROUTER_GUARDRAIL_VERSION": "1",
                    }
                )
            }
        },
    )
    policies = [
        resource["Properties"]["PolicyDocument"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
    ]
    serialized = str(policies)
    assert "bedrock:ApplyGuardrail" in serialized
    assert "guardrail/3hkym9cgw048" in serialized
