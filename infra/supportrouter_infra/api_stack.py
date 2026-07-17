"""HTTP API edge that fronts the SupportRouter chat Lambda (ADR-014).

Dormancy-safe: HTTP API (not REST) with pay-per-request pricing, throttled
default stage, a 14-day log group, and a least-privilege role that can only write
its own logs. The chat Lambda runs the local-stub agent, so no Bedrock, DynamoDB,
or other data-plane permissions are granted here.
"""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct

from supportrouter_infra.constants import PROJECT_NAME

SRC_ASSET = str(Path(__file__).resolve().parents[2] / "src")
CHAT_ROUTE = "/chat"

# Throttle caps keep a dormant demo from accruing runaway request cost.
THROTTLE_RATE_LIMIT = 10
THROTTLE_BURST_LIMIT = 20


class ApiStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cdk.Tags.of(self).add("Project", PROJECT_NAME)

        function_name = f"{PROJECT_NAME}-chat"
        log_group = logs.LogGroup(
            self,
            "ChatLogs",
            log_group_name=f"/aws/lambda/{function_name}",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        role = iam.Role(
            self,
            "ChatRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description=f"Least-privilege execution role for {function_name}",
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="WriteOwnLogs",
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[log_group.log_group_arn, f"{log_group.log_group_arn}:*"],
            )
        )

        chat_function = lambda_.Function(
            self,
            "ChatFunction",
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            code=lambda_.Code.from_asset(
                SRC_ASSET,
                exclude=[
                    "**/__pycache__",
                    "*.pyc",
                    # UI needs gradio, which the chat edge does not import.
                    "supportrouter/ui.py",
                ],
            ),
            handler="supportrouter.api.handler",
            role=role,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            log_group=log_group,
        )

        http_api = apigwv2.HttpApi(
            self,
            "ChatHttpApi",
            api_name=f"{PROJECT_NAME}-chat-api",
            description="SupportRouter synthetic chat edge (ADR-014)",
            create_default_stage=False,
        )
        http_api.add_routes(
            path=CHAT_ROUTE,
            methods=[apigwv2.HttpMethod.POST],
            integration=integrations.HttpLambdaIntegration(
                "ChatIntegration",
                handler=chat_function,
            ),
        )
        stage = apigwv2.HttpStage(
            self,
            "ChatStage",
            http_api=http_api,
            stage_name="$default",
            auto_deploy=True,
            throttle=apigwv2.ThrottleSettings(
                rate_limit=THROTTLE_RATE_LIMIT,
                burst_limit=THROTTLE_BURST_LIMIT,
            ),
        )

        cdk.CfnOutput(self, "ChatFunctionArn", value=chat_function.function_arn)
        cdk.CfnOutput(self, "ChatApiEndpoint", value=stage.url)
        cdk.CfnOutput(self, "ChatRoute", value=f"POST {CHAT_ROUTE}")
