"""Observability with dormancy cost caps (ADR-008): ≤3 dashboards, short log retention."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_logs as logs
from constructs import Construct

from supportrouter_infra.constants import (
    CHAT_FUNCTION_NAME,
    LOG_RETENTION_DAYS,
    MAX_DASHBOARDS,
    PROJECT_NAME,
    RUNTIME_LAMBDA_NAMES,
)


def _lambda_metric(
    function_name: str,
    metric_name: str,
    *,
    statistic: str = "Sum",
    period: cdk.Duration | None = None,
) -> cloudwatch.Metric:
    return cloudwatch.Metric(
        namespace="AWS/Lambda",
        metric_name=metric_name,
        dimensions_map={"FunctionName": function_name},
        statistic=statistic,
        period=period or cdk.Duration.minutes(5),
    )


class ObservabilityStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        retention = (
            logs.RetentionDays.TWO_WEEKS
            if LOG_RETENTION_DAYS == 14
            else logs.RetentionDays.ONE_WEEK
        )

        self.agent_log_group = logs.LogGroup(
            self,
            "AgentLogGroup",
            log_group_name=f"/supportrouter/{PROJECT_NAME}/agent",
            retention=retention,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.eval_log_group = logs.LogGroup(
            self,
            "EvalLogGroup",
            log_group_name=f"/supportrouter/{PROJECT_NAME}/evals",
            retention=retention,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        chat_log_group_name = f"/aws/lambda/{CHAT_FUNCTION_NAME}"
        period = cdk.Duration.minutes(5)

        # Cap: at most MAX_DASHBOARDS (3). Token amplification noted in EVAL_STRATEGY.
        dashboards: list[cloudwatch.Dashboard] = []

        runtime_dash = cloudwatch.Dashboard(
            self,
            "RuntimeDashboard",
            dashboard_name=f"{PROJECT_NAME}-runtime",
        )
        runtime_dash.add_widgets(
            cloudwatch.TextWidget(
                markdown=(
                    f"# {PROJECT_NAME} runtime\n"
                    f"- Chat Lambda log group (structured JSON traces): "
                    f"`{chat_log_group_name}`\n"
                    f"- Reserved agent log group (no writers yet): "
                    f"`{self.agent_log_group.log_group_name}`\n"
                    f"- Retention: **{LOG_RETENTION_DAYS}** days. "
                    "Token amplification: expect 5–10× Bedrock tokens per user turn."
                ),
                width=24,
                height=4,
            ),
            cloudwatch.GraphWidget(
                title="Chat Lambda — invocations / errors / throttles",
                left=[
                    _lambda_metric(CHAT_FUNCTION_NAME, "Invocations", period=period),
                    _lambda_metric(CHAT_FUNCTION_NAME, "Errors", period=period),
                    _lambda_metric(CHAT_FUNCTION_NAME, "Throttles", period=period),
                ],
                width=12,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Chat Lambda — duration (avg / p99)",
                left=[
                    _lambda_metric(
                        CHAT_FUNCTION_NAME,
                        "Duration",
                        statistic="Average",
                        period=period,
                    ),
                    _lambda_metric(
                        CHAT_FUNCTION_NAME,
                        "Duration",
                        statistic="p99",
                        period=period,
                    ),
                ],
                width=12,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Tool Lambdas — invocations",
                left=[
                    _lambda_metric(name, "Invocations", period=period)
                    for name in RUNTIME_LAMBDA_NAMES
                    if name != CHAT_FUNCTION_NAME
                ],
                width=12,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Tool Lambdas — errors",
                left=[
                    _lambda_metric(name, "Errors", period=period)
                    for name in RUNTIME_LAMBDA_NAMES
                    if name != CHAT_FUNCTION_NAME
                ],
                width=12,
                height=6,
            ),
        )
        dashboards.append(runtime_dash)

        cost_dash = cloudwatch.Dashboard(
            self,
            "CostSignalsDashboard",
            dashboard_name=f"{PROJECT_NAME}-cost-signals",
        )
        cost_dash.add_widgets(
            cloudwatch.TextWidget(
                markdown=(
                    "# Cost signals\n"
                    "Bedrock account-level invocation metrics (not dollar spend). "
                    "Cite cache savings **only** from measured scorecards "
                    "(ADR-021). Monthly budget alert lives on "
                    "`SupportRouter-CostGuardrails` ($20)."
                ),
                width=24,
                height=3,
            ),
            cloudwatch.GraphWidget(
                title="Bedrock — invocations",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/Bedrock",
                        metric_name="Invocations",
                        statistic="Sum",
                        period=period,
                    )
                ],
                width=12,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Bedrock — invocation latency (avg)",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/Bedrock",
                        metric_name="InvocationLatency",
                        statistic="Average",
                        period=period,
                    )
                ],
                width=12,
                height=6,
            ),
            cloudwatch.GraphWidget(
                title="Bedrock — client / server errors",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/Bedrock",
                        metric_name="InvocationClientErrors",
                        statistic="Sum",
                        period=period,
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/Bedrock",
                        metric_name="InvocationServerErrors",
                        statistic="Sum",
                        period=period,
                    ),
                ],
                width=24,
                height=6,
            ),
        )
        dashboards.append(cost_dash)

        eval_dash = cloudwatch.Dashboard(
            self,
            "EvalDashboard",
            dashboard_name=f"{PROJECT_NAME}-evals",
        )
        eval_dash.add_widgets(
            cloudwatch.TextWidget(
                markdown=(
                    "# Eval plane\n"
                    "- Schedule default **OFF** (`enable_reeval_schedule=false`). "
                    "Prefer the local/live harness CLI while dormant.\n"
                    f"- Reserved eval log group (no harness writer yet): "
                    f"`{self.eval_log_group.log_group_name}`\n"
                    "- Scorecards under `evals/scorecards/` remain the source of "
                    "truth for measured eval cost and cache claims."
                ),
                width=24,
                height=5,
            )
        )
        dashboards.append(eval_dash)

        if len(dashboards) > MAX_DASHBOARDS:
            raise ValueError(
                f"Dashboard count {len(dashboards)} exceeds MAX_DASHBOARDS={MAX_DASHBOARDS}"
            )

        # Cheap operator signals; no SNS actions (dormancy-safe).
        cloudwatch.Alarm(
            self,
            "ChatLambdaErrorsAlarm",
            alarm_name=f"{PROJECT_NAME}-chat-errors",
            metric=_lambda_metric(CHAT_FUNCTION_NAME, "Errors", period=period),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="Chat Lambda reported Errors ≥ 1 in a 5-minute period.",
        )
        cloudwatch.Alarm(
            self,
            "ChatLambdaThrottlesAlarm",
            alarm_name=f"{PROJECT_NAME}-chat-throttles",
            metric=_lambda_metric(CHAT_FUNCTION_NAME, "Throttles", period=period),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="Chat Lambda reported Throttles ≥ 1 in a 5-minute period.",
        )

        cdk.CfnOutput(self, "AgentLogGroupName", value=self.agent_log_group.log_group_name)
        cdk.CfnOutput(self, "EvalLogGroupName", value=self.eval_log_group.log_group_name)
        cdk.CfnOutput(self, "ChatLogGroupName", value=chat_log_group_name)
        cdk.CfnOutput(self, "DashboardCount", value="3")
        cdk.CfnOutput(self, "LogRetentionDays", value=str(LOG_RETENTION_DAYS))
        cdk.CfnOutput(
            self,
            "RuntimeDashboardName",
            value=f"{PROJECT_NAME}-runtime",
        )
        cdk.CfnOutput(
            self,
            "CostSignalsDashboardName",
            value=f"{PROJECT_NAME}-cost-signals",
        )
        cdk.CfnOutput(
            self,
            "EvalDashboardName",
            value=f"{PROJECT_NAME}-evals",
        )
        cdk.CfnOutput(
            self,
            "TokenAmplificationNote",
            value="5-10x Bedrock tokens per user-visible turn (see EVAL_STRATEGY)",
        )
        cdk.CfnOutput(
            self,
            "TraceSinkNote",
            value=(
                "Lambda chat handler activates LoggingTraceSink; JSON events land in "
                f"{chat_log_group_name}. Dedicated agent/evals groups are reserved."
            ),
        )

        cdk.Tags.of(self).add("Project", PROJECT_NAME)
