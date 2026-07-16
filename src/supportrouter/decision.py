"""Deterministic confidence and HITL helpers."""

from __future__ import annotations

from supportrouter.tools_local import REFUND_HITL_THRESHOLD_USD

LOW_CONFIDENCE_THRESHOLD = 0.55


def score_confidence(
    *,
    classifier_confidence: float,
    task_type: str,
    citations: list,
    tool_calls: list,
) -> float:
    """Combine classifier confidence with retrieval/tool success signals."""
    score = float(classifier_confidence)
    if task_type in ("faq_policy", "product_question"):
        score = min(score, 0.95 if citations else 0.45)
    if task_type in ("order_status", "return_request", "refund_request"):
        ok = any(t.get("result", {}).get("ok") for t in tool_calls)
        score = min(score, 0.95 if ok else 0.35)
    if task_type == "unknown":
        score = min(score, 0.4)
    return round(max(0.0, min(1.0, score)), 3)


def hitl_decision(
    *,
    task_type: str,
    confidence: float,
    refund_amount_usd: float | None,
) -> tuple[str, str | None]:
    """Return (status, reason). Deterministic refund threshold + low-confidence escalate."""
    if (
        task_type == "refund_request"
        and refund_amount_usd is not None
        and refund_amount_usd > REFUND_HITL_THRESHOLD_USD
    ):
        return (
            "pending_approval",
            f"Refund ${refund_amount_usd:.2f} exceeds ${REFUND_HITL_THRESHOLD_USD:.0f} threshold",
        )
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return ("escalated", f"Confidence {confidence:.2f} below {LOW_CONFIDENCE_THRESHOLD:.2f}")
    return ("resolved", None)
