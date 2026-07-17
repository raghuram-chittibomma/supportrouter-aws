"""Lambda tool that creates an idempotent synthetic return request."""

from __future__ import annotations

from typing import Any

try:
    from . import _shared
except ImportError:  # Lambda asset root imports this module directly
    import _shared


def handler(event: Any, context: Any) -> dict[str, Any]:
    del context
    try:
        order_id = _shared.order_id_from_event(event)
    except ValueError as exc:
        return _shared.invalid_request(exc)

    order = _shared.get_order(order_id)
    if order is None:
        return _shared.order_not_found(order_id)
    if order.get("status") not in {"delivered", "shipped"}:
        return {
            "ok": False,
            "error": (
                f"Order {order_id} status '{order.get('status')}' "
                "is not return-eligible"
            ),
        }

    return_id = f"RMA-{order_id}"
    stored, created = _shared.put_once(
        table_env="RETURNS_TABLE_NAME",
        key_name="return_id",
        item={
            "return_id": return_id,
            "order_id": order_id,
            "status": "initiated",
            "created_at": _shared.utc_now(),
            "execution_status": "not_executed",
        },
    )
    return {
        "ok": True,
        "order_id": order_id,
        "rma_id": stored["return_id"],
        "status": stored["status"],
        "execution_status": stored["execution_status"],
        "idempotent_replay": not created,
        "message": "Return initiated (synthetic). Ship unused item within 30 days.",
    }
