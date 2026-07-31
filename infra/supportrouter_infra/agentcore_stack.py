"""Opt-in Bedrock AgentCore Runtime host for SupportRouter (ADR-024).

Dual-run: keeps ``SupportRouter-Api`` chat Lambda as the default edge.
Packages an ARM64 code asset (``from_code_asset``) with a thin
``BedrockAgentCoreApp`` entrypoint over ``run_agent``.
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
    aws_bedrockagentcore as agentcore,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct

from supportrouter_infra.constants import PROJECT_NAME

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTCORE_REQUIREMENTS = PROJECT_ROOT / "infra" / "agentcore_runtime_requirements.txt"
RUNTIME_NAME = "supportrouter_agent"
# Demo-friendly idle teardown (default AgentCore idle is 900s).
IDLE_SESSION_TIMEOUT = cdk.Duration.seconds(120)


def copy_agentcore_sources(output_dir: Path) -> None:
    """Stage package + synthetic fixtures at the asset root (importable layout)."""
    shutil.copytree(
        PROJECT_ROOT / "src" / "supportrouter",
        output_dir / "supportrouter",
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
class AgentCoreLocalBundling:
    """Build Linux ARM64 deps for AgentCore code deploy without local Docker."""

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
                    f"--requirement={AGENTCORE_REQUIREMENTS}",
                    f"--target={target}",
                ],
                check=True,
            )
            copy_agentcore_sources(target)
        except (OSError, subprocess.CalledProcessError):
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
            return False
        return True


def agentcore_runtime_bundling() -> cdk.BundlingOptions:
    return cdk.BundlingOptions(
        image=lambda_.Runtime.PYTHON_3_12.bundling_image,
        platform="linux/arm64",
        local=AgentCoreLocalBundling(),
        command=[
            "bash",
            "-c",
            (
                "pip install --disable-pip-version-check --no-compile "
                "--quiet --only-binary=:all: "
                "--platform=manylinux2014_aarch64 --implementation=cp "
                "--python-version=3.12 --abi=cp312 "
                "-r /asset-input/infra/agentcore_runtime_requirements.txt "
                "-t /asset-output && "
                "cp -r /asset-input/src/supportrouter /asset-output/supportrouter && "
                "rm -rf /asset-output/supportrouter/ui.py && "
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


class AgentCoreStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        sessions_table: dynamodb.ITable,
        approvals_table: dynamodb.ITable,
        routing_table: dynamodb.ITable,
        knowledge_base_id: str | None = None,
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        get_order_status_function: lambda_.IFunction | None = None,
        initiate_return_function: lambda_.IFunction | None = None,
        issue_refund_function: lambda_.IFunction | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cdk.Tags.of(self).add("Project", PROJECT_NAME)

        environment: dict[str, str] = {
            "SESSIONS_TABLE_NAME": sessions_table.table_name,
            "APPROVALS_TABLE_NAME": approvals_table.table_name,
            "SUPPORTROUTER_ROUTING_TABLE_NAME": routing_table.table_name,
            # Default local stubs; operators can InvokeAgentRuntime with
            # runtime_mode=aws in the payload for Bedrock/tool path.
            "SUPPORTROUTER_RUNTIME_MODE": "local",
        }
        if knowledge_base_id:
            environment["SUPPORTROUTER_KB_ID"] = knowledge_base_id
        if guardrail_id:
            environment["SUPPORTROUTER_GUARDRAIL_ID"] = guardrail_id
        if guardrail_version:
            environment["SUPPORTROUTER_GUARDRAIL_VERSION"] = guardrail_version
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

        artifact = agentcore.AgentRuntimeArtifact.from_code_asset(
            path=str(PROJECT_ROOT),
            runtime=agentcore.AgentCoreRuntime.PYTHON_3_12,
            entrypoint=["python", "-m", "supportrouter.agentcore_main"],
            bundling=agentcore_runtime_bundling(),
        )

        runtime = agentcore.Runtime(
            self,
            "SupportAgentRuntime",
            runtime_name=RUNTIME_NAME,
            description="SupportRouter LangGraph dual-run host (ADR-024)",
            agent_runtime_artifact=artifact,
            protocol_configuration=agentcore.ProtocolType.HTTP,
            environment_variables=environment,
            lifecycle_configuration=agentcore.LifecycleConfiguration(
                idle_runtime_session_timeout=IDLE_SESSION_TIMEOUT,
            ),
        )

        hitl_arns = [sessions_table.table_arn, approvals_table.table_arn]
        runtime.add_to_role_policy(
            iam.PolicyStatement(
                sid="HitlSessionApprovalAccess",
                actions=["dynamodb:GetItem", "dynamodb:PutItem"],
                resources=hitl_arns,
            )
        )
        runtime.add_to_role_policy(
            iam.PolicyStatement(
                sid="RoutingTableRead",
                actions=["dynamodb:GetItem"],
                resources=[routing_table.table_arn],
            )
        )

        bedrock_resources = [
            "arn:aws:bedrock:*:*:inference-profile/*",
            "arn:aws:bedrock:*:*:application-inference-profile/*",
            "arn:aws:bedrock:*::foundation-model/*",
        ]
        if knowledge_base_id:
            bedrock_resources.append(
                f"arn:aws:bedrock:*:*:knowledge-base/{knowledge_base_id}"
            )
        else:
            bedrock_resources.append("arn:aws:bedrock:*:*:knowledge-base/*")
        runtime.add_to_role_policy(
            iam.PolicyStatement(
                sid="BedrockConverseAndRetrieve",
                actions=[
                    "bedrock:Converse",
                    "bedrock:InvokeModel",
                    "bedrock:Retrieve",
                ],
                resources=bedrock_resources,
            )
        )
        if guardrail_id:
            runtime.add_to_role_policy(
                iam.PolicyStatement(
                    sid="BedrockApplyGuardrail",
                    actions=["bedrock:ApplyGuardrail"],
                    resources=[
                        f"arn:aws:bedrock:{cdk.Stack.of(self).region}:"
                        f"{cdk.Stack.of(self).account}:guardrail/{guardrail_id}",
                        f"arn:aws:bedrock:{cdk.Stack.of(self).region}:"
                        f"{cdk.Stack.of(self).account}:guardrail/{guardrail_id}/*",
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
            runtime.add_to_role_policy(
                iam.PolicyStatement(
                    sid="InvokeToolLambdas",
                    actions=["lambda:InvokeFunction"],
                    resources=[fn.function_arn for fn in tool_fns],
                )
            )

        self.agent_runtime = runtime
        cdk.CfnOutput(self, "AgentRuntimeId", value=runtime.agent_runtime_id)
        cdk.CfnOutput(self, "AgentRuntimeArn", value=runtime.agent_runtime_arn)
        cdk.CfnOutput(self, "AgentRuntimeName", value=RUNTIME_NAME)
