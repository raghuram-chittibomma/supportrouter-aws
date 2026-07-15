"""Deterministic task-type classifier stub (no LLM)."""

from __future__ import annotations

import re

from supportrouter.schemas import ClassificationResult, TaskType

_ORDER_ID = re.compile(r"\bVE-\d+\b", re.IGNORECASE)

# Ordered rules: first match wins.
_RULES: list[tuple[TaskType, tuple[str, ...], str]] = [
    (
        "refund_request",
        ("refund", "money back", "chargeback"),
        "Matched refund keywords",
    ),
    (
        "return_request",
        ("return", "send back", "rma"),
        "Matched return keywords",
    ),
    (
        "order_status",
        ("order", "tracking", "shipped", "delivery", "where is my"),
        "Matched order/shipping keywords",
    ),
    (
        "product_question",
        ("compatible", "compatibility", "will this", "work with", "setup", "pair"),
        "Matched product/compatibility keywords",
    ),
    (
        "faq_policy",
        ("policy", "warranty", "shipping policy", "how long", "faq"),
        "Matched FAQ/policy keywords",
    ),
]


def classify(message: str) -> ClassificationResult:
    text = (message or "").strip().lower()
    if not text:
        return ClassificationResult("unknown", 0.0, "Empty message")

    for task_type, keywords, rationale in _RULES:
        if any(k in text for k in keywords):
            confidence = 0.9 if task_type != "order_status" else (
                0.95 if _ORDER_ID.search(message) else 0.85
            )
            return ClassificationResult(task_type, confidence, rationale)

    if _ORDER_ID.search(message):
        return ClassificationResult(
            "order_status", 0.8, "Order ID present without other strong intent"
        )

    return ClassificationResult("unknown", 0.4, "No keyword rule matched")
