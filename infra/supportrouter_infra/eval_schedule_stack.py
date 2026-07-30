"""Optional EventBridge re-eval schedule — default OFF (ADR-008 / #75).

Always provisions a placeholder Step Functions machine + 14-day log group so
operators can deploy scaffolding. Creates an EventBridge rule **only** when
``enable_reeval_schedule=true``. Prefer on-demand ``python -m evals.harness``
(or ``--live``) for manual runs; flip the CDK context only when a standing
weekly schedule is intentionally wanted.
"""

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

        # Placeholder until a future slice wires SFN Map → live harness.
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
            comment=(
                "Placeholder — replace with Step Functions Map fan-out that "
                "invokes the live eval harness when scheduled re-eval is wired"
            ),
            result=sfn.Result.from_object(
                {
                    "status": "placeholder",
                    "message": (
                        "Scheduled eval stub — no Bedrock until the harness is "
                        "wired; keep enable_reeval_schedule=false unless intentional"
                    ),
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
        cdk.CfnOutput(
            self,
            "ManualEvalPreferred",
            value=(
                "python -m evals.harness [--live]; schedule stays off until "
                "enable_reeval_schedule=true"
            ),
        )

        if enable_reeval_schedule:
            rule = events.Rule(
                self,
                "ReevalScheduleRule",
                rule_name=f"{PROJECT_NAME}-reeval-schedule",
                description=(
                    "SupportRouter scheduled re-eval (ADR-008 — opt-in only; "
                    "burns Bedrock tokens once the stub targets a live harness)"
                ),
                schedule=events.Schedule.rate(cdk.Duration.days(7)),
                enabled=True,
            )
            rule.add_target(targets.SfnStateMachine(state_machine))
            cdk.CfnOutput(self, "ReevalRuleName", value=rule.rule_name)
        # When false: intentionally create NO EventBridge rule.

        cdk.Tags.of(self).add("Project", PROJECT_NAME)
