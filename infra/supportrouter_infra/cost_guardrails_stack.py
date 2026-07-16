"""AWS Budget + account-level cost guardrails (ADR-008)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_budgets as budgets
from constructs import Construct

from supportrouter_infra.constants import MONTHLY_BUDGET_USD, PROJECT_NAME


class CostGuardrailsStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

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
                cost_filters=None,
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
                            address="supportrouter-budget@example.com",
                            subscription_type="EMAIL",
                        )
                    ],
                )
            ],
        )

        cdk.Tags.of(self).add("Project", PROJECT_NAME)
        cdk.Tags.of(self).add("CostCenter", "dormancy-safe")
