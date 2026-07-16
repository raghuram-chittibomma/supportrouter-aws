"""Tests for deterministic classifier stub."""

import pytest

from supportrouter.classifier import classify


def test_order_status_with_order_id():
    result = classify("Where is my order #VE-1001?")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("order_status", 0.95, "Matched order/shipping keywords")


def test_order_status_without_order_id():
    result = classify("Where is my delivery?")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("order_status", 0.85, "Matched order/shipping keywords")


def test_order_id_alone_uses_fallback():
    result = classify("VE-1001")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("order_status", 0.8, "Order ID present without other strong intent")


@pytest.mark.parametrize("keyword", ["refund", "money back", "chargeback"])
def test_refund_keywords(keyword):
    result = classify(f"I want a {keyword} for my TypeCraft 87")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("refund_request", 0.9, "Matched refund keywords")


@pytest.mark.parametrize("keyword", ["return", "send back", "rma"])
def test_return_keywords(keyword):
    result = classify(f"Please {keyword} this item")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("return_request", 0.9, "Matched return keywords")


@pytest.mark.parametrize("keyword", ["policy", "warranty", "faq", "how long"])
def test_faq_policy_keywords(keyword):
    result = classify(f"Tell me the {keyword} details")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("faq_policy", 0.9, "Matched FAQ/policy keywords")


def test_product_compatibility():
    result = classify("Will this dock work with my laptop?")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("product_question", 0.9, "Matched product/compatibility keywords")


def test_first_match_refund_wins_over_return_and_order():
    result = classify("Refund and return order VE-1002")
    assert result.task_type == "refund_request"
    assert result.rationale == "Matched refund keywords"


def test_no_match_is_unknown():
    result = classify("blorp zizzle")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("unknown", 0.4, "No keyword rule matched")


def test_empty_message():
    result = classify("  ")
    assert (
        result.task_type,
        result.confidence,
        result.rationale,
    ) == ("unknown", 0.0, "Empty message")
