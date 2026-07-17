"""Local synthetic order tools (stand-ins for Lambda tools)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_ORDERS_PATH = Path(__file__).resolve().parents[2] / "data" / "sample" / "orders.json"
_ORDER_ID_RE = re.compile(r"\bVE-\d+\b", re.IGNORECASE)

REFUND_HITL_THRESHOLD_USD = 100.0


@lru_cache(maxsize=1)
def _orders() -> dict[str, dict[str, Any]]:
    data = json.loads(_ORDERS_PATH.read_text(encoding="utf-8"))
    return {o["order_id"].upper(): o for o in data["orders"]}


def extract_order_id(message: str) -> str | None:
    match = _ORDER_ID_RE.search(message or "")
    return match.group(0).upper() if match else None


def get_order_status(order_id: str) -> dict[str, Any]:
    order = _orders().get(order_id.upper())
    if order is None:
        return {"ok": False, "error": f"Order {order_id} not found"}
    return {
        "ok": True,
        "order_id": order["order_id"],
        "status": order["status"],
        "tracking_number": order.get("tracking_number"),
        "items": order.get("items", []),
    }


def initiate_return(order_id: str) -> dict[str, Any]:
    order = _orders().get(order_id.upper())
    if order is None:
        return {"ok": False, "error": f"Order {order_id} not found"}
    if order["status"] not in ("delivered", "shipped"):
        return {
            "ok": False,
            "error": f"Order {order_id} status '{order['status']}' is not return-eligible",
        }
    return {
        "ok": True,
        "order_id": order["order_id"],
        "rma_id": f"RMA-{order['order_id']}",
        "status": "initiated",
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": "Return initiated (synthetic). Ship unused item within 30 days.",
    }


def issue_refund(order_id: str) -> dict[str, Any]:
    order = _orders().get(order_id.upper())
    if order is None:
        return {"ok": False, "error": f"Order {order_id} not found"}
    if not order.get("refund_eligible"):
        return {"ok": False, "error": f"Order {order_id} is not refund-eligible"}
    amount = float(order.get("refund_amount_usd") or 0)
    return {
        "ok": True,
        "order_id": order["order_id"],
        "refund_id": f"REFUND-{order['order_id']}",
        "amount_usd": amount,
        "requires_approval": amount > REFUND_HITL_THRESHOLD_USD,
        "status": (
            "pending_approval"
            if amount > REFUND_HITL_THRESHOLD_USD
            else "prepared"
        ),
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": (
            (
                f"Refund of ${amount:.2f} prepared (synthetic); "
                "requires supervisor approval; no payment was executed"
            )
            if amount > REFUND_HITL_THRESHOLD_USD
            else (
                f"Refund of ${amount:.2f} prepared (synthetic); "
                "no payment was executed"
            )
        ),
    }
