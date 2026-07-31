"""Generate a routing-table JSON from a measured eval scorecard (ADR-003 / ADR-022).

Offline transform only — does not call Bedrock. Prefer measured live scorecards.

Usage:
  python -m evals.generate_routing_policy \\
    --scorecard evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json \\
    --out /tmp/routing_table.generated.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Sequence

from supportrouter.bedrock_models import (
    published_input_cost_per_1k,
    to_routing_model_id,
)

DEFAULT_QUALITY_TOLERANCE = 0.05  # within 5% of best (ADR-003)
DEFAULT_P95_LATENCY_CAP_MS = 12000.0  # NFR: tools path < 12s
QUALITY_FORMULA = "mean(judge faithfulness/helpfulness/policy_adherence) / 5.0"


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _quality_from_judge(scores: dict[str, Any] | None) -> float | None:
    if not isinstance(scores, dict):
        return None
    dims = []
    for key in ("faithfulness", "helpfulness", "policy_adherence"):
        value = scores.get(key)
        if value is None:
            continue
        dims.append(float(value))
    if not dims:
        return None
    return round(statistics.fmean(dims) / 5.0, 6)


def validate_scorecard_for_policy(
    scorecard: dict[str, Any],
    *,
    allow_incomplete: bool,
) -> None:
    """Raise ValueError when the scorecard is unsafe for ADR-003 selection."""
    summary = scorecard.get("summary") or {}
    reasons: list[str] = []
    if scorecard.get("execution_mode") == "local_stub":
        reasons.append("execution_mode is local_stub (candidates not invoked)")
    if not summary.get("candidates_executed"):
        reasons.append("summary.candidates_executed is false")
    if not summary.get("judge_completed"):
        reasons.append("summary.judge_completed is false")
    cost = scorecard.get("cost") or {}
    if cost.get("status") != "measured":
        reasons.append("cost.status is not measured")
    incomplete = list(scorecard.get("incomplete_reasons") or [])
    if incomplete:
        reasons.append(f"incomplete_reasons={incomplete}")
    if reasons and not allow_incomplete:
        raise ValueError(
            "Scorecard is incomplete for routing-policy generation: "
            + "; ".join(reasons)
            + ". Re-run with a measured live scorecard or pass --allow-incomplete."
        )


def aggregate_candidates(scorecard: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Aggregate results by task_type → candidate metrics."""
    by_task: dict[str, dict[str, dict[str, Any]]] = {}
    for row in scorecard.get("results") or []:
        if not row.get("candidate_executed"):
            continue
        task_type = row.get("task_type")
        requested = row.get("requested_model_id")
        if not isinstance(task_type, str) or not isinstance(requested, str):
            continue
        judge = row.get("judge") or {}
        if judge.get("status") != "completed":
            continue
        quality = _quality_from_judge(judge.get("scores"))
        if quality is None:
            continue
        routing_id = to_routing_model_id(requested)
        bucket = by_task.setdefault(task_type, {}).setdefault(
            routing_id,
            {
                "model_id": routing_id,
                "qualities": [],
                "latencies_ms": [],
                "costs_usd": [],
                "run_count": 0,
            },
        )
        bucket["qualities"].append(quality)
        wall = row.get("wall_time_ms")
        if wall is not None:
            bucket["latencies_ms"].append(float(wall))
        cost = row.get("cost_usd")
        if cost is not None:
            bucket["costs_usd"].append(float(cost))
        bucket["run_count"] += 1

    aggregated: dict[str, list[dict[str, Any]]] = {}
    for task_type, models in by_task.items():
        candidates: list[dict[str, Any]] = []
        for model_id, raw in models.items():
            if not raw["qualities"]:
                continue
            mean_cost = (
                statistics.fmean(raw["costs_usd"]) if raw["costs_usd"] else None
            )
            p95 = (
                _percentile(raw["latencies_ms"], 95.0)
                if raw["latencies_ms"]
                else None
            )
            candidates.append(
                {
                    "model_id": model_id,
                    "quality_score": round(statistics.fmean(raw["qualities"]), 6),
                    "mean_cost_usd": (
                        round(mean_cost, 8) if mean_cost is not None else None
                    ),
                    "cost_per_1k_tokens": published_input_cost_per_1k(model_id),
                    "p95_latency_ms": (
                        round(p95, 3) if p95 is not None else None
                    ),
                    "run_count": raw["run_count"],
                }
            )
        aggregated[task_type] = candidates
    return aggregated


def select_route(
    candidates: Sequence[dict[str, Any]],
    *,
    quality_tolerance: float = DEFAULT_QUALITY_TOLERANCE,
    p95_latency_cap_ms: float = DEFAULT_P95_LATENCY_CAP_MS,
) -> dict[str, Any]:
    """Pick cheapest candidate within quality tolerance under the latency cap."""
    if not candidates:
        raise ValueError("no candidates to select from")
    under_cap = [
        c
        for c in candidates
        if c.get("p95_latency_ms") is not None
        and float(c["p95_latency_ms"]) <= p95_latency_cap_ms
    ]
    pool = under_cap if under_cap else list(candidates)
    best_quality = max(float(c["quality_score"]) for c in pool)
    floor = best_quality * (1.0 - quality_tolerance)
    eligible = [c for c in pool if float(c["quality_score"]) >= floor]
    if not eligible:
        raise ValueError("no candidates within quality tolerance")

    def sort_key(c: dict[str, Any]) -> tuple[float, float, str]:
        cost = c.get("mean_cost_usd")
        if cost is None:
            cost = c.get("cost_per_1k_tokens")
        if cost is None:
            cost = float("inf")
        # Cheapest first; then higher quality; then stable model_id.
        return (float(cost), -float(c["quality_score"]), str(c["model_id"]))

    return sorted(eligible, key=sort_key)[0]


def generate_routing_table(
    scorecard: dict[str, Any],
    *,
    allow_incomplete: bool = False,
    quality_tolerance: float = DEFAULT_QUALITY_TOLERANCE,
    p95_latency_cap_ms: float = DEFAULT_P95_LATENCY_CAP_MS,
    seed_table: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a routing-table document for task types present in the scorecard.

    Task types absent from the scorecard are copied from ``seed_table`` when
    provided (keep-seed-for-missing). Generated routes always overwrite seed
    entries for covered task types.
    """
    validate_scorecard_for_policy(scorecard, allow_incomplete=allow_incomplete)
    scorecard_id = scorecard.get("scorecard_id") or "unknown-scorecard"
    aggregated = aggregate_candidates(scorecard)
    if not aggregated:
        raise ValueError("scorecard has no completed candidate+judge rows to aggregate")

    routes: dict[str, Any] = {}
    selection_notes: list[dict[str, Any]] = []
    for task_type, candidates in sorted(aggregated.items()):
        chosen = select_route(
            candidates,
            quality_tolerance=quality_tolerance,
            p95_latency_cap_ms=p95_latency_cap_ms,
        )
        routes[task_type] = {
            "model_id": chosen["model_id"],
            "quality_score": chosen["quality_score"],
            "cost_per_1k_tokens": chosen["cost_per_1k_tokens"],
            "p95_latency_ms": chosen["p95_latency_ms"],
        }
        selection_notes.append(
            {
                "task_type": task_type,
                "selected": chosen["model_id"],
                "candidates": candidates,
            }
        )

    if seed_table:
        for task_type, entry in (seed_table.get("routes") or {}).items():
            if task_type not in routes:
                routes[task_type] = dict(entry)

    return {
        "routing_table_version": f"generated-from-{scorecard_id}",
        "policy": (
            f"Generated from scorecard {scorecard_id} via ADR-003/ADR-022: "
            f"cheapest model within {quality_tolerance:.0%} of best quality "
            f"({QUALITY_FORMULA}), subject to p95_latency_cap_ms="
            f"{p95_latency_cap_ms:g}. Offline transform; cost not re-measured."
        ),
        "source_scorecard_id": scorecard_id,
        "quality_formula": QUALITY_FORMULA,
        "quality_tolerance": quality_tolerance,
        "p95_latency_cap_ms": p95_latency_cap_ms,
        "selection": selection_notes,
        "routes": routes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--seed",
        type=Path,
        default=None,
        help="Optional seed routing table; missing task types are copied through.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow local-stub / incomplete scorecards (not for release claims).",
    )
    parser.add_argument(
        "--quality-tolerance",
        type=float,
        default=DEFAULT_QUALITY_TOLERANCE,
        help="Max relative quality drop from best (default 0.05 = 5%%).",
    )
    parser.add_argument(
        "--p95-latency-cap-ms",
        type=float,
        default=DEFAULT_P95_LATENCY_CAP_MS,
        help="Drop candidates above this p95 wall time (default 12000).",
    )
    args = parser.parse_args(argv)

    scorecard = json.loads(args.scorecard.read_text(encoding="utf-8"))
    seed = (
        json.loads(args.seed.read_text(encoding="utf-8"))
        if args.seed is not None
        else None
    )
    table = generate_routing_table(
        scorecard,
        allow_incomplete=args.allow_incomplete,
        quality_tolerance=args.quality_tolerance,
        p95_latency_cap_ms=args.p95_latency_cap_ms,
        seed_table=seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(args.out),
                "routing_table_version": table["routing_table_version"],
                "task_types": sorted(table["routes"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
