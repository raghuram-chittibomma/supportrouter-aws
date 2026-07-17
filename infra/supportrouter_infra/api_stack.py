"""HTTP API edge that fronts the SupportRouter chat Lambda (ADR-014).

Dormancy-safe: HTTP API (not REST) with pay-per-request pricing, throttled
default stage, a 14-day log group, and a least-privilege role that can only write
its own logs. The chat Lambda runs the local-stub agent, so no Bedrock, DynamoDB,
or other data-plane permissions are granted here.
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
            environment={"PYTHONPATH": "/var/task/src:/var/task"},
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
