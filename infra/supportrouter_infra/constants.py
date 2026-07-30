"""Shared dormancy / cost constants (ADR-007, ADR-008)."""

from __future__ import annotations

PROJECT_NAME = "supportrouter"
LOG_RETENTION_DAYS = 14  # ADR-008: 7–14 days; default 14
MONTHLY_BUDGET_USD = 20
MAX_DASHBOARDS = 3
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024

# Stable Lambda names used by Api/Tools stacks and Observability dashboards.
CHAT_FUNCTION_NAME = f"{PROJECT_NAME}-chat"
GET_ORDER_STATUS_FUNCTION_NAME = f"{PROJECT_NAME}-get-order-status"
INITIATE_RETURN_FUNCTION_NAME = f"{PROJECT_NAME}-initiate-return"
ISSUE_REFUND_FUNCTION_NAME = f"{PROJECT_NAME}-issue-refund"
RUNTIME_LAMBDA_NAMES = (
    CHAT_FUNCTION_NAME,
    GET_ORDER_STATUS_FUNCTION_NAME,
    INITIATE_RETURN_FUNCTION_NAME,
    ISSUE_REFUND_FUNCTION_NAME,
)
