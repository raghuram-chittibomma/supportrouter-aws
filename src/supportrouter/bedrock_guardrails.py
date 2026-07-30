"""Bedrock ApplyGuardrail adapter for SupportRouter AWS runtime mode (#70)."""

from __future__ import annotations

import os
from typing import Any

from supportrouter.guardrails import (
    GuardrailAssessment,
    GuardrailStage,
)

ENV_GUARDRAIL_ID = "SUPPORTROUTER_GUARDRAIL_ID"
ENV_GUARDRAIL_VERSION = "SUPPORTROUTER_GUARDRAIL_VERSION"


def configured_guardrail_ids() -> tuple[str, str] | None:
    guardrail_id = os.environ.get(ENV_GUARDRAIL_ID, "").strip()
    version = os.environ.get(ENV_GUARDRAIL_VERSION, "").strip()
    if not guardrail_id or not version:
        return None
    return guardrail_id, version


def _client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    import boto3

    return boto3.client("bedrock-runtime")


def _categories_from_assessments(assessments: list[dict[str, Any]]) -> tuple[str, ...]:
    categories: list[str] = []
    for assessment in assessments or []:
        if not isinstance(assessment, dict):
            continue
        topic = assessment.get("topicPolicy") or {}
        for topic_hit in topic.get("topics") or []:
            if topic_hit.get("action") == "BLOCKED" or topic_hit.get("detected"):
                name = str(topic_hit.get("name") or "denied_topic").lower()
                categories.append(f"topic:{name}")
        content = assessment.get("contentPolicy") or {}
        for filt in content.get("filters") or []:
            if filt.get("action") == "BLOCKED" or filt.get("detected"):
                categories.append(
                    f"content:{str(filt.get('type') or 'filter').lower()}"
                )
        sensitive = assessment.get("sensitiveInformationPolicy") or {}
        for entity in sensitive.get("piiEntities") or []:
            if entity.get("action") in {"BLOCKED", "ANONYMIZED"} or entity.get(
                "detected"
            ):
                categories.append(
                    f"pii:{str(entity.get('type') or 'entity').lower()}"
                )
        for regex_hit in sensitive.get("regexes") or []:
            if regex_hit.get("action") in {"BLOCKED", "ANONYMIZED"} or regex_hit.get(
                "detected"
            ):
                categories.append("pii:regex")
        word = assessment.get("wordPolicy") or {}
        for custom in word.get("customWords") or []:
            if custom.get("action") == "BLOCKED" or custom.get("detected"):
                categories.append("word:custom")
        for managed in word.get("managedWordLists") or []:
            if managed.get("action") == "BLOCKED" or managed.get("detected"):
                categories.append(
                    f"word:{str(managed.get('type') or 'managed').lower()}"
                )
    # Dedupe while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for category in categories:
        if category not in seen:
            seen.add(category)
            ordered.append(category)
    return tuple(ordered)


def apply_guardrail(
    text: str,
    *,
    stage: GuardrailStage,
    guardrail_id: str | None = None,
    guardrail_version: str | None = None,
    client: Any | None = None,
) -> GuardrailAssessment:
    """Call Bedrock ApplyGuardrail and map to GuardrailAssessment."""
    configured = configured_guardrail_ids()
    resolved_id = (guardrail_id or "").strip() or (
        configured[0] if configured else ""
    )
    resolved_version = (guardrail_version or "").strip() or (
        configured[1] if configured else ""
    )
    if not resolved_id or not resolved_version:
        return GuardrailAssessment(
            stage=stage,
            action="blocked",
            categories=("guardrail_misconfigured",),
            guardrail_identifier="missing",
            guardrail_version="missing",
            provider="bedrock",
        )

    source = "INPUT" if stage == "input" else "OUTPUT"
    try:
        response = _client(client).apply_guardrail(
            guardrailIdentifier=resolved_id,
            guardrailVersion=resolved_version,
            source=source,
            content=[{"text": {"text": text or ""}}],
        )
    except Exception:  # noqa: BLE001 — fail closed on Bedrock/API errors
        return GuardrailAssessment(
            stage=stage,
            action="blocked",
            categories=("guardrail_unavailable",),
            guardrail_identifier=resolved_id,
            guardrail_version=resolved_version,
            provider="bedrock",
        )
    intervened = response.get("action") == "GUARDRAIL_INTERVENED"
    categories = _categories_from_assessments(list(response.get("assessments") or []))
    if intervened and not categories:
        categories = ("guardrail_intervened",)
    return GuardrailAssessment(
        stage=stage,
        action="blocked" if intervened else "allowed",
        categories=categories,
        guardrail_identifier=resolved_id,
        guardrail_version=resolved_version,
        provider="bedrock",
    )
