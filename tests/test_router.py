"""Tests for seeded model router."""

from supportrouter.classifier import classify
from supportrouter.router import route


def test_route_order_status_seed():
    decision = route("order_status")
    assert decision.model_id == "amazon.nova-micro"
    assert decision.routing_table_version == "seed-v0.1.0"


def test_classify_then_route_demo_path():
    classification = classify("Where is my order #VE-1001?")
    decision = route(classification.task_type)
    assert classification.task_type == "order_status"
    assert decision.model_id == "amazon.nova-micro"
