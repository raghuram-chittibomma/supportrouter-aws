"""Tests for deterministic classifier stub."""

from supportrouter.classifier import classify


def test_order_status_with_order_id():
    result = classify("Where is my order #VE-1001?")
    assert result.task_type == "order_status"
    assert result.confidence >= 0.85


def test_refund_keywords():
    result = classify("I want a refund for my TypeCraft 87")
    assert result.task_type == "refund_request"


def test_product_compatibility():
    result = classify("Will this dock work with my laptop?")
    assert result.task_type == "product_question"


def test_empty_message():
    result = classify("  ")
    assert result.task_type == "unknown"
    assert result.confidence == 0.0
