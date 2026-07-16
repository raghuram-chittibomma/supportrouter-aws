"""AWS Budget + account-level cost guardrails (ADR-008)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_budgets as budgets
from constructs import Construct

from supportrouter_infra.constants import MONTHLY_BUDGET_USD, PROJECT_NAME


class CostGuardrailsStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        alert_email = (
            self.node.try_get_context("budget_alert_email")
            or "supportrouter-budget@example.com"
        )

        budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=MONTHLY_BUDGET_USD,
                    unit="USD",
                ),
                budget_name=f"{PROJECT_NAME}-monthly-{MONTHLY_BUDGET_USD}",
                # Tag filter: resources tagged Project=supportrouter (ADR-008)
                cost_filters={
                    "TagKeyValue": [f"user:Project${PROJECT_NAME}"],
                },
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN",
                        notification_type="ACTUAL",
                        threshold=80,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=str(alert_email),
                            subscription_type="EMAIL",
                        )
                    ],
                )
            ],
        )

        cdk.Tags.of(self).add("Project", PROJECT_NAME)
        cdk.Tags.of(self).add("CostCenter", "dormancy-safe")

        cdk.CfnOutput(self, "BudgetAlertEmail", value=str(alert_email))
        cdk.CfnOutput(
            self,
            "BudgetTagFilter",
            value=f"user:Project${PROJECT_NAME}",
        )
