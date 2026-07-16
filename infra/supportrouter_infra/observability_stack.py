"""Observability with dormancy cost caps (ADR-008): ≤3 dashboards, short log retention."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_logs as logs
from constructs import Construct

from supportrouter_infra.constants import LOG_RETENTION_DAYS, MAX_DASHBOARDS, PROJECT_NAME


class ObservabilityStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        retention = (
            logs.RetentionDays.TWO_WEEKS
            if LOG_RETENTION_DAYS == 14
            else logs.RetentionDays.ONE_WEEK
        )

        agent_logs = logs.LogGroup(
            self,
            "AgentLogGroup",
            log_group_name=f"/supportrouter/{PROJECT_NAME}/agent",
            retention=retention,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        eval_logs = logs.LogGroup(
            self,
            "EvalLogGroup",
            log_group_name=f"/supportrouter/{PROJECT_NAME}/evals",
            retention=retention,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Cap: at most MAX_DASHBOARDS (3). Token amplification noted in EVAL_STRATEGY.
        runtime_dash = cloudwatch.Dashboard(
            self,
            "RuntimeDashboard",
            dashboard_name=f"{PROJECT_NAME}-runtime",
        )
        runtime_dash.add_widgets(
            cloudwatch.TextWidget(
                markdown=(
                    f"# {PROJECT_NAME} runtime\n"
                    "Place Lambda/API metrics here when runtime Lambdas land.\n"
                    f"Log retention: {LOG_RETENTION_DAYS} days. "
                    "Token amplification: expect 5–10× Bedrock tokens per user turn."
                ),
                width=24,
                height=4,
            )
        )

        cost_dash = cloudwatch.Dashboard(
            self,
            "CostSignalsDashboard",
            dashboard_name=f"{PROJECT_NAME}-cost-signals",
        )
        cost_dash.add_widgets(
            cloudwatch.TextWidget(
                markdown=(
                    "# Cost signals\n"
                    "Track Bedrock invocation counts and estimated spend. "
                    "Assume `cache_enabled=false` until scorecards measure hits (ADR-005/008)."
                ),
                width=24,
                height=4,
            )
        )

        eval_dash = cloudwatch.Dashboard(
            self,
            "EvalDashboard",
            dashboard_name=f"{PROJECT_NAME}-evals",
        )
        eval_dash.add_widgets(
            cloudwatch.TextWidget(
                markdown=(
                    "# Eval plane\n"
                    "Schedule default OFF. Manual harness preferred while dormant."
                ),
                width=24,
                height=3,
            )
        )

        if MAX_DASHBOARDS < 3:
            raise ValueError("MAX_DASHBOARDS unexpectedly below dashboard count")

        cdk.CfnOutput(self, "AgentLogGroupName", value=agent_logs.log_group_name)
        cdk.CfnOutput(self, "EvalLogGroupName", value=eval_logs.log_group_name)
        cdk.CfnOutput(self, "DashboardCount", value="3")
        cdk.CfnOutput(self, "LogRetentionDays", value=str(LOG_RETENTION_DAYS))
        cdk.CfnOutput(
            self,
            "TokenAmplificationNote",
            value="5-10x Bedrock tokens per user-visible turn (see EVAL_STRATEGY)",
        )

        cdk.Tags.of(self).add("Project", PROJECT_NAME)
