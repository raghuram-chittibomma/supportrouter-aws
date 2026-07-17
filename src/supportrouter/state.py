"""Typed LangGraph state for the SupportRouter runtime agent."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from supportrouter.schemas import TaskType

OutcomeStatus = Literal[
    "open",
    "resolved",
    "escalated",
    "pending_approval",
    "rejected",
]


class AgentState(TypedDict):
    session_id: str
    message: str
    correlation_id: NotRequired[str | None]
    task_type: NotRequired[TaskType | None]
    model_id: NotRequired[str | None]
    routing_table_version: NotRequired[str | None]
    classifier_rationale: NotRequired[str | None]
    classifier_confidence: NotRequired[float | None]
    citations: NotRequired[list[dict[str, Any]]]
    tool_calls: NotRequired[list[dict[str, Any]]]
    answer: NotRequired[str | None]
    confidence: NotRequired[float | None]
    status: NotRequired[OutcomeStatus]
    hitl_reason: NotRequired[str | None]
    refund_amount_usd: NotRequired[float | None]
    notes: NotRequired[list[str]]
    error: NotRequired[str | None]
