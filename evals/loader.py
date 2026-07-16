"""Load and validate golden eval datasets under evals/datasets/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

from supportrouter.schemas import TaskType

REQUIRED_SCENARIO_KEYS = (
    "id",
    "task_type",
    "input",
    "expected_tools",
    "expected_citations",
    "expected_outcome",
)
OPTIONAL_SCENARIO_KEYS = ("expected_answer_facts", "expected_tool_error")

ALLOWED_TASK_TYPES = frozenset(get_args(TaskType))
ALLOWED_TOOLS = frozenset(
    {"get_order_status", "initiate_return", "issue_refund"}
)
ALLOWED_TOOL_ERRORS = frozenset({"missing_order_id"})
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
    if not isinstance(data, dict):
        raise ValueError("dataset must be an object")
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
        unknown = set(scenario) - set(REQUIRED_SCENARIO_KEYS) - set(OPTIONAL_SCENARIO_KEYS)
        if unknown:
            raise ValueError(f"scenarios[{i}] has unknown keys: {sorted(unknown)}")
        scenario_id = scenario["id"]
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(f"scenarios[{i}].id must be a non-empty string")
        if scenario_id in seen_ids:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen_ids.add(scenario_id)
        if scenario["task_type"] not in ALLOWED_TASK_TYPES:
            raise ValueError(
                f"{scenario_id}: task_type must be one of {sorted(ALLOWED_TASK_TYPES)}"
            )
        if not isinstance(scenario["input"], str) or not scenario["input"].strip():
            raise ValueError(f"{scenario_id}: input must be a non-empty string")
        _validate_string_list(scenario_id, "expected_tools", scenario["expected_tools"])
        unknown_tools = set(scenario["expected_tools"]) - ALLOWED_TOOLS
        if unknown_tools:
            raise ValueError(
                f"{scenario_id}: unsupported expected_tools: {sorted(unknown_tools)}"
            )
        _validate_string_list(
            scenario_id, "expected_citations", scenario["expected_citations"]
        )
        if "expected_answer_facts" in scenario:
            _validate_string_list(
                scenario_id,
                "expected_answer_facts",
                scenario["expected_answer_facts"],
                allow_empty=False,
            )
        tool_error = scenario.get("expected_tool_error")
        if tool_error is not None and tool_error not in ALLOWED_TOOL_ERRORS:
            raise ValueError(
                f"{scenario_id}: expected_tool_error must be one of "
                f"{sorted(ALLOWED_TOOL_ERRORS)}"
            )
        if tool_error is not None and scenario["expected_tools"]:
            raise ValueError(
                f"{scenario_id}: expected_tool_error cannot be combined with expected_tools"
            )
        if scenario["expected_outcome"] not in ALLOWED_OUTCOMES:
            raise ValueError(
                f"{scenario_id}: expected_outcome must be one of {sorted(ALLOWED_OUTCOMES)}"
            )


def _validate_string_list(
    scenario_id: str,
    field: str,
    value: Any,
    *,
    allow_empty: bool = True,
) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{scenario_id}: {field} must be a list")
    if not allow_empty and not value:
        raise ValueError(f"{scenario_id}: {field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{scenario_id}: {field} entries must be non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{scenario_id}: {field} entries must be unique")


def golden_scenario_inputs(path: Path | None = None) -> list[str]:
    """Return golden input strings (for anti-leakage checks against src/)."""
    data = load_dataset(path)
    return [s["input"] for s in data["scenarios"]]
