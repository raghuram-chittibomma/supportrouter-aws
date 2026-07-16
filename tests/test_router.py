"""Tests for seeded model router."""

import json

import pytest

from supportrouter.classifier import classify
from supportrouter.router import route


@pytest.mark.parametrize(
    ("task_type", "model_id"),
    [
        ("faq_policy", "amazon.nova-micro"),
        ("order_status", "amazon.nova-micro"),
        ("return_request", "amazon.nova-lite"),
        ("refund_request", "anthropic.claude-haiku"),
        ("product_question", "amazon.nova-lite"),
        ("unknown", "anthropic.claude-haiku"),
    ],
)
def test_route_all_seeded_task_types(task_type, model_id):
    decision = route(task_type)
    assert decision.task_type == task_type
    assert decision.model_id == model_id
    assert decision.routing_table_version == "seed-v0.1.0"


def test_classify_then_route_demo_path():
    classification = classify("Where is my order #VE-1001?")
    decision = route(classification.task_type)
    assert classification.task_type == "order_status"
    assert decision.model_id == "amazon.nova-micro"


def test_custom_table_falls_back_to_unknown_entry(tmp_path):
    table_path = tmp_path / "routing.json"
    table_path.write_text(
        json.dumps(
            {
                "routing_table_version": "test-v1",
                "routes": {"unknown": {"model_id": "test.fallback"}},
            }
        ),
        encoding="utf-8",
    )

    decision = route("missing", table_path)

    assert decision.task_type == "missing"
    assert decision.model_id == "test.fallback"
    assert decision.routing_table_version == "test-v1"


def test_custom_table_without_matching_or_unknown_entry_raises(tmp_path):
    table_path = tmp_path / "routing.json"
    table_path.write_text(
        json.dumps(
            {
                "routing_table_version": "test-v1",
                "routes": {"faq_policy": {"model_id": "test.faq"}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(KeyError, match="No routing entry for task_type=order_status"):
        route("order_status", table_path)


def test_custom_table_defaults_missing_version_to_unknown(tmp_path):
    table_path = tmp_path / "routing.json"
    table_path.write_text(
        json.dumps({"routes": {"order_status": {"model_id": "test.order"}}}),
        encoding="utf-8",
    )

    decision = route("order_status", table_path)

    assert decision.model_id == "test.order"
    assert decision.routing_table_version == "unknown"
