"""Deterministic model router over file seed or DynamoDB RoutingTable."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from supportrouter.routing_dynamo import (
    ROUTING_TABLE_ENV,
    dynamo_routing_enabled,
    get_route_item,
)
from supportrouter.schemas import RoutingDecision, TaskType

_DEFAULT_TABLE = (
    Path(__file__).resolve().parents[2] / "data" / "sample" / "routing_table.json"
)


@lru_cache(maxsize=1)
def _load_table(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def clear_route_cache() -> None:
    """Clear file-table cache (tests / after local seed rewrite)."""
    _load_table.cache_clear()


def route(
    task_type: TaskType,
    table_path: Path | None = None,
    *,
    dynamo_client: object | None = None,
) -> RoutingDecision:
    """Resolve ``model_id`` for a task type.

    When ``SUPPORTROUTER_ROUTING_TABLE_NAME`` is set (and no explicit
    ``table_path`` override), lookup uses DynamoDB ``GetItem`` by ``task_type``,
    falling back to the ``unknown`` item. Otherwise the JSON seed file is used.
    """
    if table_path is None and dynamo_routing_enabled():
        return _route_from_dynamo(task_type, client=dynamo_client)

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


def _route_from_dynamo(
    task_type: TaskType,
    *,
    client: object | None = None,
) -> RoutingDecision:
    item = get_route_item(str(task_type), client=client)
    if item is None and task_type != "unknown":
        item = get_route_item("unknown", client=client)
    if item is None:
        raise KeyError(
            f"No DynamoDB routing entry for task_type={task_type} "
            f"(table={os.environ.get(ROUTING_TABLE_ENV)!r})"
        )
    return RoutingDecision(
        task_type=task_type,
        model_id=item["model_id"],
        routing_table_version=item["routing_table_version"],
    )
