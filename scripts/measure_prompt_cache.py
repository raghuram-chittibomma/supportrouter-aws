"""Measure Bedrock prompt-cache hit vs miss cost for the judge prefix (#72).

Runs two Converse calls with the same cacheable judge prefix within TTL:
1) cold write  2) warm read. Writes a scorecard under evals/scorecards/.

Usage:
  python scripts/measure_prompt_cache.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.prompt_cache import judge_cacheable_prefix
from supportrouter.bedrock_converse import converse_text
from supportrouter.bedrock_models import (
    estimate_cost_usd,
    estimate_uncached_equivalent_cost_usd,
)
from supportrouter.prompt_cache import converse_system_with_cache_point

DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "evals" / "scorecards"
)


def _call(
    *,
    model_id: str,
    system: list[dict[str, Any]],
    user: str,
    client: Any | None,
) -> dict[str, Any]:
    return converse_text(
        model_id=model_id,
        system=system,
        user=user,
        max_tokens=64,
        temperature=0.0,
        client=client,
        prompt_cache=True,
    )


def measure(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    client: Any | None = None,
    scorecard_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    prefix = judge_cacheable_prefix()
    system = converse_system_with_cache_point(prefix)
    users = (
        "Return JSON only: {\"ok\": true, \"pass\": 1}",
        "Return JSON only: {\"ok\": true, \"pass\": 2}",
    )
    calls: list[dict[str, Any]] = []
    for index, user in enumerate(users, start=1):
        raw = _call(model_id=model_id, system=system, user=user, client=client)
        usage = raw["usage"]
        measured = estimate_cost_usd(model_id, usage)
        uncached = estimate_uncached_equivalent_cost_usd(model_id, usage)
        calls.append(
            {
                "call_index": index,
                "label": "cold_write" if index == 1 else "warm_read",
                "usage": usage,
                "cost_usd": measured,
                "uncached_equivalent_cost_usd": uncached,
                "stop_reason": raw.get("stop_reason"),
            }
        )

    measured_total = round(sum(float(c["cost_usd"] or 0) for c in calls), 8)
    uncached_total = round(
        sum(float(c["uncached_equivalent_cost_usd"] or 0) for c in calls),
        8,
    )
    savings = round(uncached_total - measured_total, 8)
    read_total = sum(int(c["usage"].get("cache_read_tokens") or 0) for c in calls)
    write_total = sum(int(c["usage"].get("cache_write_tokens") or 0) for c in calls)
    cache_enabled = all(c["usage"].get("cache_enabled") is True for c in calls)
    if read_total > 0 and write_total > 0:
        cache_status = "hit_and_write"
    elif read_total > 0:
        cache_status = "hit"
    elif write_total > 0:
        cache_status = "write"
    else:
        cache_status = "below_minimum"

    return {
        "schema_version": "v0.1-prompt-cache",
        "scorecard_id": scorecard_id
        or f"scorecard-prompt-cache-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "measurement": "judge_prefix_hit_vs_miss",
        "model_id": model_id,
        "cache_enabled": cache_enabled,
        "cache_status": cache_status,
        "cache_read_tokens": read_total,
        "cache_write_tokens": write_total,
        "judge_prompt_cache": {
            "prefix_name": prefix.name,
            "prefix_version": prefix.version,
            "prefix_sha256": prefix.sha256,
        },
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "calls": calls,
        "cache_comparison": {
            "basis": (
                "Two Converse calls sharing the judge cacheable prefix; "
                "measured uses cache read/write rates; uncached-equivalent "
                "prices all input tokens at the full input rate"
            ),
            "measured_cost_usd": measured_total,
            "uncached_equivalent_cost_usd": uncached_total,
            "savings_usd": savings,
            "savings_pct": (
                round((savings / uncached_total) * 100.0, 4)
                if uncached_total > 0
                else None
            ),
        },
        "incomplete_reasons": (
            []
            if cache_status in {"hit", "hit_and_write"} and read_total > 0
            else [
                "Expected a cache read on the warm call (and preferably a cold "
                f"write); observed cache_status={cache_status}."
            ]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--scorecard-id", default=None)
    args = parser.parse_args(argv)

    scorecard = measure(
        model_id=args.model_id,
        scorecard_id=args.scorecard_id,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"{scorecard['scorecard_id']}.json"
    path.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "cache_status": scorecard["cache_status"]}, indent=2))
    ok = (
        scorecard["cache_status"] in {"hit", "hit_and_write"}
        and int(scorecard["cache_read_tokens"] or 0) > 0
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
