"""Local-first evaluation harness and versioned scorecard writer.

The local runner exercises fan-out and scoring mechanics without claiming that
Bedrock candidates or an LLM judge ran. Live providers will replace the runner
and judge adapters after issues #24 and #25 are resolved.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

from evals.loader import ALLOWED_TOOLS, GOLDEN_DATASET_PATH, load_dataset
from supportrouter.graph import run_agent
from supportrouter.observability import PLANE_EVAL

DEFAULT_CANDIDATE_MODELS = (
    "logical:nova-micro",
    "logical:nova-lite",
    "logical:claude-haiku",
)
DEFAULT_PROMPT_VERSION = "local-stub-v0.1"
DEFAULT_RUBRIC_PATH = Path(__file__).resolve().parent / "rubrics" / "v0.1_judge.json"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "scorecards"


class CandidateRunner(Protocol):
    execution_mode: str

    def run(self, scenario: dict[str, Any], requested_model_id: str) -> dict[str, Any]:
        """Return a serializable candidate execution record."""


class Judge(Protocol):
    judge_version: str

    def evaluate(
        self,
        scenario: dict[str, Any],
        model_output: dict[str, Any],
    ) -> dict[str, Any]:
        """Return judge status, scores, and pass state."""


class LocalStubCandidateRunner:
    """Run the deterministic local graph; requested candidates are not invoked."""

    execution_mode = "local_stub"

    def run(self, scenario: dict[str, Any], requested_model_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        output = run_agent(scenario["input"], plane=PLANE_EVAL)
        wall_time_ms = round((time.perf_counter() - started) * 1000, 3)
        return {
            "requested_model_id": requested_model_id,
            "candidate_executed": False,
            "actual_model_id": output.get("model_id"),
            "execution_mode": self.execution_mode,
            "wall_time_ms": wall_time_ms,
            "usage": None,
            "cost_usd": None,
            "output": output,
        }


class NotRunJudge:
    """Explicit local placeholder; never fabricates LLM-as-judge scores."""

    def __init__(self, judge_version: str) -> None:
        self.judge_version = judge_version

    def evaluate(
        self,
        scenario: dict[str, Any],
        model_output: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "not_run",
            "judge_version": self.judge_version,
            "model_id": None,
            "scores": {
                "faithfulness": None,
                "helpfulness": None,
                "policy_adherence": None,
            },
            "pass": None,
            "reason": "No LLM judge is configured for local-stub execution (#25).",
        }


def programmatic_metrics(
    scenario: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate deterministic expectations from ADR-004."""
    calls = output.get("tool_calls") or []
    call_names = [call.get("name") for call in calls]
    callable_tools = [name for name in call_names if name in ALLOWED_TOOLS]
    tool_errors = [name for name in call_names if name not in ALLOWED_TOOLS]
    expected_error = scenario.get("expected_tool_error")
    citation_ids = {citation.get("doc_id") for citation in output.get("citations") or []}

    checks = {
        "task_type_match": output.get("task_type") == scenario["task_type"],
        "outcome_match": output.get("status") == scenario["expected_outcome"],
        "tools_match": callable_tools == scenario["expected_tools"],
        "tool_error_match": tool_errors == ([expected_error] if expected_error else []),
        "citations_match": set(scenario["expected_citations"]).issubset(citation_ids),
    }
    return {
        **checks,
        "pass": all(checks.values()),
        "actual_tools": callable_tools,
        "actual_tool_errors": tool_errors,
        "actual_citations": sorted(doc_id for doc_id in citation_ids if doc_id),
    }


def run_harness(
    *,
    dataset_path: Path = GOLDEN_DATASET_PATH,
    candidate_model_ids: Sequence[str] = DEFAULT_CANDIDATE_MODELS,
    task_types: set[str] | None = None,
    runner: CandidateRunner | None = None,
    judge: Judge | None = None,
    rubric_path: Path = DEFAULT_RUBRIC_PATH,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    scorecard_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Fan out scenarios across candidates and return a scorecard artifact."""
    if not candidate_model_ids:
        raise ValueError("candidate_model_ids must not be empty")
    if any(not isinstance(model_id, str) or not model_id.strip() for model_id in candidate_model_ids):
        raise ValueError("candidate_model_ids must contain non-empty strings")
    if len(set(candidate_model_ids)) != len(candidate_model_ids):
        raise ValueError("candidate_model_ids must be unique")

    dataset = load_dataset(dataset_path)
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    active_runner = runner or LocalStubCandidateRunner()
    active_judge = judge or NotRunJudge(rubric["judge_version"])
    selected = [
        scenario
        for scenario in dataset["scenarios"]
        if task_types is None or scenario["task_type"] in task_types
    ]
    if not selected:
        raise ValueError("no scenarios matched the requested task types")

    results: list[dict[str, Any]] = []
    for model_id in candidate_model_ids:
        for scenario in selected:
            candidate = active_runner.run(scenario, model_id)
            output = candidate["output"]
            programmatic = programmatic_metrics(scenario, output)
            judged = active_judge.evaluate(scenario, output)
            overall_pass = (
                programmatic["pass"] and judged["pass"]
                if candidate["candidate_executed"]
                and judged["status"] == "completed"
                and judged["pass"] is not None
                else None
            )
            results.append(
                {
                    "scenario_id": scenario["id"],
                    "task_type": scenario["task_type"],
                    "requested_model_id": candidate["requested_model_id"],
                    "candidate_executed": candidate["candidate_executed"],
                    "actual_model_id": candidate["actual_model_id"],
                    "execution_mode": candidate["execution_mode"],
                    "wall_time_ms": candidate["wall_time_ms"],
                    "usage": candidate["usage"],
                    "cost_usd": candidate["cost_usd"],
                    "model_output": {
                        "answer": output.get("answer"),
                        "task_type": output.get("task_type"),
                        "status": output.get("status"),
                        "citations": output.get("citations") or [],
                        "tool_calls": output.get("tool_calls") or [],
                    },
                    "programmatic": programmatic,
                    "judge": judged,
                    "pass": overall_pass,
                }
            )

    programmatic_passes = sum(1 for result in results if result["programmatic"]["pass"])
    candidates_executed = all(result["candidate_executed"] for result in results)
    judge_ran = all(result["judge"]["status"] == "completed" for result in results)
    pass_states_complete = all(result["pass"] is not None for result in results)
    cost_measured = all(result["cost_usd"] is not None for result in results)
    incomplete_reasons: list[str] = []
    if not candidates_executed:
        incomplete_reasons.append("Candidate models were not invoked (#24).")
    if not judge_ran:
        incomplete_reasons.append("LLM-as-judge was not run (#25).")
    if not cost_measured:
        incomplete_reasons.append("Bedrock token usage and cost were not measured.")

    return {
        "schema_version": "v0.1",
        "scorecard_id": scorecard_id or f"scorecard-{uuid.uuid4()}",
        "dataset_version": dataset["dataset_version"],
        "prompt_version": prompt_version,
        "judge_version": active_judge.judge_version,
        "model_ids": list(candidate_model_ids),
        "execution_mode": active_runner.execution_mode,
        "cache_enabled": False,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "incomplete_reasons": incomplete_reasons,
        "summary": {
            "candidate_count": len(candidate_model_ids),
            "candidates_executed": candidates_executed,
            "task_types": sorted({scenario["task_type"] for scenario in selected}),
            "scenario_count": len(selected),
            "scenario_runs": len(results),
            "programmatic_passes": programmatic_passes,
            "programmatic_pass_rate": programmatic_passes / len(results),
            "judge_completed": judge_ran,
            "overall_pass": (
                all(result["pass"] is True for result in results)
                if candidates_executed and judge_ran and pass_states_complete
                else None
            ),
        },
        "cost": {
            "status": "measured" if cost_measured else "not_measured",
            "total_usd": (
                sum(result["cost_usd"] for result in results)
                if cost_measured
                else None
            ),
        },
        "results": results,
    }


def write_scorecard(
    scorecard: dict[str, Any],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{scorecard['scorecard_id']}.json"
    path.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SupportRouter golden evaluations.")
    parser.add_argument("--dataset", type=Path, default=GOLDEN_DATASET_PATH)
    parser.add_argument(
        "--candidate-model",
        action="append",
        dest="candidate_models",
        help="Logical candidate ID; repeat for fan-out (defaults to three local candidates).",
    )
    parser.add_argument(
        "--task-type",
        action="append",
        dest="task_types",
        help="Limit scenarios to a task type; repeat as needed.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    scorecard = run_harness(
        dataset_path=args.dataset,
        candidate_model_ids=args.candidate_models or DEFAULT_CANDIDATE_MODELS,
        task_types=set(args.task_types) if args.task_types else None,
    )
    path = write_scorecard(scorecard, args.output_dir)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
