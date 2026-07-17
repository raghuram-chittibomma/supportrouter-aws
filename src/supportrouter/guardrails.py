"""Deterministic local guardrail policy mirroring the future Bedrock boundary."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

LOCAL_GUARDRAIL_IDENTIFIER = "supportrouter-local-guardrail"
LOCAL_GUARDRAIL_VERSION = "local-v0.1"
LOCAL_POLICY_CAPABILITIES = frozenset(
    {
        "pii",
        "dangerous_assistance",
        "self_harm_assistance",
        "financial_advice",
    }
)

GuardrailAction = Literal["allowed", "blocked", "skipped"]
GuardrailStage = Literal["input", "output"]

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_US_SSN_DASHED = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_US_SSN_UNDASHED = re.compile(
    r"\b(?:ssn|social\s+security(?:\s+number)?)\b.{0,20}\b\d{9}\b",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")

_DENIED_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "dangerous_assistance",
        re.compile(
            r"(?:\b(?:build|make|assemble|buy)\b.{0,30}\b"
            r"(?:bomb|explosive|weapon|gun)\b|"
            r"\b(?:bomb|explosive|weapon)\b.{0,20}\b"
            r"(?:making|guide|instructions?)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "self_harm_assistance",
        re.compile(
            r"(?:\b(?:how|ways?|instructions?|methods?)\b.{0,30})?"
            r"\b(?:kill|hurt|harm)\s+(?:myself|yourself)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "financial_advice",
        re.compile(
            r"(?:\bshould\s+i\s+(?:buy|sell|invest)\b|"
            r"\b(?:buy|sell|purchas(?:e|ing)|invest\s+in|recommend|"
            r"consider\s+(?:buying|purchasing))\b.{0,30}\b"
            r"(?:stocks?|shares?|crypto|bitcoin)\b|"
            r"\b(?:stocks?|shares?|crypto)\b.{0,20}\b"
            r"(?:recommendation|advice)\b|\bfinancial\s+advice\b)",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class GuardrailAssessment:
    stage: GuardrailStage
    action: GuardrailAction
    categories: tuple[str, ...]
    guardrail_identifier: str = LOCAL_GUARDRAIL_IDENTIFIER
    guardrail_version: str = LOCAL_GUARDRAIL_VERSION
    provider: str = "local_deterministic"

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["categories"] = list(self.categories)
        return result


def assess_text(text: str, *, stage: GuardrailStage) -> GuardrailAssessment:
    """Classify high-risk PII and denied topics without retaining matched text."""
    normalized = text or ""
    categories: list[str] = []

    if _EMAIL.search(normalized):
        categories.append("pii_email")
    if _US_SSN_DASHED.search(normalized) or _US_SSN_UNDASHED.search(normalized):
        categories.append("pii_us_ssn")
    if _PHONE.search(normalized):
        categories.append("pii_phone")
    if _AWS_ACCESS_KEY.search(normalized):
        categories.append("pii_aws_access_key")
    if any(_luhn_valid(match.group()) for match in _CARD_CANDIDATE.finditer(normalized)):
        categories.append("pii_payment_card")

    for category, pattern in _DENIED_TOPIC_PATTERNS:
        if pattern.search(normalized):
            categories.append(category)

    return GuardrailAssessment(
        stage=stage,
        action="blocked" if categories else "allowed",
        categories=tuple(categories),
    )


def skipped_assessment(*, stage: GuardrailStage) -> GuardrailAssessment:
    return GuardrailAssessment(stage=stage, action="skipped", categories=())


def blocked_message(
    *,
    stage: GuardrailStage,
    categories: tuple[str, ...] = (),
) -> str:
    if "self_harm_assistance" in categories:
        return (
            "I can’t help with self-harm instructions. If you may be in "
            "immediate danger, contact local emergency services or a trusted "
            "person now."
        )
    if stage == "input":
        return (
            "I can’t process that message because it may contain sensitive "
            "information or a denied topic. Remove sensitive details and ask "
            "a VoltEdge support question."
        )
    return (
        "I can’t provide that response. A VoltEdge support specialist can "
        "help with a safe alternative."
    )


def _luhn_valid(candidate: str) -> bool:
    digits = [int(char) for char in candidate if char.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0
