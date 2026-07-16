"""Load and validate golden eval datasets under evals/datasets/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_SCENARIO_KEYS = (
    "id",
    "task_type",
    "input",
    "expected_tools",
    "expected_citations",
    "expected_outcome",
)

ALLOWED_OUTCOMES = frozenset(
    {"resolved", "escalated", "pending_approval", "rejected"}
)

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
GOLDEN_DATASET_PATH = DATASETS_DIR / "v0.1_golden.json"


def load_dataset(path: Path | None = None) -> dict[str, Any]:
    """Load a dataset JSON file and validate required schema fields."""
    dataset_path = path or GOLDEN_DATASET_PATH
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    validate_dataset(data)
    return data


def validate_dataset(data: dict[str, Any]) -> None:
    if not isinstance(data.get("dataset_version"), str) or not data["dataset_version"]:
        raise ValueError("dataset_version must be a non-empty string")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a non-empty list")

    seen_ids: set[str] = set()
    for i, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ValueError(f"scenarios[{i}] must be an object")
        missing = [k for k in REQUIRED_SCENARIO_KEYS if k not in scenario]
        if missing:
            raise ValueError(f"scenarios[{i}] missing keys: {missing}")
        scenario_id = scenario["id"]
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(f"scenarios[{i}].id must be a non-empty string")
        if scenario_id in seen_ids:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen_ids.add(scenario_id)
        if not isinstance(scenario["task_type"], str) or not scenario["task_type"]:
            raise ValueError(f"{scenario_id}: task_type must be a non-empty string")
        if not isinstance(scenario["input"], str) or not scenario["input"].strip():
            raise ValueError(f"{scenario_id}: input must be a non-empty string")
        if not isinstance(scenario["expected_tools"], list):
            raise ValueError(f"{scenario_id}: expected_tools must be a list")
        if not isinstance(scenario["expected_citations"], list):
            raise ValueError(f"{scenario_id}: expected_citations must be a list")
        if scenario["expected_outcome"] not in ALLOWED_OUTCOMES:
            raise ValueError(
                f"{scenario_id}: expected_outcome must be one of {sorted(ALLOWED_OUTCOMES)}"
            )


def golden_scenario_inputs(path: Path | None = None) -> list[str]:
    """Return golden input strings (for anti-leakage checks against src/)."""
    data = load_dataset(path)
    return [s["input"] for s in data["scenarios"]]
