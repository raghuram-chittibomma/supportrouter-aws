"""Shared schemas for sessions, routing, and classification (first slice)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskType = Literal[
    "faq_policy",
    "order_status",
    "return_request",
    "refund_request",
    "product_question",
    "unknown",
]


@dataclass(frozen=True)
class ClassificationResult:
    task_type: TaskType
    confidence: float
    rationale: str


@dataclass(frozen=True)
class RoutingDecision:
    task_type: TaskType
    model_id: str
    routing_table_version: str


@dataclass
class SessionRecord:
    session_id: str
    message: str
    task_type: TaskType | None = None
    model_id: str | None = None
    status: str = "open"
    confidence: float | None = None
    citations: list[dict] = field(default_factory=list)
