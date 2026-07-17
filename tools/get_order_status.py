"""Read-only Lambda tool for one synthetic VoltEdge order."""

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
    return {
        "ok": True,
        "order_id": order["order_id"],
        "status": order["status"],
        "tracking_number": order.get("tracking_number"),
        "items": _shared.json_safe(order.get("items", [])),
    }
