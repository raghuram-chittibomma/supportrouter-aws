"""Deterministic eval gate for the versioned guardrail adversarial dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from supportrouter.guardrails import LOCAL_GUARDRAIL_VERSION, assess_text

DEFAULT_GUARDRAIL_DATASET = (
    Path(__file__).resolve().parent / "datasets" / "v0.1_guardrails.json"
)


def run_guardrail_harness(
    dataset_path: Path = DEFAULT_GUARDRAIL_DATASET,
) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    _validate_dataset(dataset)

    results: list[dict[str, Any]] = []
    for scenario in dataset["scenarios"]:
        assessment = assess_text(scenario["text"], stage=scenario["stage"])
        category = scenario.get("expected_category")
        passed = assessment.action == scenario["expected_action"] and (
            category is None or category in assessment.categories
        )
        results.append(
            {
                "scenario_id": scenario["id"],
                "stage": scenario["stage"],
                "expected_action": scenario["expected_action"],
                "actual_action": assessment.action,
                "expected_category": category,
                "actual_categories": list(assessment.categories),
                "pass": passed,
            }
        )

    return {
        "schema_version": "v0.1",
        "dataset_version": dataset["dataset_version"],
        "guardrail_version": LOCAL_GUARDRAIL_VERSION,
        "execution_mode": "local_deterministic",
        "managed_guardrail_executed": False,
        "results": results,
        "summary": {
            "scenario_count": len(results),
            "passed": sum(result["pass"] for result in results),
            "overall_pass": all(result["pass"] for result in results),
        },
    }


def _validate_dataset(dataset: Any) -> None:
    if not isinstance(dataset, dict):
        raise ValueError("guardrail dataset must be an object")
    if dataset.get("policy_version") != LOCAL_GUARDRAIL_VERSION:
        raise ValueError("guardrail dataset policy_version does not match local policy")
    scenarios = dataset.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("guardrail dataset scenarios must be a non-empty list")

    ids: set[str] = set()
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ValueError(f"scenarios[{index}] must be an object")
        required = {"id", "stage", "text", "expected_action", "expected_category"}
        if set(scenario) != required:
            raise ValueError(f"scenarios[{index}] must contain exactly {sorted(required)}")
        scenario_id = scenario["id"]
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in ids:
            raise ValueError(f"scenarios[{index}] id must be a unique non-empty string")
        ids.add(scenario_id)
        if scenario["stage"] not in {"input", "output"}:
            raise ValueError(f"{scenario_id}: stage must be input or output")
        if not isinstance(scenario["text"], str) or not scenario["text"]:
            raise ValueError(f"{scenario_id}: text must be a non-empty string")
        if scenario["expected_action"] not in {"allowed", "blocked"}:
            raise ValueError(f"{scenario_id}: unsupported expected_action")
        category = scenario["expected_category"]
        if category is not None and (not isinstance(category, str) or not category):
            raise ValueError(f"{scenario_id}: expected_category must be null or a string")
