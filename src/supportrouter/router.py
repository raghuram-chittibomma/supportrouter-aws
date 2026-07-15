"""Deterministic model router over a seeded routing table."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from supportrouter.schemas import RoutingDecision, TaskType

_DEFAULT_TABLE = Path(__file__).resolve().parents[2] / "data" / "sample" / "routing_table.json"


@lru_cache(maxsize=1)
def _load_table(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def route(task_type: TaskType, table_path: Path | None = None) -> RoutingDecision:
    path = table_path or _DEFAULT_TABLE
    table = _load_table(str(path))
    version = table.get("routing_table_version", "unknown")
    entries = table.get("routes", {})
    entry = entries.get(task_type) or entries.get("unknown")
    if entry is None:
        raise KeyError(f"No routing entry for task_type={task_type}")
    return RoutingDecision(
        task_type=task_type,
        model_id=entry["model_id"],
        routing_table_version=version,
    )
