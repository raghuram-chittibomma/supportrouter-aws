"""CDK synthesis guardrails for dormancy-safe design (ADR-007/008)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template
from supportrouter.guardrails import LOCAL_POLICY_CAPABILITIES

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
sys.path.insert(0, str(INFRA))

from supportrouter_infra.cost_guardrails_stack import CostGuardrailsStack  # noqa: E402
from supportrouter_infra.eval_schedule_stack import EvalScheduleStack  # noqa: E402
from supportrouter_infra.guardrails_stack import (  # noqa: E402
    BEDROCK_GUARDRAIL_POLICY_SHA256,
    BEDROCK_GUARDRAIL_POLICY_SPEC,
    GuardrailsStack,
)
from supportrouter_infra.api_stack import (  # noqa: E402
    RUNTIME_REQUIREMENTS,
    ApiStack,
    ChatRuntimeLocalBundling,
    chat_runtime_bundling,
    copy_runtime_sources,
)
from supportrouter_infra.knowledge_base_stack import KnowledgeBaseStack  # noqa: E402
from supportrouter_infra.observability_stack import ObservabilityStack  # noqa: E402
from supportrouter_infra.tools_stack import (  # noqa: E402
    ToolsStack,
    tool_asset_excludes,
)


@pytest.fixture
def env() -> cdk.Environment:
    return cdk.Environment(account="111111111111", region="us-east-1")


def test_cost_budget_twenty_dollars(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = CostGuardrailsStack(app, "Cost", env=env)
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": {
                "BudgetLimit": {"Amount": 20, "Unit": "USD"},
                "BudgetType": "COST",
                "TimeUnit": "MONTHLY",
                "CostFilters": {
                    "TagKeyValue": ["user:Project$supportrouter"],
                },
            }
        },
    )


def test_knowledge_base_uses_s3_vectors_not_opensearch(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = KnowledgeBaseStack(app, "Kb", env=env)
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::Bedrock::KnowledgeBase",
        {
            "StorageConfiguration": {"Type": "S3_VECTORS"},
        },
    )
    raw = json.dumps(template.to_json())
    assert "AWS::OpenSearchServerless::Collection" not in raw
    assert "OPENSEARCH_SERVERLESS" not in raw
    assert "AWS::EC2::VPC" not in raw
    assert "AWS::EC2::NatGateway" not in raw
    assert '"Type": "S3_VECTORS"' in raw or '"Type":"S3_VECTORS"' in raw


def test_knowledge_base_role_scopes_s3_vector_permissions(
    env: cdk.Environment,
) -> None:
    app = cdk.App()
    stack = KnowledgeBaseStack(app, "KbIam", env=env)
    resources = Template.from_stack(stack).to_json()["Resources"]
    policies = [
        resource["Properties"]["PolicyDocument"]
        for resource in resources.values()
        if resource["Type"] == "AWS::IAM::Policy"
    ]
    s3_vector_statements = [
        statement
        for policy in policies
        for statement in policy["Statement"]
        if any(
            str(action).startswith("s3vectors:")
            for action in (
                statement["Action"]
                if isinstance(statement["Action"], list)
                else [statement["Action"]]
            )
        )
    ]

    assert len(s3_vector_statements) == 2
    assert all(statement["Resource"] != "*" for statement in s3_vector_statements)

    bucket_statement = next(
        statement
        for statement in s3_vector_statements
        if "s3vectors:GetVectorBucket" in statement["Action"]
    )
    assert set(bucket_statement["Action"]) == {
        "s3vectors:GetVectorBucket",
        "s3vectors:ListIndexes",
    }
    assert "VectorBucket" in json.dumps(bucket_statement["Resource"])

    index_statement = next(
        statement
        for statement in s3_vector_statements
        if "s3vectors:QueryVectors" in statement["Action"]
    )
    assert set(index_statement["Action"]) == {
        "s3vectors:DeleteVectors",
        "s3vectors:GetIndex",
        "s3vectors:GetVectors",
        "s3vectors:PutVectors",
        "s3vectors:QueryVectors",
    }
    assert "VectorIndex" in json.dumps(index_statement["Resource"])


def test_eval_schedule_rule_absent_when_disabled(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = EvalScheduleStack(app, "EvalOff", enable_reeval_schedule=False, env=env)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::Events::Rule", 0)
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)


def test_eval_schedule_rule_present_when_enabled(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = EvalScheduleStack(app, "EvalOn", enable_reeval_schedule=True, env=env)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::Events::Rule", 1)
    template.has_resource_properties(
        "AWS::Events::Rule",
        {"State": "ENABLED"},
    )


def test_observability_caps(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = ObservabilityStack(app, "Obs", env=env)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::CloudWatch::Dashboard", 3)
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {"RetentionInDays": 14},
    )
    raw = json.dumps(template.to_json())
    assert "AWS::EC2::VPC" not in raw


def test_bedrock_guardrail_covers_input_output_and_version(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = GuardrailsStack(app, "Guardrails", env=env)
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::Bedrock::Guardrail", 1)
    template.resource_count_is("AWS::Bedrock::GuardrailVersion", 1)
    template.has_resource_properties(
        "AWS::Bedrock::Guardrail",
        {
            "Name": "supportrouter-safety",
            "BlockedInputMessaging": Match.string_like_regexp(
                "Remove sensitive details"
            ),
            "SensitiveInformationPolicyConfig": Match.object_like(
                {
                    "PiiEntitiesConfig": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "BLOCK",
                                    "InputAction": "BLOCK",
                                    "InputEnabled": True,
                                    "OutputAction": "BLOCK",
                                    "OutputEnabled": True,
                                }
                            )
                        ]
                    )
                }
            ),
        },
    )
    raw = json.dumps(template.to_json())
    version_logical_ids = [
        logical_id
        for logical_id, resource in template.to_json()["Resources"].items()
        if resource["Type"] == "AWS::Bedrock::GuardrailVersion"
    ]
    assert len(version_logical_ids) == 1
    assert (
        BEDROCK_GUARDRAIL_POLICY_SHA256[:12].lower()
        in version_logical_ids[0].lower()
    )
    assert "DangerousAssistance" in raw
    assert "FinancialAdvice" in raw
    assert "CREDIT_DEBIT_CARD_NUMBER" in raw
    assert "US_SOCIAL_SECURITY_NUMBER" in raw
    assert BEDROCK_GUARDRAIL_POLICY_SHA256 in raw
    assert {topic["name"] for topic in BEDROCK_GUARDRAIL_POLICY_SPEC["topics"]} == {
        "DangerousAssistance",
        "FinancialAdvice",
    }
    assert LOCAL_POLICY_CAPABILITIES == {
        "pii",
        "dangerous_assistance",
        "self_harm_assistance",
        "financial_advice",
    }
    assert {
        "EMAIL",
        "PHONE",
        "CREDIT_DEBIT_CARD_NUMBER",
        "US_SOCIAL_SECURITY_NUMBER",
    }.issubset(BEDROCK_GUARDRAIL_POLICY_SPEC["pii_entity_types"])
    assert '"InputEnabled": true' in raw
    assert '"OutputEnabled": true' in raw


def test_tools_stack_has_three_isolated_lambda_roles(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = ToolsStack(app, "Tools", env=env)
    template = Template.from_stack(stack)
    raw = template.to_json()

    template.resource_count_is("AWS::DynamoDB::Table", 3)
    template.resource_count_is("AWS::Lambda::Function", 3)
    template.resource_count_is("AWS::IAM::Role", 3)
    template.resource_count_is("AWS::Logs::LogGroup", 3)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"BillingMode": "PAY_PER_REQUEST"},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "MemorySize": 128,
            "Timeout": 5,
        },
    )
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {"RetentionInDays": 14},
    )

    functions = {
        resource["Properties"]["Handler"]: resource["Properties"]
        for resource in raw["Resources"].values()
        if resource["Type"] == "AWS::Lambda::Function"
    }
    assert set(functions) == {
        "get_order_status.handler",
        "initiate_return.handler",
        "issue_refund.handler",
    }
    assert set(
        functions["get_order_status.handler"]["Environment"]["Variables"]
    ) == {"ORDERS_TABLE_NAME"}
    assert set(
        functions["initiate_return.handler"]["Environment"]["Variables"]
    ) == {"ORDERS_TABLE_NAME", "RETURNS_TABLE_NAME"}
    assert set(
        functions["issue_refund.handler"]["Environment"]["Variables"]
    ) == {"ORDERS_TABLE_NAME", "REFUNDS_TABLE_NAME"}
    role_ids = {
        properties["Role"]["Fn::GetAtt"][0]
        for properties in functions.values()
    }
    assert len(role_ids) == 3
    roles = [
        resource["Properties"]
        for resource in raw["Resources"].values()
        if resource["Type"] == "AWS::IAM::Role"
    ]
    assert all("ManagedPolicyArns" not in role for role in roles)
    serialized = json.dumps(raw)
    assert "AWS::EC2::VPC" not in serialized
    assert "AWS::EC2::SecurityGroup" not in serialized


def test_api_stack_uses_throttled_http_api_and_least_privilege(
    env: cdk.Environment,
) -> None:
    app = cdk.App()
    stack = ApiStack(app, "Api", env=env)
    template = Template.from_stack(stack)
    raw = template.to_json()

    # HTTP API (v2), not the more expensive REST API.
    template.resource_count_is("AWS::ApiGatewayV2::Api", 1)
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Api",
        {"ProtocolType": "HTTP"},
    )
    serialized = json.dumps(raw)
    assert "AWS::ApiGateway::RestApi" not in serialized
    assert "AWS::EC2::VPC" not in serialized
    assert "AWS::EC2::SecurityGroup" not in serialized

    # Exactly one Lambda, one role, one log group with 14-day retention.
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::IAM::Role", 1)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "Handler": "supportrouter.api.handler",
            "MemorySize": 256,
            "Timeout": 30,
            "Environment": {
                "Variables": {"PYTHONPATH": "/var/task/src:/var/task"},
            },
        },
    )
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {"RetentionInDays": 14},
    )

    # POST /chat route.
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Route",
        {"RouteKey": "POST /chat"},
    )

    # Default stage is throttled to bound request cost.
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {
            "StageName": "$default",
            "AutoDeploy": True,
            "DefaultRouteSettings": {
                "ThrottlingRateLimit": 10,
                "ThrottlingBurstLimit": 20,
            },
        },
    )

    # Role grants only log writes: no data-plane or wildcard permissions.
    roles = [
        resource["Properties"]
        for resource in raw["Resources"].values()
        if resource["Type"] == "AWS::IAM::Role"
    ]
    assert len(roles) == 1
    assert "ManagedPolicyArns" not in roles[0]

    policies = [
        resource["Properties"]["PolicyDocument"]
        for resource in raw["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
    ]
    assert len(policies) == 1
    statements = policies[0]["Statement"]
    all_actions = set()
    for statement in statements:
        actions = statement["Action"]
        all_actions.update(actions if isinstance(actions, list) else [actions])
    assert all_actions == {"logs:CreateLogStream", "logs:PutLogEvents"}

    policy_serialized = json.dumps(policies[0])
    for forbidden in (
        "dynamodb:",
        "bedrock:",
        "s3:",
        '"Action": "*"',
        '"Resource": "*"',
    ):
        assert forbidden not in policy_serialized


def test_chat_runtime_asset_contains_code_data_and_pinned_dependencies(
    tmp_path: Path,
) -> None:
    copy_runtime_sources(tmp_path)

    staged_module = tmp_path / "src" / "supportrouter" / "tools_local.py"
    assert (tmp_path / "src" / "supportrouter" / "api.py").is_file()
    assert not (tmp_path / "src" / "supportrouter" / "ui.py").exists()
    assert (tmp_path / "data" / "sample" / "orders.json").is_file()
    assert (
        staged_module.resolve().parents[2]
        / "data"
        / "sample"
        / "routing_table.json"
    ).is_file()
    assert (
        tmp_path / "data" / "knowledge_base" / "faq-powerdock-001.md"
    ).is_file()

    requirement_lines = [
        line
        for line in RUNTIME_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert len(requirement_lines) > 30
    assert all(line.count("==") == 1 for line in requirement_lines)
    assert any(line.startswith("boto3==") for line in requirement_lines)
    assert any(line.startswith("langgraph==") for line in requirement_lines)


def test_chat_runtime_bundlers_target_same_linux_arm64_layout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SUPPORTROUTER_FORCE_DOCKER_BUNDLING", "1")
    assert not ChatRuntimeLocalBundling().try_bundle(str(tmp_path), None)  # type: ignore[arg-type]

    options = chat_runtime_bundling()
    command = " ".join(options.command or [])
    assert options.platform == "linux/arm64"
    for expected in (
        "--platform=manylinux2014_aarch64",
        "--python-version=3.12",
        "--abi=cp312",
        "/asset-output/src/supportrouter",
        "/asset-output/data/sample",
        "/asset-output/data/knowledge_base",
    ):
        assert expected in command


def test_chat_runtime_local_failure_falls_back_to_docker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_install(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "pip")

    monkeypatch.delenv("SUPPORTROUTER_FORCE_DOCKER_BUNDLING", raising=False)
    monkeypatch.setattr(
        "supportrouter_infra.api_stack.subprocess.run",
        fail_install,
    )
    (tmp_path / "partial-install").write_text("partial", encoding="utf-8")

    assert not ChatRuntimeLocalBundling().try_bundle(str(tmp_path), None)  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == []


def test_each_tool_asset_excludes_sibling_handlers() -> None:
    assert tool_asset_excludes("issue_refund.handler") == [
        "__pycache__",
        "*.pyc",
        "get_order_status.py",
        "initiate_return.py",
    ]


def test_refund_lambda_iam_cannot_write_unrelated_tables(env: cdk.Environment) -> None:
    app = cdk.App()
    stack = ToolsStack(app, "ToolsIam", env=env)
    raw = Template.from_stack(stack).to_json()
    resources = raw["Resources"]

    refund_function = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Lambda::Function"
        and resource["Properties"]["Handler"] == "issue_refund.handler"
    )
    refund_role_id = refund_function["Role"]["Fn::GetAtt"][0]
    refund_policy = next(
        resource["Properties"]["PolicyDocument"]
        for resource in resources.values()
        if resource["Type"] == "AWS::IAM::Policy"
        and {"Ref": refund_role_id} in resource["Properties"]["Roles"]
    )
    statements = refund_policy["Statement"]
    dynamodb_statements = [
        statement
        for statement in statements
        if any(
            str(action).startswith("dynamodb:")
            for action in (
                statement["Action"]
                if isinstance(statement["Action"], list)
                else [statement["Action"]]
            )
        )
    ]

    assert {
        tuple(
            action
            if isinstance(action, list)
            else [action]
        )
        for action in [statement["Action"] for statement in dynamodb_statements]
    } == {("dynamodb:GetItem",), ("dynamodb:PutItem",)}

    write_statement = next(
        statement
        for statement in dynamodb_statements
        if statement["Action"] == "dynamodb:PutItem"
    )
    write_resources = (
        write_statement["Resource"]
        if isinstance(write_statement["Resource"], list)
        else [write_statement["Resource"]]
    )
    assert len(write_resources) == 1
    write_table_id = write_resources[0]["Fn::GetAtt"][0]
    assert "RefundRequests" in write_table_id
    assert "Orders" not in write_table_id
    assert "Returns" not in write_table_id

    serialized = json.dumps(refund_policy)
    assert '"dynamodb:*"' not in serialized
    assert '"Resource": "*"' not in serialized


@pytest.mark.parametrize(
    ("handler", "read_table_fragments", "write_table_fragment"),
    [
        ("get_order_status.handler", {"Orders"}, None),
        ("initiate_return.handler", {"Orders", "Returns"}, "Returns"),
        (
            "issue_refund.handler",
            {"Orders", "RefundRequests"},
            "RefundRequests",
        ),
    ],
)
def test_each_tool_role_has_only_its_required_write_target(
    env: cdk.Environment,
    handler: str,
    read_table_fragments: set[str],
    write_table_fragment: str | None,
) -> None:
    app = cdk.App()
    stack_name = handler.split(".")[0].replace("_", "-")
    stack = ToolsStack(app, f"Tools-{stack_name}", env=env)
    resources = Template.from_stack(stack).to_json()["Resources"]
    function = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Lambda::Function"
        and resource["Properties"]["Handler"] == handler
    )
    role_id = function["Role"]["Fn::GetAtt"][0]
    policy = next(
        resource["Properties"]["PolicyDocument"]
        for resource in resources.values()
        if resource["Type"] == "AWS::IAM::Policy"
        and {"Ref": role_id} in resource["Properties"]["Roles"]
    )
    log_statements = [
        statement
        for statement in policy["Statement"]
        if any(
            str(action).startswith("logs:")
            for action in (
                statement["Action"]
                if isinstance(statement["Action"], list)
                else [statement["Action"]]
            )
        )
    ]
    assert len(log_statements) == 1
    log_actions = log_statements[0]["Action"]
    if not isinstance(log_actions, list):
        log_actions = [log_actions]
    assert set(log_actions) == {"logs:CreateLogStream", "logs:PutLogEvents"}
    log_resources = log_statements[0]["Resource"]
    if not isinstance(log_resources, list):
        log_resources = [log_resources]
    assert len(log_resources) == 2
    assert all(resource != "*" for resource in log_resources)

    write_statements = [
        statement
        for statement in policy["Statement"]
        if statement["Action"] == "dynamodb:PutItem"
    ]
    read_statements = [
        statement
        for statement in policy["Statement"]
        if statement["Action"] == "dynamodb:GetItem"
    ]
    assert len(read_statements) == 1
    read_resources = read_statements[0]["Resource"]
    if not isinstance(read_resources, list):
        read_resources = [read_resources]
    read_table_ids = {
        resource["Fn::GetAtt"][0]
        for resource in read_resources
    }
    assert all(
        any(fragment in table_id for table_id in read_table_ids)
        for fragment in read_table_fragments
    )
    assert len(read_table_ids) == len(read_table_fragments)

    serialized = json.dumps(policy)
    for forbidden_action in (
        "dynamodb:BatchWriteItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:UpdateItem",
    ):
        assert forbidden_action not in serialized

    if write_table_fragment is None:
        assert write_statements == []
        return
    assert len(write_statements) == 1
    resources_for_write = write_statements[0]["Resource"]
    if not isinstance(resources_for_write, list):
        resources_for_write = [resources_for_write]
    assert len(resources_for_write) == 1
    assert write_table_fragment in resources_for_write[0]["Fn::GetAtt"][0]
