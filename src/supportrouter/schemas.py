"""Shared schemas for sessions, routing, and classification (first slice)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

TaskType = Literal[
    "faq_policy",
    "order_status",
    "return_request",
    "refund_request",
    "product_question",
    "unknown",
]

ApprovalStatus = Literal["pending", "approved", "rejected"]
ApprovalExecutionStatus = Literal["not_executed"]


class ApprovalRequest(TypedDict):
    """Local approval contract; DynamoDB persistence lands in the AWS slice."""

    approval_id: str
    session_id: str
    order_id: str
    amount_usd: float
    status: ApprovalStatus
    reason: str
    created_at: str
    updated_at: str
    decided_at: str | None
    decided_by: str | None
    decision_note: str
    version: int
    execution_status: ApprovalExecutionStatus


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
