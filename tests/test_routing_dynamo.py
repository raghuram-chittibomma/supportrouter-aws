"""Tests for DynamoDB RoutingTable publish/lookup (#88 / ADR-023)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from supportrouter.router import clear_route_cache, route
from supportrouter.routing_dynamo import get_route_item, publish_routing_table


class FakeDynamoClient:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.put_calls = 0
        self.get_calls = 0

    def put_item(self, *, TableName: str, Item: dict[str, Any]) -> dict[str, Any]:
        self.put_calls += 1
        key = Item["task_type"]["S"]
        self.items[key] = Item
        return {}

    def get_item(
        self,
        *,
        TableName: str,
        Key: dict[str, Any],
        ConsistentRead: bool = False,
    ) -> dict[str, Any]:
        self.get_calls += 1
        key = Key["task_type"]["S"]
        item = self.items.get(key)
        return {"Item": item} if item else {}


def _sample_table() -> dict[str, Any]:
    return {
        "routing_table_version": "generated-from-test",
        "routes": {
            "order_status": {
                "model_id": "amazon.nova-micro",
                "quality_score": 1.0,
                "cost_per_1k_tokens": 0.000035,
                "p95_latency_ms": 900,
            },
            "unknown": {
                "model_id": "anthropic.claude-haiku",
                "quality_score": 0.7,
                "cost_per_1k_tokens": 0.001,
                "p95_latency_ms": 1300,
            },
        },
    }


def test_publish_and_get_round_trip(monkeypatch):
    client = FakeDynamoClient()
    monkeypatch.setenv("SUPPORTROUTER_ROUTING_TABLE_NAME", "supportrouter-routingtable")
    summary = publish_routing_table(
        _sample_table(),
        client=client,
        table_name="supportrouter-routingtable",
    )
    assert summary["routing_table_version"] == "generated-from-test"
    assert summary["task_types"] == ["order_status", "unknown"]
    assert client.put_calls == 2

    item = get_route_item("order_status", client=client)
    assert item is not None
    assert item["model_id"] == "amazon.nova-micro"
    assert item["routing_table_version"] == "generated-from-test"


def test_route_uses_dynamo_when_env_set(monkeypatch):
    client = FakeDynamoClient()
    monkeypatch.setenv("SUPPORTROUTER_ROUTING_TABLE_NAME", "supportrouter-routingtable")
    publish_routing_table(_sample_table(), client=client)
    clear_route_cache()

    decision = route("order_status", dynamo_client=client)
    assert decision.model_id == "amazon.nova-micro"
    assert decision.routing_table_version == "generated-from-test"

    missing = route("product_question", dynamo_client=client)
    assert missing.model_id == "anthropic.claude-haiku"


def test_route_file_fallback_when_env_unset(monkeypatch):
    monkeypatch.delenv("SUPPORTROUTER_ROUTING_TABLE_NAME", raising=False)
    clear_route_cache()
    decision = route("order_status")
    assert decision.model_id == "amazon.nova-micro"
    assert "generated-from-scorecard" in decision.routing_table_version
