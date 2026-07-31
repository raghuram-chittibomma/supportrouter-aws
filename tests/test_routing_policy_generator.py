"""Tests for offline routing-policy generation (ADR-003 / #84)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.generate_routing_policy import (
    generate_routing_table,
    main,
    select_route,
    validate_scorecard_for_policy,
)
from supportrouter.bedrock_models import to_routing_model_id


def _scorecard_fixture() -> dict:
    """Two models on one task; both at top quality so cheaper micro wins."""
    return {
        "scorecard_id": "scorecard-fixture-routing",
        "execution_mode": "bedrock_converse",
        "incomplete_reasons": [],
        "summary": {
            "candidates_executed": True,
            "judge_completed": True,
        },
        "cost": {"status": "measured", "total_usd": 0.01},
        "results": [
            {
                "task_type": "order_status",
                "requested_model_id": "logical:nova-micro",
                "candidate_executed": True,
                "wall_time_ms": 800,
                "cost_usd": 0.00002,
                "judge": {
                    "status": "completed",
                    "scores": {
                        "faithfulness": 5,
                        "helpfulness": 5,
                        "policy_adherence": 5,
                    },
                },
            },
            {
                "task_type": "order_status",
                "requested_model_id": "logical:nova-lite",
                "candidate_executed": True,
                "wall_time_ms": 900,
                "cost_usd": 0.00005,
                "judge": {
                    "status": "completed",
                    "scores": {
                        "faithfulness": 5,
                        "helpfulness": 5,
                        "policy_adherence": 5,
                    },
                },
            },
        ],
    }


def test_to_routing_model_id_maps_logical_ids():
    assert to_routing_model_id("logical:nova-micro") == "amazon.nova-micro"
    assert to_routing_model_id("us.amazon.nova-lite-v1:0") == "amazon.nova-lite"


def test_validate_refuses_local_stub_without_override():
    bad = {
        "execution_mode": "local_stub",
        "summary": {"candidates_executed": False, "judge_completed": False},
        "cost": {"status": "not_measured"},
        "incomplete_reasons": ["local"],
    }
    with pytest.raises(ValueError, match="incomplete"):
        validate_scorecard_for_policy(bad, allow_incomplete=False)
    validate_scorecard_for_policy(bad, allow_incomplete=True)


def test_select_route_picks_cheapest_within_tolerance():
    chosen = select_route(
        [
            {
                "model_id": "amazon.nova-micro",
                "quality_score": 0.96,
                "mean_cost_usd": 0.00002,
                "cost_per_1k_tokens": 0.000035,
                "p95_latency_ms": 800,
            },
            {
                "model_id": "amazon.nova-lite",
                "quality_score": 1.0,
                "mean_cost_usd": 0.00005,
                "cost_per_1k_tokens": 0.00006,
                "p95_latency_ms": 900,
            },
        ],
        quality_tolerance=0.05,
        p95_latency_cap_ms=12000,
    )
    assert chosen["model_id"] == "amazon.nova-micro"


def test_select_route_skips_model_outside_quality_band():
    chosen = select_route(
        [
            {
                "model_id": "amazon.nova-micro",
                "quality_score": 0.90,
                "mean_cost_usd": 0.00002,
                "cost_per_1k_tokens": 0.000035,
                "p95_latency_ms": 800,
            },
            {
                "model_id": "amazon.nova-lite",
                "quality_score": 1.0,
                "mean_cost_usd": 0.00005,
                "cost_per_1k_tokens": 0.00006,
                "p95_latency_ms": 900,
            },
        ],
        quality_tolerance=0.05,
        p95_latency_cap_ms=12000,
    )
    assert chosen["model_id"] == "amazon.nova-lite"


def test_select_route_excludes_over_latency_cap_when_alternatives_exist():
    chosen = select_route(
        [
            {
                "model_id": "amazon.nova-micro",
                "quality_score": 0.9,
                "mean_cost_usd": 0.00002,
                "cost_per_1k_tokens": 0.000035,
                "p95_latency_ms": 20000,
            },
            {
                "model_id": "amazon.nova-lite",
                "quality_score": 0.91,
                "mean_cost_usd": 0.00005,
                "cost_per_1k_tokens": 0.00006,
                "p95_latency_ms": 1000,
            },
        ],
        p95_latency_cap_ms=12000,
    )
    assert chosen["model_id"] == "amazon.nova-lite"


def test_generate_routing_table_writes_version_and_keeps_seed_gaps(tmp_path: Path):
    scorecard = _scorecard_fixture()
    seed = {
        "routes": {
            "unknown": {
                "model_id": "anthropic.claude-haiku",
                "quality_score": 0.7,
                "cost_per_1k_tokens": 0.001,
                "p95_latency_ms": 1300,
            }
        }
    }
    table = generate_routing_table(scorecard, seed_table=seed)
    assert table["routing_table_version"] == "generated-from-scorecard-fixture-routing"
    assert table["source_scorecard_id"] == "scorecard-fixture-routing"
    assert table["routes"]["order_status"]["model_id"] == "amazon.nova-micro"
    assert table["routes"]["unknown"]["model_id"] == "anthropic.claude-haiku"
    assert "selection" in table

    sc_path = tmp_path / "sc.json"
    out = tmp_path / "routing.json"
    sc_path.write_text(json.dumps(scorecard), encoding="utf-8")
    assert main(["--scorecard", str(sc_path), "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["routes"]["order_status"]["model_id"] == "amazon.nova-micro"
