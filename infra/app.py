"""SupportRouter CDK app — dormancy-safe defaults (ADR-007, ADR-008)."""

from __future__ import annotations

import aws_cdk as cdk

from supportrouter_infra.api_stack import ApiStack
from supportrouter_infra.cost_guardrails_stack import CostGuardrailsStack
from supportrouter_infra.eval_schedule_stack import EvalScheduleStack
from supportrouter_infra.guardrails_stack import GuardrailsStack
from supportrouter_infra.knowledge_base_stack import KnowledgeBaseStack
from supportrouter_infra.observability_stack import ObservabilityStack
from supportrouter_infra.tools_stack import ToolsStack


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


app = cdk.App()

enable_reeval = _as_bool(app.node.try_get_context("enable_reeval_schedule"), default=False)

env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region=app.node.try_get_context("region") or "us-east-1",
)

CostGuardrailsStack(app, "SupportRouter-CostGuardrails", env=env)
KnowledgeBaseStack(app, "SupportRouter-KnowledgeBase", env=env)
GuardrailsStack(app, "SupportRouter-Guardrails", env=env)
ToolsStack(app, "SupportRouter-Tools", env=env)
ApiStack(app, "SupportRouter-Api", env=env)
ObservabilityStack(app, "SupportRouter-Observability", env=env)
EvalScheduleStack(
    app,
    "SupportRouter-EvalSchedule",
    enable_reeval_schedule=enable_reeval,
    env=env,
)

app.synth()
