"""Tests for the local-first eval harness and scorecard contract (#17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.harness import (
    DEFAULT_CANDIDATE_MODELS,
    DEFAULT_RUBRIC_PATH,
    LocalStubCandidateRunner,
    main,
    programmatic_metrics,
    run_harness,
    write_scorecard,
)
from evals.loader import ALLOWED_TASK_TYPES, GOLDEN_DATASET_PATH, load_dataset


def test_local_harness_fans_out_three_candidates_across_two_task_types():
    scorecard = run_harness(
        dataset_path=GOLDEN_DATASET_PATH,
        task_types={"order_status", "faq_policy"},
        scorecard_id="scorecard-test",
        created_at="2026-07-16T00:00:00+00:00",
    )

    scenario_count = sum(
        1
        for scenario in load_dataset()["scenarios"]
        if scenario["task_type"] in {"order_status", "faq_policy"}
    )
    assert scorecard["model_ids"] == list(DEFAULT_CANDIDATE_MODELS)
    assert scorecard["summary"]["candidate_count"] == 3
    assert scorecard["summary"]["task_types"] == ["faq_policy", "order_status"]
    assert scorecard["summary"]["scenario_runs"] == scenario_count * 3
    assert scorecard["summary"]["programmatic_passes"] == scenario_count * 3


def test_local_scorecard_never_claims_model_judge_or_cost_execution():
    scorecard = run_harness(
        candidate_model_ids=["logical:test"],
        task_types={"order_status"},
    )

    assert scorecard["execution_mode"] == "local_stub"
    assert scorecard["summary"]["candidates_executed"] is False
    assert scorecard["summary"]["judge_completed"] is False
    assert scorecard["summary"]["overall_pass"] is None
    assert scorecard["cost"] == {"status": "not_measured", "total_usd": None}
    assert len(scorecard["incomplete_reasons"]) == 3
    for result in scorecard["results"]:
        assert result["candidate_executed"] is False
        assert result["usage"] is None
        assert result["cost_usd"] is None
        assert result["judge"]["status"] == "not_run"
        assert result["judge"]["pass"] is None
        assert result["pass"] is None


def test_completed_judge_cannot_make_local_stub_candidate_pass():
    class PassingJudge:
        judge_version = "test-judge"

        def evaluate(self, scenario, model_output):
            return {
                "status": "completed",
                "judge_version": self.judge_version,
                "model_id": "test-judge-model",
                "scores": {
                    "faithfulness": 5,
                    "helpfulness": 5,
                    "policy_adherence": 5,
                },
                "pass": True,
                "reason": "test",
            }

    scorecard = run_harness(
        candidate_model_ids=["logical:test"],
        task_types={"faq_policy"},
        judge=PassingJudge(),
    )

    assert scorecard["summary"]["judge_completed"] is True
    assert scorecard["summary"]["candidates_executed"] is False
    assert scorecard["summary"]["overall_pass"] is None
    assert all(result["pass"] is None for result in scorecard["results"])


def test_programmatic_metrics_require_all_adr_checks():
    scenario = {
        "task_type": "faq_policy",
        "expected_outcome": "resolved",
        "expected_tools": [],
        "expected_citations": ["pol-returns-001"],
    }
    output = {
        "task_type": "faq_policy",
        "status": "resolved",
        "tool_calls": [],
        "citations": [{"doc_id": "wrong-doc"}],
    }

    metrics = programmatic_metrics(scenario, output)

    assert metrics["task_type_match"] is True
    assert metrics["outcome_match"] is True
    assert metrics["citations_match"] is False
    assert metrics["pass"] is False


def test_programmatic_metrics_distinguish_tool_errors_from_callable_tools():
    scenario = {
        "task_type": "order_status",
        "expected_outcome": "escalated",
        "expected_tools": [],
        "expected_tool_error": "missing_order_id",
        "expected_citations": [],
    }
    output = {
        "task_type": "order_status",
        "status": "escalated",
        "tool_calls": [{"name": "missing_order_id"}],
        "citations": [],
    }

    metrics = programmatic_metrics(scenario, output)

    assert metrics["tools_match"] is True
    assert metrics["tool_error_match"] is True
    assert metrics["actual_tools"] == []
    assert metrics["actual_tool_errors"] == ["missing_order_id"]
    assert metrics["pass"] is True


def test_scorecard_writer_creates_versioned_json(tmp_path):
    scorecard = run_harness(
        candidate_model_ids=["logical:test"],
        task_types={"faq_policy"},
        scorecard_id="scorecard-fixed",
        created_at="2026-07-16T00:00:00+00:00",
    )

    path = write_scorecard(scorecard, tmp_path)

    assert path == tmp_path / "scorecard-fixed.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["schema_version"] == "v0.1"
    assert written["dataset_version"] == "v0.1-golden"
    assert written["scorecard_id"] == "scorecard-fixed"


def test_cli_writes_scorecard_with_default_three_candidates(tmp_path, capsys):
    exit_code = main(
        [
            "--dataset",
            str(GOLDEN_DATASET_PATH),
            "--task-type",
            "faq_policy",
            "--task-type",
            "order_status",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    output_path = Path(capsys.readouterr().out.strip())
    assert output_path.is_file()
    scorecard = json.loads(output_path.read_text(encoding="utf-8"))
    assert scorecard["summary"]["candidate_count"] == 3
    assert scorecard["summary"]["task_types"] == ["faq_policy", "order_status"]


@pytest.mark.parametrize(
    "candidate_ids",
    [[], [""], ["logical:test", "logical:test"]],
)
def test_harness_rejects_invalid_candidate_configuration(candidate_ids):
    with pytest.raises(ValueError, match="candidate_model_ids"):
        run_harness(candidate_model_ids=candidate_ids)


def test_judge_rubric_is_versioned_and_covers_all_task_types():
    rubric = json.loads(DEFAULT_RUBRIC_PATH.read_text(encoding="utf-8"))

    assert rubric["judge_version"] == "v0.1-rubric-draft"
    assert set(rubric["dimensions"]) == {
        "faithfulness",
        "helpfulness",
        "policy_adherence",
    }
    assert set(rubric["pass_thresholds"]) == set(ALLOWED_TASK_TYPES)
    assert all(
        threshold in rubric["dimensions"]["faithfulness"]["scale"]
        for threshold in rubric["pass_thresholds"].values()
    )


def test_local_runner_records_actual_router_model_separately():
    scenario = next(
        scenario
        for scenario in load_dataset()["scenarios"]
        if scenario["id"] == "ord-status-001"
    )

    result = LocalStubCandidateRunner().run(scenario, "logical:requested")

    assert result["requested_model_id"] == "logical:requested"
    assert result["candidate_executed"] is False
    assert result["actual_model_id"] == "amazon.nova-micro"
