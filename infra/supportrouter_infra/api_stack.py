"""HTTP API edge that fronts the SupportRouter chat Lambda (ADR-014 / ADR-017).

Dormancy-safe: HTTP API (not REST) with pay-per-request pricing, throttled
default stage, a 14-day log group, and a least-privilege role. The chat Lambda
still drafts with the local stub (no Bedrock). When Sessions and ApprovalRequests
tables are present, the role may read/write only those tables for HITL (#16).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import aws_cdk as cdk
import jsii
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct

from supportrouter_infra.constants import PROJECT_NAME

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_REQUIREMENTS = PROJECT_ROOT / "infra" / "chat_runtime_requirements.txt"
CHAT_ROUTE = "/chat"

# Throttle caps keep a dormant demo from accruing runaway request cost.
THROTTLE_RATE_LIMIT = 10
THROTTLE_BURST_LIMIT = 20


def copy_runtime_sources(output_dir: Path) -> None:
    """Copy only runtime package and synthetic fixtures into a staged asset."""
    shutil.copytree(
        PROJECT_ROOT / "src" / "supportrouter",
        output_dir / "src" / "supportrouter",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "ui.py"),
    )
    for fixture_dir in ("sample", "knowledge_base"):
        shutil.copytree(
            PROJECT_ROOT / "data" / fixture_dir,
            output_dir / "data" / fixture_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


@jsii.implements(cdk.ILocalBundling)
class ChatRuntimeLocalBundling:
    """Build Linux ARM64 Python dependencies without requiring local Docker."""

    def try_bundle(
        self,
        output_dir: str,
        options: cdk.BundlingOptions,
    ) -> bool:
        del options
        if os.environ.get("SUPPORTROUTER_FORCE_DOCKER_BUNDLING") == "1":
            return False
        target = Path(output_dir)
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--quiet",
                    "--no-compile",
                    "--only-binary=:all:",
                    "--platform=manylinux2014_aarch64",
                    "--implementation=cp",
                    "--python-version=3.12",
                    "--abi=cp312",
                    f"--requirement={RUNTIME_REQUIREMENTS}",
                    f"--target={target}",
                ],
                check=True,
            )
            copy_runtime_sources(target)
        except (OSError, subprocess.CalledProcessError):
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
            return False
        return True


def chat_runtime_bundling() -> cdk.BundlingOptions:
    return cdk.BundlingOptions(
        image=lambda_.Runtime.PYTHON_3_12.bundling_image,
        platform="linux/arm64",
        local=ChatRuntimeLocalBundling(),
        command=[
            "bash",
            "-c",
            (
                "pip install --disable-pip-version-check --no-compile "
                "--quiet --only-binary=:all: "
                "--platform=manylinux2014_aarch64 --implementation=cp "
                "--python-version=3.12 --abi=cp312 "
                "-r /asset-input/infra/chat_runtime_requirements.txt "
                "-t /asset-output && "
                "mkdir -p /asset-output/src && "
                "cp -r /asset-input/src/supportrouter "
                "/asset-output/src/supportrouter && "
                "rm -rf /asset-output/src/supportrouter/ui.py && "
                "mkdir -p /asset-output/data && "
                "cp -r /asset-input/data/sample /asset-output/data/sample && "
                "cp -r /asset-input/data/knowledge_base "
                "/asset-output/data/knowledge_base && "
                "find /asset-output -type d -name __pycache__ "
                "-prune -exec rm -rf '{}' + && "
                "find /asset-output -type f -name '*.pyc' -delete"
            ),
        ],
    )


class ApiStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        knowledge_base_id: str | None = None,
        get_order_status_function: lambda_.IFunction | None = None,
        initiate_return_function: lambda_.IFunction | None = None,
        issue_refund_function: lambda_.IFunction | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cdk.Tags.of(self).add("Project", PROJECT_NAME)

        sessions = self._table("Sessions", "session_id")
        approvals = self._table("ApprovalRequests", "approval_id")

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
        hitl_table_arns = [sessions.table_arn, approvals.table_arn]
        role.add_to_policy(
            iam.PolicyStatement(
                sid="HitlSessionApprovalAccess",
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                ],
                resources=hitl_table_arns,
            )
        )
        # AWS runtime mode: Bedrock draft + KB retrieve (service-scoped ARNs).
        role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockConverseAndRetrieve",
                actions=[
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Retrieve",
                ],
                resources=[
                    "arn:aws:bedrock:*:*:inference-profile/*",
                    "arn:aws:bedrock:*:*:application-inference-profile/*",
                    "arn:aws:bedrock:*::foundation-model/*",
                    "arn:aws:bedrock:*:*:knowledge-base/*",
                ],
            )
        )
        tool_fns = [
            fn
            for fn in (
                get_order_status_function,
                initiate_return_function,
                issue_refund_function,
            )
            if fn is not None
        ]
        if tool_fns:
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="InvokeToolLambdas",
                    actions=["lambda:InvokeFunction"],
                    resources=[fn.function_arn for fn in tool_fns],
                )
            )

        environment = {
            "PYTHONPATH": "/var/task/src:/var/task",
            "SESSIONS_TABLE_NAME": sessions.table_name,
            "APPROVALS_TABLE_NAME": approvals.table_name,
            "SUPPORTROUTER_RUNTIME_MODE": "local",
        }
        if knowledge_base_id:
            environment["SUPPORTROUTER_KB_ID"] = knowledge_base_id
        if get_order_status_function is not None:
            environment["GET_ORDER_STATUS_FUNCTION_NAME"] = (
                get_order_status_function.function_name
            )
        if initiate_return_function is not None:
            environment["INITIATE_RETURN_FUNCTION_NAME"] = (
                initiate_return_function.function_name
            )
        if issue_refund_function is not None:
            environment["ISSUE_REFUND_FUNCTION_NAME"] = (
                issue_refund_function.function_name
            )

        chat_function = lambda_.Function(
            self,
            "ChatFunction",
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            code=lambda_.Code.from_asset(
                str(PROJECT_ROOT),
                asset_hash_type=cdk.AssetHashType.OUTPUT,
                bundling=chat_runtime_bundling(),
                exclude=[
                    ".git",
                    ".github",
                    ".cursor",
                    ".env",
                    ".env.*",
                    ".venv",
                    ".pytest_cache",
                    "docs",
                    "evals",
                    "infra/cdk.out",
                    "scripts",
                    "tests",
                    "tools",
                ],
            ),
            handler="supportrouter.api.handler",
            role=role,
            environment=environment,
            timeout=cdk.Duration.seconds(60),
            memory_size=512,
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
        cdk.CfnOutput(self, "SessionsTableName", value=sessions.table_name)
        cdk.CfnOutput(self, "ApprovalRequestsTableName", value=approvals.table_name)

    def _table(self, logical_id: str, partition_key: str) -> dynamodb.Table:
        return dynamodb.Table(
            self,
            logical_id,
            table_name=f"{PROJECT_NAME}-{logical_id.lower()}",
            partition_key=dynamodb.Attribute(
                name=partition_key,
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
