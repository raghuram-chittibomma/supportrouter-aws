"""Lambda tool that prepares, but never executes, a synthetic refund."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

try:
    from . import _shared
except ImportError:  # Lambda asset root imports this module directly
    import _shared

REFUND_HITL_THRESHOLD_USD = Decimal("100.00")


def handler(event: Any, context: Any) -> dict[str, Any]:
    del context
    try:
        order_id = _shared.order_id_from_event(event)
    except ValueError as exc:
        return _shared.invalid_request(exc)

    order = _shared.get_order(order_id)
    if order is None:
        return _shared.order_not_found(order_id)
    if not order.get("refund_eligible"):
        return {"ok": False, "error": f"Order {order_id} is not refund-eligible"}

    amount = Decimal(str(order.get("refund_amount_usd") or "0")).quantize(
        Decimal("0.01")
    )
    requires_approval = amount > REFUND_HITL_THRESHOLD_USD
    refund_id = f"REFUND-{order_id}"
    stored, created = _shared.put_once(
        table_env="REFUNDS_TABLE_NAME",
        key_name="refund_id",
        item={
            "refund_id": refund_id,
            "order_id": order_id,
            "amount_usd": amount,
            "requires_approval": requires_approval,
            "status": "pending_approval" if requires_approval else "prepared",
            "execution_status": "not_executed",
            "created_at": _shared.utc_now(),
        },
    )
    try:
        stored_amount = Decimal(str(stored.get("amount_usd"))).quantize(
            Decimal("0.01")
        )
    except (InvalidOperation, TypeError, ValueError):
        return {
            "ok": False,
            "error": "Stored refund request failed integrity validation",
        }
    expected_status = "pending_approval" if requires_approval else "prepared"
    if (
        stored.get("refund_id") != refund_id
        or stored.get("order_id") != order_id
        or stored_amount != amount
        or not isinstance(stored.get("requires_approval"), bool)
        or stored.get("requires_approval") is not requires_approval
        or stored.get("status") != expected_status
        or stored.get("execution_status") != "not_executed"
    ):
        return {
            "ok": False,
            "error": "Stored refund request failed integrity validation",
        }
    return {
        "ok": True,
        "order_id": order_id,
        "refund_id": stored["refund_id"],
        "amount_usd": float(stored_amount),
        "requires_approval": requires_approval,
        "status": stored["status"],
        "execution_status": "not_executed",
        "idempotent_replay": not created,
        "message": (
            (
                f"Refund of ${stored_amount:.2f} prepared (synthetic); "
                "requires supervisor approval; no payment was executed"
            )
            if stored["requires_approval"]
            else (
                f"Refund of ${stored_amount:.2f} prepared (synthetic); "
                "no payment was executed"
            )
        ),
    }
