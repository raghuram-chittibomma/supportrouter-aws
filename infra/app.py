"""SupportRouter CDK app — dormancy-safe defaults (ADR-007, ADR-008)."""

from __future__ import annotations

import aws_cdk as cdk

from supportrouter_infra.agentcore_gateway_stack import AgentCoreGatewayStack
from supportrouter_infra.agentcore_stack import AgentCoreStack
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
enable_agentcore = _as_bool(app.node.try_get_context("enable_agentcore"), default=False)
enable_agentcore_gateway = _as_bool(
    app.node.try_get_context("enable_agentcore_gateway"), default=False
)

env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region=app.node.try_get_context("region") or "us-east-1",
)

CostGuardrailsStack(app, "SupportRouter-CostGuardrails", env=env)
kb_stack = KnowledgeBaseStack(app, "SupportRouter-KnowledgeBase", env=env)
guardrails_stack = GuardrailsStack(app, "SupportRouter-Guardrails", env=env)
tools_stack = ToolsStack(app, "SupportRouter-Tools", env=env)
api_stack = ApiStack(
    app,
    "SupportRouter-Api",
    env=env,
    knowledge_base_id=kb_stack.knowledge_base_id,
    guardrail_id=guardrails_stack.guardrail_id,
    guardrail_version=guardrails_stack.guardrail_version,
    get_order_status_function=tools_stack.get_order_status_function,
    initiate_return_function=tools_stack.initiate_return_function,
    issue_refund_function=tools_stack.issue_refund_function,
)
# Dual-run stretch host (ADR-024). Opt-in: -c enable_agentcore=true
if enable_agentcore:
    AgentCoreStack(
        app,
        "SupportRouter-AgentCore",
        env=env,
        sessions_table=api_stack.sessions_table,
        approvals_table=api_stack.approvals_table,
        routing_table=api_stack.routing_table,
        knowledge_base_id=kb_stack.knowledge_base_id,
        guardrail_id=guardrails_stack.guardrail_id,
        guardrail_version=guardrails_stack.guardrail_version,
        get_order_status_function=tools_stack.get_order_status_function,
        initiate_return_function=tools_stack.initiate_return_function,
        issue_refund_function=tools_stack.issue_refund_function,
    )
# Optional MCP façade over tool Lambdas (ADR-024 / #93).
if enable_agentcore_gateway:
    AgentCoreGatewayStack(
        app,
        "SupportRouter-AgentCoreGateway",
        env=env,
        get_order_status_function=tools_stack.get_order_status_function,
        initiate_return_function=tools_stack.initiate_return_function,
        issue_refund_function=tools_stack.issue_refund_function,
    )
ObservabilityStack(app, "SupportRouter-Observability", env=env)
EvalScheduleStack(
    app,
    "SupportRouter-EvalSchedule",
    enable_reeval_schedule=enable_reeval,
    env=env,
)

app.synth()
