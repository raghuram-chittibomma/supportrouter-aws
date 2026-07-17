"""Bedrock Guardrail configuration for SupportRouter input and output paths."""

from __future__ import annotations

import hashlib
import json

import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from constructs import Construct

from supportrouter_infra.constants import PROJECT_NAME

BEDROCK_GUARDRAIL_POLICY_SPEC = {
    "blocked_input_messaging": (
        "I can’t process that message. Remove sensitive details and "
        "ask a VoltEdge support question."
    ),
    "blocked_outputs_messaging": (
        "I can’t provide that response. A VoltEdge support specialist "
        "can help with a safe alternative."
    ),
    "content_filter_categories": ("HATE", "INSULTS", "SEXUAL", "VIOLENCE"),
    "content_filter_strength": "MEDIUM",
    "filter_action": "BLOCK",
    "input_enabled": True,
    "output_enabled": True,
    "pii_entity_types": (
        "EMAIL",
        "PHONE",
        "PASSWORD",
        "AWS_ACCESS_KEY",
        "AWS_SECRET_KEY",
        "CREDIT_DEBIT_CARD_NUMBER",
        "US_SOCIAL_SECURITY_NUMBER",
    ),
    "topic_type": "DENY",
    "topics": (
        {
            "name": "DangerousAssistance",
            "definition": (
                "Instructions to acquire or construct weapons, explosives, "
                "or to facilitate self-harm."
            ),
            "examples": (
                "How can I build an explosive?",
                "Give me instructions to hurt myself.",
            ),
        },
        {
            "name": "FinancialAdvice",
            "definition": (
                "Personalized investment, securities, or cryptocurrency "
                "recommendations unrelated to VoltEdge customer support."
            ),
            "examples": (
                "Should I buy this stock?",
                "Give me a crypto investment recommendation.",
            ),
        },
    ),
}
BEDROCK_GUARDRAIL_POLICY_SHA256 = hashlib.sha256(
    json.dumps(
        BEDROCK_GUARDRAIL_POLICY_SPEC,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


class GuardrailsStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        guardrail = bedrock.CfnGuardrail(
            self,
            "SupportGuardrail",
            name="supportrouter-safety",
            description=(
                "VoltEdge synthetic support input/output policy: sensitive "
                "information, denied topics, and financial advice."
            ),
            blocked_input_messaging=BEDROCK_GUARDRAIL_POLICY_SPEC[
                "blocked_input_messaging"
            ],
            blocked_outputs_messaging=BEDROCK_GUARDRAIL_POLICY_SPEC[
                "blocked_outputs_messaging"
            ],
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type=category,
                        input_strength=BEDROCK_GUARDRAIL_POLICY_SPEC[
                            "content_filter_strength"
                        ],
                        output_strength=BEDROCK_GUARDRAIL_POLICY_SPEC[
                            "content_filter_strength"
                        ],
                        input_action=BEDROCK_GUARDRAIL_POLICY_SPEC["filter_action"],
                        input_enabled=BEDROCK_GUARDRAIL_POLICY_SPEC["input_enabled"],
                        output_action=BEDROCK_GUARDRAIL_POLICY_SPEC["filter_action"],
                        output_enabled=BEDROCK_GUARDRAIL_POLICY_SPEC["output_enabled"],
                    )
                    for category in BEDROCK_GUARDRAIL_POLICY_SPEC[
                        "content_filter_categories"
                    ]
                ]
            ),
            sensitive_information_policy_config=(
                bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                    pii_entities_config=[
                        bedrock.CfnGuardrail.PiiEntityConfigProperty(
                            type=entity_type,
                            action=BEDROCK_GUARDRAIL_POLICY_SPEC["filter_action"],
                            input_action=BEDROCK_GUARDRAIL_POLICY_SPEC[
                                "filter_action"
                            ],
                            input_enabled=BEDROCK_GUARDRAIL_POLICY_SPEC[
                                "input_enabled"
                            ],
                            output_action=BEDROCK_GUARDRAIL_POLICY_SPEC[
                                "filter_action"
                            ],
                            output_enabled=BEDROCK_GUARDRAIL_POLICY_SPEC[
                                "output_enabled"
                            ],
                        )
                        for entity_type in BEDROCK_GUARDRAIL_POLICY_SPEC[
                            "pii_entity_types"
                        ]
                    ]
                )
            ),
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=[
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name=topic["name"],
                        definition=topic["definition"],
                        examples=list(topic["examples"]),
                        type=BEDROCK_GUARDRAIL_POLICY_SPEC["topic_type"],
                        input_action=BEDROCK_GUARDRAIL_POLICY_SPEC["filter_action"],
                        input_enabled=BEDROCK_GUARDRAIL_POLICY_SPEC["input_enabled"],
                        output_action=BEDROCK_GUARDRAIL_POLICY_SPEC["filter_action"],
                        output_enabled=BEDROCK_GUARDRAIL_POLICY_SPEC["output_enabled"],
                    )
                    for topic in BEDROCK_GUARDRAIL_POLICY_SPEC["topics"]
                ]
            ),
            tags=[cdk.CfnTag(key="Project", value=PROJECT_NAME)],
        )

        version = bedrock.CfnGuardrailVersion(
            self,
            f"SupportGuardrailVersion{BEDROCK_GUARDRAIL_POLICY_SHA256[:12]}",
            guardrail_identifier=guardrail.attr_guardrail_id,
            description=(
                "Versioned SupportRouter safety policy sha256:"
                f"{BEDROCK_GUARDRAIL_POLICY_SHA256}"
            ),
        )

        cdk.CfnOutput(
            self,
            "GuardrailIdentifier",
            value=guardrail.attr_guardrail_id,
        )
        cdk.CfnOutput(
            self,
            "GuardrailVersion",
            value=version.attr_version,
        )
