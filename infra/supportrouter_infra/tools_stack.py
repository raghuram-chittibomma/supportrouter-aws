"""Synthetic order Lambda tools with per-function least-privilege IAM."""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct

from supportrouter_infra.constants import PROJECT_NAME

TOOLS_ASSET = str(Path(__file__).resolve().parents[2] / "tools")
TOOL_HANDLER_FILES = {
    "get_order_status.py",
    "initiate_return.py",
    "issue_refund.py",
}


def tool_asset_excludes(handler: str) -> list[str]:
    own_file = f"{handler.split('.')[0]}.py"
    return [
        "__pycache__",
        "*.pyc",
        *sorted(TOOL_HANDLER_FILES - {own_file}),
    ]


class ToolsStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cdk.Tags.of(self).add("Project", PROJECT_NAME)

        orders = self._table("Orders", "order_id")
        returns = self._table("Returns", "return_id")
        refunds = self._table("RefundRequests", "refund_id")

        status_function = self._tool_function(
            logical_id="GetOrderStatus",
            function_name=f"{PROJECT_NAME}-get-order-status",
            handler="get_order_status.handler",
            environment={"ORDERS_TABLE_NAME": orders.table_name},
            read_table_arns=[orders.table_arn],
            write_table_arns=[],
        )
        return_function = self._tool_function(
            logical_id="InitiateReturn",
            function_name=f"{PROJECT_NAME}-initiate-return",
            handler="initiate_return.handler",
            environment={
                "ORDERS_TABLE_NAME": orders.table_name,
                "RETURNS_TABLE_NAME": returns.table_name,
            },
            read_table_arns=[orders.table_arn, returns.table_arn],
            write_table_arns=[returns.table_arn],
        )
        refund_function = self._tool_function(
            logical_id="IssueRefund",
            function_name=f"{PROJECT_NAME}-issue-refund",
            handler="issue_refund.handler",
            environment={
                "ORDERS_TABLE_NAME": orders.table_name,
                "REFUNDS_TABLE_NAME": refunds.table_name,
            },
            read_table_arns=[orders.table_arn, refunds.table_arn],
            write_table_arns=[refunds.table_arn],
        )

        for name, value in (
            ("OrdersTableName", orders.table_name),
            ("ReturnsTableName", returns.table_name),
            ("RefundRequestsTableName", refunds.table_name),
            ("GetOrderStatusFunctionArn", status_function.function_arn),
            ("InitiateReturnFunctionArn", return_function.function_arn),
            ("IssueRefundFunctionArn", refund_function.function_arn),
        ):
            cdk.CfnOutput(self, name, value=value)

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

    def _tool_function(
        self,
        *,
        logical_id: str,
        function_name: str,
        handler: str,
        environment: dict[str, str],
        read_table_arns: list[str],
        write_table_arns: list[str],
    ) -> lambda_.Function:
        log_group = logs.LogGroup(
            self,
            f"{logical_id}Logs",
            log_group_name=f"/aws/lambda/{function_name}",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        role = iam.Role(
            self,
            f"{logical_id}Role",
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
        if read_table_arns:
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="ReadRequiredTables",
                    actions=["dynamodb:GetItem"],
                    resources=read_table_arns,
                )
            )
        if write_table_arns:
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="WriteRequiredTable",
                    actions=["dynamodb:PutItem"],
                    resources=write_table_arns,
                )
            )

        return lambda_.Function(
            self,
            f"{logical_id}Function",
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            code=lambda_.Code.from_asset(
                TOOLS_ASSET,
                exclude=tool_asset_excludes(handler),
            ),
            handler=handler,
            role=role,
            environment=environment,
            timeout=cdk.Duration.seconds(5),
            memory_size=128,
            log_group=log_group,
        )
