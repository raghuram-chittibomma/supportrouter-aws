"""Exact-match unit tests for deterministic local order tools."""

from __future__ import annotations

import pytest

import supportrouter.tools_local as tools_local
from supportrouter.tools_local import (
    REFUND_HITL_THRESHOLD_USD,
    extract_order_id,
    get_order_status,
    initiate_return,
    issue_refund,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Track order ve-1001 please", "VE-1001"),
        ("No order reference here", None),
        ("", None),
    ],
)
def test_extract_order_id(message, expected):
    assert extract_order_id(message) == expected


def test_get_order_status_found():
    assert get_order_status("ve-1001") == {
        "ok": True,
        "order_id": "VE-1001",
        "status": "shipped",
        "tracking_number": "VETRACK-90821",
        "items": [{"sku": "VE-CC-4K", "qty": 1, "line_total_usd": 99.99}],
    }


def test_get_order_status_not_found():
    assert get_order_status("VE-9999") == {
        "ok": False,
        "error": "Order VE-9999 not found",
    }


def test_initiate_return_success():
    assert initiate_return("VE-1002") == {
        "ok": True,
        "order_id": "VE-1002",
        "rma_id": "RMA-VE-1002",
        "status": "initiated",
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": "Return initiated (synthetic). Ship unused item within 30 days.",
    }


def test_initiate_return_not_found():
    assert initiate_return("VE-9999") == {
        "ok": False,
        "error": "Order VE-9999 not found",
    }


def test_initiate_return_rejects_ineligible_status(monkeypatch):
    monkeypatch.setattr(
        tools_local,
        "_orders",
        lambda: {"VE-2000": {"order_id": "VE-2000", "status": "placed"}},
    )

    assert initiate_return("VE-2000") == {
        "ok": False,
        "error": "Order VE-2000 status 'placed' is not return-eligible",
    }


def test_issue_refund_not_found():
    assert issue_refund("VE-9999") == {
        "ok": False,
        "error": "Order VE-9999 not found",
    }


def test_issue_refund_rejects_ineligible_order():
    assert issue_refund("VE-1001") == {
        "ok": False,
        "error": "Order VE-1001 is not refund-eligible",
    }


def test_issue_refund_below_threshold():
    assert issue_refund("VE-1002") == {
        "ok": True,
        "order_id": "VE-1002",
        "refund_id": "REFUND-VE-1002",
        "amount_usd": 89.99,
        "requires_approval": False,
        "status": "prepared",
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": (
            "Refund of $89.99 prepared (synthetic); no payment was executed"
        ),
    }


def test_issue_refund_above_threshold():
    assert issue_refund("VE-1003") == {
        "ok": True,
        "order_id": "VE-1003",
        "refund_id": "REFUND-VE-1003",
        "amount_usd": 159.99,
        "requires_approval": True,
        "status": "pending_approval",
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": (
            "Refund of $159.99 prepared (synthetic); requires supervisor "
            "approval; no payment was executed"
        ),
    }


def test_issue_refund_at_threshold_does_not_require_approval(monkeypatch):
    monkeypatch.setattr(
        tools_local,
        "_orders",
        lambda: {
            "VE-2000": {
                "order_id": "VE-2000",
                "refund_eligible": True,
                "refund_amount_usd": 100.0,
            }
        },
    )

    assert issue_refund("VE-2000") == {
        "ok": True,
        "order_id": "VE-2000",
        "refund_id": "REFUND-VE-2000",
        "amount_usd": 100.0,
        "requires_approval": False,
        "status": "prepared",
        "execution_status": "not_executed",
        "idempotent_replay": False,
        "message": (
            "Refund of $100.00 prepared (synthetic); no payment was executed"
        ),
    }


def test_refund_hitl_threshold_constant():
    assert REFUND_HITL_THRESHOLD_USD == 100.0
