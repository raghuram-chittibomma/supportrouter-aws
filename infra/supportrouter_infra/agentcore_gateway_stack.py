"""AgentCore Gateway exposing SupportRouter tool Lambdas as MCP tools (ADR-024 / #93).

Opt-in via CDK context ``enable_agentcore_gateway=true``. Does not change the
LangGraph direct ``lambda:InvokeFunction`` tool path.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_bedrockagentcore as agentcore,
    aws_lambda as lambda_,
)
from constructs import Construct

from supportrouter_infra.constants import PROJECT_NAME

GATEWAY_NAME = "supportrouter-tools-gw"

# MCP discovery names are ``{target}___{tool}`` (triple underscore).
TOOL_TARGETS: tuple[tuple[str, str, str], ...] = (
    (
        "order-status",
        "get_order_status",
        "Look up a synthetic VoltEdge order status by order_id (VE-####).",
    ),
    (
        "initiate-return",
        "initiate_return",
        "Start a synthetic return (RMA) for an eligible VoltEdge order_id.",
    ),
    (
        "issue-refund",
        "issue_refund",
        "Record a synthetic refund request for an eligible VoltEdge order_id.",
    ),
)


def _order_id_tool(name: str, description: str) -> agentcore.ToolDefinition:
    return agentcore.ToolDefinition(
        name=name,
        description=description,
        input_schema=agentcore.SchemaDefinition(
            type=agentcore.SchemaDefinitionType.OBJECT,
            properties={
                "order_id": agentcore.SchemaDefinition(
                    type=agentcore.SchemaDefinitionType.STRING,
                    description="Synthetic VoltEdge order id matching VE-####",
                )
            },
            required=["order_id"],
        ),
    )


class AgentCoreGatewayStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        get_order_status_function: lambda_.IFunction,
        initiate_return_function: lambda_.IFunction,
        issue_refund_function: lambda_.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cdk.Tags.of(self).add("Project", PROJECT_NAME)

        gateway = agentcore.Gateway(
            self,
            "ToolsGateway",
            gateway_name=GATEWAY_NAME,
            description="MCP façade over SupportRouter order/return/refund Lambdas",
            # SigV4 for operators/demos (ADR-024); avoid default Cognito pool.
            authorizer_configuration=agentcore.GatewayAuthorizer.using_aws_iam(),
            # Omit semantic search to avoid tool-index monthly fees when idle.
            protocol_configuration=agentcore.McpProtocolConfiguration(),
        )

        lambdas = {
            "get_order_status": get_order_status_function,
            "initiate_return": initiate_return_function,
            "issue_refund": issue_refund_function,
        }
        for target_name, tool_name, tool_description in TOOL_TARGETS:
            gateway.add_lambda_target(
                f"Target{tool_name.title().replace('_', '')}",
                gateway_target_name=target_name,
                description=f"Lambda target for {tool_name}",
                lambda_function=lambdas[tool_name],
                tool_schema=agentcore.ToolSchema.from_inline(
                    [_order_id_tool(tool_name, tool_description)]
                ),
            )

        self.gateway = gateway
        cdk.CfnOutput(self, "GatewayId", value=gateway.gateway_id)
        cdk.CfnOutput(self, "GatewayArn", value=gateway.gateway_arn)
        cdk.CfnOutput(self, "GatewayUrl", value=gateway.gateway_url)
        cdk.CfnOutput(self, "GatewayName", value=GATEWAY_NAME)
        cdk.CfnOutput(
            self,
            "McpToolNames",
            value=",".join(
                f"{target}___{tool}" for target, tool, _ in TOOL_TARGETS
            ),
            description="Discovered MCP tool names (target___tool)",
        )
