"""Shared dormancy / cost constants (ADR-007, ADR-008)."""

from __future__ import annotations

PROJECT_NAME = "supportrouter"
LOG_RETENTION_DAYS = 14  # ADR-008: 7–14 days; default 14
MONTHLY_BUDGET_USD = 20
MAX_DASHBOARDS = 3
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024
