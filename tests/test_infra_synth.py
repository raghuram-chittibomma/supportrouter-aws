"""CDK synthesis guardrails for dormancy-safe design (ADR-007/008)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
sys.path.insert(0, str(INFRA))

from supportrouter_infra.cost_guardrails_stack import CostGuardrailsStack  # noqa: E402
from supportrouter_infra.eval_schedule_stack import EvalScheduleStack  # noqa: E402
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
