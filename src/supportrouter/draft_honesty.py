"""Keep refund/return drafts honest about synthetic non-execution (#73)."""

from __future__ import annotations

import re
from typing import Any

# Phrases that overclaim payment rails or post-execution timelines.
_OVERCLAIM_RE = re.compile(
    "|".join(
        (
            r"\b(?:has been|have been|was|were)\s+processed\b",
            r"\brefund has been processed\b",
            r"\bprocessed and is ready\b",
            r"\b\d+\s*[-–]\s*\d+\s+business days\b",
            r"\bbusiness days\b",
            r"\boriginal payment method\b",
            r"\bfunds will (?:appear|be|return)\b",
            r"\bconfirmation email\b",
            r"(?<!no )payment (?:was|has been) (?:executed|sent|issued)\b",
            r"\bmoney (?:has been|was) (?:refunded|returned)\b",
        )
    ),
    re.IGNORECASE,
)

HONEST_DRAFT_INSTRUCTIONS = (
    "Draft a concise VoltEdge Electronics customer support reply using only "
    "the provided synthetic tool results and citations. Do not invent orders, "
    "policies, or amounts. "
    "When a tool result includes execution_status=not_executed, you must say "
    "the refund/return was prepared or initiated only — never claim payment "
    "was processed, bank timelines (e.g. 3-5 business days), confirmation "
    "emails, or funds returning to a payment method. Prefer the tool message "
    "wording (prepared / not executed / pending approval)."
)


def tool_results_not_executed(tool_calls: list[dict[str, Any]] | None) -> bool:
    for call in tool_calls or []:
        result = call.get("result")
        if isinstance(result, dict) and result.get("execution_status") == "not_executed":
            return True
    return False


def overclaims_execution(text: str) -> bool:
    return bool(_OVERCLAIM_RE.search(text or ""))


def _preferred_tool_message(tool_calls: list[dict[str, Any]] | None) -> str | None:
    for call in tool_calls or []:
        name = call.get("name")
        if name not in {"issue_refund", "initiate_return"}:
            continue
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        if result.get("execution_status") != "not_executed":
            continue
        message = result.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


def enforce_execution_honesty(
    answer: str,
    tool_calls: list[dict[str, Any]] | None,
) -> tuple[str, bool]:
    """Replace overclaiming drafts with tool-backed honest wording.

    Returns (answer, rewritten).
    """
    if not tool_results_not_executed(tool_calls):
        return answer, False
    if not overclaims_execution(answer):
        return answer, False
    preferred = _preferred_tool_message(tool_calls)
    if preferred:
        return preferred, True
    return (
        "A synthetic refund/return was prepared only; no payment was executed "
        "(execution_status=not_executed).",
        True,
    )
