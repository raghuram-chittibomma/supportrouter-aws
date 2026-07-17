"""CDK synthesis guardrails for dormancy-safe design (ADR-007/008)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template
from supportrouter.guardrails import LOCAL_POLICY_CAPABILITIES

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
sys.path.insert(0, str(INFRA))

from supportrouter_infra.cost_guardrails_stack import CostGuardrailsStack  # noqa: E402
from supportrouter_infra.eval_schedule_stack import EvalScheduleStack  # noqa: E402
from supportrouter_infra.guardrails_stack import (  # noqa: E402
    BEDROCK_GUARDRAIL_POLICY_SHA256,
    BEDROCK_GUARDRAIL_POLICY_SPEC,
    GuardrailsStack,
)
from supportrouter_infra.knowledge_base_stack import KnowledgeBaseStack  # noqa: E402
from supportrouter_infra.observability_stack import ObservabilityStack  # noqa: E402


@pytest.fixture
def env() -> cdk.Environment:
    return cdk.Environment(account="111111111111", region="us-east-1")


def test_cost_budget_twenty_dollars(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = CostGuardrailsStack(app, "Cost", env=env)
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": {
                "BudgetLimit": {"Amount": 20, "Unit": "USD"},
                "BudgetType": "COST",
                "TimeUnit": "MONTHLY",
                "CostFilters": {
                    "TagKeyValue": ["user:Project$supportrouter"],
                },
            }
        },
    )


def test_knowledge_base_uses_s3_vectors_not_opensearch(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = KnowledgeBaseStack(app, "Kb", env=env)
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::Bedrock::KnowledgeBase",
        {
            "StorageConfiguration": {"Type": "S3_VECTORS"},
        },
    )
    raw = json.dumps(template.to_json())
    assert "AWS::OpenSearchServerless::Collection" not in raw
    assert "OPENSEARCH_SERVERLESS" not in raw
    assert "AWS::EC2::VPC" not in raw
    assert "AWS::EC2::NatGateway" not in raw
    assert '"Type": "S3_VECTORS"' in raw or '"Type":"S3_VECTORS"' in raw


def test_eval_schedule_rule_absent_when_disabled(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = EvalScheduleStack(app, "EvalOff", enable_reeval_schedule=False, env=env)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::Events::Rule", 0)
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)


def test_eval_schedule_rule_present_when_enabled(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = EvalScheduleStack(app, "EvalOn", enable_reeval_schedule=True, env=env)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::Events::Rule", 1)
    template.has_resource_properties(
        "AWS::Events::Rule",
        {"State": "ENABLED"},
    )


def test_observability_caps(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = ObservabilityStack(app, "Obs", env=env)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::CloudWatch::Dashboard", 3)
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {"RetentionInDays": 14},
    )
    raw = json.dumps(template.to_json())
    assert "AWS::EC2::VPC" not in raw


def test_bedrock_guardrail_covers_input_output_and_version(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = GuardrailsStack(app, "Guardrails", env=env)
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::Bedrock::Guardrail", 1)
    template.resource_count_is("AWS::Bedrock::GuardrailVersion", 1)
    template.has_resource_properties(
        "AWS::Bedrock::Guardrail",
        {
            "Name": "supportrouter-safety",
            "BlockedInputMessaging": Match.string_like_regexp(
                "Remove sensitive details"
            ),
            "SensitiveInformationPolicyConfig": Match.object_like(
                {
                    "PiiEntitiesConfig": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "BLOCK",
                                    "InputAction": "BLOCK",
                                    "InputEnabled": True,
                                    "OutputAction": "BLOCK",
                                    "OutputEnabled": True,
                                }
                            )
                        ]
                    )
                }
            ),
        },
    )
    raw = json.dumps(template.to_json())
    assert "DangerousAssistance" in raw
    assert "FinancialAdvice" in raw
    assert "CREDIT_DEBIT_CARD_NUMBER" in raw
    assert "US_SOCIAL_SECURITY_NUMBER" in raw
    assert BEDROCK_GUARDRAIL_POLICY_SHA256 in raw
    assert {topic["name"] for topic in BEDROCK_GUARDRAIL_POLICY_SPEC["topics"]} == {
        "DangerousAssistance",
        "FinancialAdvice",
    }
    assert LOCAL_POLICY_CAPABILITIES == {
        "pii",
        "dangerous_assistance",
        "self_harm_assistance",
        "financial_advice",
    }
    assert {
        "EMAIL",
        "PHONE",
        "CREDIT_DEBIT_CARD_NUMBER",
        "US_SOCIAL_SECURITY_NUMBER",
    }.issubset(BEDROCK_GUARDRAIL_POLICY_SPEC["pii_entity_types"])
    assert '"InputEnabled": true' in raw
    assert '"OutputEnabled": true' in raw
