"""Optional EventBridge re-eval schedule — default OFF (ADR-008)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_logs as logs
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct

from supportrouter_infra.constants import LOG_RETENTION_DAYS, PROJECT_NAME


class EvalScheduleStack(cdk.Stack):
    """Creates EventBridge rule ONLY when enable_reeval_schedule=true."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        enable_reeval_schedule: bool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stub state machine until issue #17 wires the real eval harness.
        log_group = logs.LogGroup(
            self,
            "EvalStubLogs",
            log_group_name=f"/supportrouter/{PROJECT_NAME}/eval-stub",
            retention=logs.RetentionDays.TWO_WEEKS
            if LOG_RETENTION_DAYS == 14
            else logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        definition = sfn.Pass(
            self,
            "EvalPlaceholder",
            comment="Replace with Step Functions Map fan-out when eval harness (#17) lands",
            result=sfn.Result.from_object(
                {
                    "status": "placeholder",
                    "message": "Scheduled eval stub — enable only for demos",
                }
            ),
        )
        state_machine = sfn.StateMachine(
            self,
            "EvalStubStateMachine",
            state_machine_name=f"{PROJECT_NAME}-eval-stub",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ERROR,
            ),
        )

        cdk.CfnOutput(self, "EvalStateMachineArn", value=state_machine.state_machine_arn)
        cdk.CfnOutput(
            self,
            "ReevalScheduleEnabled",
            value=str(enable_reeval_schedule).lower(),
        )

        if enable_reeval_schedule:
            rule = events.Rule(
                self,
                "ReevalScheduleRule",
                rule_name=f"{PROJECT_NAME}-reeval-schedule",
                description="SupportRouter scheduled re-eval (ADR-008 — burns Bedrock tokens)",
                schedule=events.Schedule.rate(cdk.Duration.days(7)),
                enabled=True,
            )
            rule.add_target(targets.SfnStateMachine(state_machine))
            cdk.CfnOutput(self, "ReevalRuleName", value=rule.rule_name)
        # When false: intentionally create NO EventBridge rule.

        cdk.Tags.of(self).add("Project", PROJECT_NAME)
