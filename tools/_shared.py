"""Shared DynamoDB and validation helpers for Lambda tool handlers."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

ORDER_ID_PATTERN = re.compile(r"^VE-\d{4}$", re.IGNORECASE)


def order_id_from_event(event: Any) -> str:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    order_id = event.get("order_id")
    if not isinstance(order_id, str) or not ORDER_ID_PATTERN.fullmatch(order_id.strip()):
        raise ValueError("order_id must match VE-####")
    return order_id.strip().upper()


def table_from_env(variable_name: str):
    table_name = os.environ.get(variable_name)
    if not table_name:
        raise RuntimeError(f"{variable_name} is not configured")
    import boto3

    return boto3.resource("dynamodb").Table(table_name)


def get_order(order_id: str) -> dict[str, Any] | None:
    response = table_from_env("ORDERS_TABLE_NAME").get_item(
        Key={"order_id": order_id},
        ConsistentRead=True,
        ProjectionExpression=(
            "#order_id, #status, tracking_number, items, "
            "refund_eligible, refund_amount_usd"
        ),
        ExpressionAttributeNames={
            "#order_id": "order_id",
            "#status": "status",
        },
    )
    return response.get("Item")


def put_once(
    *,
    table_env: str,
    item: dict[str, Any],
    key_name: str,
) -> tuple[dict[str, Any], bool]:
    """Conditionally persist one request and return the existing item on retries."""
    table = table_from_env(table_env)
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(#pk)",
            ExpressionAttributeNames={"#pk": key_name},
        )
        return item, True
    except Exception as exc:
        error_code = (
            getattr(exc, "response", {}).get("Error", {}).get("Code")
        )
        if error_code != "ConditionalCheckFailedException":
            raise
        existing = table.get_item(
            Key={key_name: item[key_name]},
            ConsistentRead=True,
        ).get("Item")
        if existing is None:
            raise RuntimeError("conditional write failed but existing item was absent") from exc
        return existing, False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def invalid_request(exc: ValueError) -> dict[str, Any]:
    return {"ok": False, "error": str(exc)}


def order_not_found(order_id: str) -> dict[str, Any]:
    return {"ok": False, "error": f"Order {order_id} not found"}


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value
