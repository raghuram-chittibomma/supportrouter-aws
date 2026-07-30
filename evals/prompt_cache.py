"""Stable judge-rubric prefix for Bedrock prompt caching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from supportrouter.prompt_cache import (
    JUDGE_CACHE_MIN_TOKENS,
    CacheablePrefix,
    build_cacheable_prefix,
    deterministic_cache_padding,
)

DEFAULT_RUBRIC_PATH = Path(__file__).resolve().parent / "rubrics" / "v0.1_judge.json"


def judge_cacheable_prefix(
    rubric_path: Path = DEFAULT_RUBRIC_PATH,
) -> CacheablePrefix:
    rubric: dict[str, Any] = json.loads(rubric_path.read_text(encoding="utf-8"))
    version = rubric.get("judge_version")
    if not isinstance(version, str) or not version:
        raise ValueError("judge rubric requires judge_version")

    stable_rubric = {
        "judge_version": version,
        "dimensions": rubric.get("dimensions"),
        "pass_thresholds": rubric.get("pass_thresholds"),
    }
    return build_cacheable_prefix(
        name="eval-judge-rubric",
        version=version,
        blocks=(
            {
                "kind": "judge_system",
                "content": (
                    "Evaluate only the supplied synthetic scenario ground truth "
                    "and candidate output. Return numeric rubric scores. "
                    "You are an evaluation judge for synthetic VoltEdge support "
                    "transcripts. Score only from supplied evidence. Return one "
                    "JSON object and no markdown."
                ),
                "cache_checkpoint": True,
            },
            {
                "kind": "judge_rubric",
                "content": json.dumps(
                    stable_rubric,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "cache_checkpoint": True,
            },
            {
                "kind": "cache_padding",
                "content": deterministic_cache_padding(
                    label="eval-judge-rubric",
                    min_tokens=JUDGE_CACHE_MIN_TOKENS,
                ),
                "cache_checkpoint": True,
            },
        ),
    )
