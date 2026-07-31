"""DynamoDB RoutingTable access (DATA_MODEL / ADR-023).

Selected when ``SUPPORTROUTER_ROUTING_TABLE_NAME`` is set. Lookup is a single
``GetItem`` by ``task_type`` (no Scan). Publish writes one item per task type.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

ROUTING_TABLE_ENV = "SUPPORTROUTER_ROUTING_TABLE_NAME"


def dynamo_routing_enabled() -> bool:
    return bool(os.environ.get(ROUTING_TABLE_ENV))


def _table_name() -> str:
    name = os.environ.get(ROUTING_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{ROUTING_TABLE_ENV} is required for DynamoDB routing")
    return name


def _client(client: Any | None = None) -> Any:
    if client is not None:
        return client
    import boto3

    return boto3.client("dynamodb")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def get_route_item(
    task_type: str,
    *,
    client: Any | None = None,
    table_name: str | None = None,
) -> dict[str, Any] | None:
    """Return a routing entry dict or None if the item is missing."""
    response = _client(client).get_item(
        TableName=table_name or _table_name(),
        Key={"task_type": {"S": task_type}},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if not item:
        return None
    return {
        "task_type": item["task_type"]["S"],
        "model_id": item["model_id"]["S"],
        "quality_score": float(item["quality_score"]["N"]),
        "cost_per_1k_tokens": float(item["cost_per_1k_tokens"]["N"]),
        "p95_latency_ms": float(item["p95_latency_ms"]["N"]),
        "routing_table_version": item["routing_table_version"]["S"],
        "updated_at": item.get("updated_at", {}).get("S"),
    }


def publish_routing_table(
    table: dict[str, Any],
    *,
    client: Any | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    """PutItem one row per route. Returns publish summary."""
    routes = table.get("routes") or {}
    if not routes:
        raise ValueError("routing table has no routes to publish")
    version = str(table.get("routing_table_version") or "unknown")
    updated_at = _utc_now()
    ddb = _client(client)
    name = table_name or _table_name()
    written: list[str] = []
    for task_type, entry in routes.items():
        if not isinstance(entry, dict) or "model_id" not in entry:
            raise ValueError(f"route {task_type!r} requires model_id")
        ddb.put_item(
            TableName=name,
            Item={
                "task_type": {"S": str(task_type)},
                "model_id": {"S": str(entry["model_id"])},
                "quality_score": {"N": str(_decimal(entry.get("quality_score", 0)))},
                "cost_per_1k_tokens": {
                    "N": str(_decimal(entry.get("cost_per_1k_tokens", 0)))
                },
                "p95_latency_ms": {"N": str(_decimal(entry.get("p95_latency_ms", 0)))},
                "routing_table_version": {"S": version},
                "updated_at": {"S": updated_at},
            },
        )
        written.append(str(task_type))
    return {
        "table_name": name,
        "routing_table_version": version,
        "task_types": sorted(written),
        "updated_at": updated_at,
    }
