"""Unit tests for live Bedrock eval adapters (#17 / ADR-016)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.bedrock_adapters import (
    DEFAULT_JUDGE_MODEL_ID,
    BedrockCandidateRunner,
    BedrockHaikuJudge,
    estimate_cost_usd,
    resolve_inference_profile,
)
from evals.harness import main, run_harness
from evals.loader import GOLDEN_DATASET_PATH, load_dataset
from supportrouter.bedrock_converse import extract_json_object


class FakeConverseClient:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected converse call")
        return self.responses.pop(0)


def test_resolve_inference_profile_maps_logical_ids():
    assert resolve_inference_profile("logical:nova-micro") == "us.amazon.nova-micro-v1:0"
    assert resolve_inference_profile("logical:nova-lite") == "us.amazon.nova-lite-v1:0"
    assert (
        resolve_inference_profile("logical:claude-haiku")
        == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )


def test_resolve_inference_profile_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown model_id"):
        resolve_inference_profile("logical:unknown")


def test_estimate_cost_usd_from_published_rates():
    cost = estimate_cost_usd(
        "us.amazon.nova-micro-v1:0",
        {"input_tokens": 1000, "output_tokens": 1000},
    )
    assert cost == pytest.approx(0.000175)


def test_extract_json_object_tolerates_fences():
    payload = extract_json_object('```json\n{"faithfulness": 5}\n```')
    assert payload == {"faithfulness": 5}


def test_bedrock_candidate_runner_marks_executed_and_cost():
    scenario = next(
        scenario
        for scenario in load_dataset()["scenarios"]
        if scenario["id"] == "faq-policy-001"
    )
    client = FakeConverseClient(
        [
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    "VoltEdge returns are accepted within 30 days "
                                    "with original packaging."
                                )
                            }
                        ]
                    }
                },
                "usage": {"inputTokens": 120, "outputTokens": 40, "totalTokens": 160},
                "stopReason": "end_turn",
            }
        ]
    )

    result = BedrockCandidateRunner(client=client).run(scenario, "logical:nova-micro")

    assert result["candidate_executed"] is True
    assert result["execution_mode"] == "bedrock_converse"
    assert result["actual_model_id"] == "us.amazon.nova-micro-v1:0"
    assert result["usage"]["input_tokens"] == 120
    assert result["cost_usd"] is not None
    assert "30 days" in result["output"]["answer"]
    assert client.calls[0]["modelId"] == "us.amazon.nova-micro-v1:0"
    assert "inferenceConfig" in client.calls[0]


def test_haiku_judge_scores_and_applies_threshold():
    scenario = next(
        scenario
        for scenario in load_dataset()["scenarios"]
        if scenario["id"] == "faq-policy-001"
    )
    client = FakeConverseClient(
        [
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": json.dumps(
                                    {
                                        "faithfulness": 5,
                                        "helpfulness": 4,
                                        "policy_adherence": 5,
                                        "reason": "Supported by policy citation.",
                                    }
                                )
                            }
                        ]
                    }
                },
                "usage": {"inputTokens": 200, "outputTokens": 50, "totalTokens": 250},
                "stopReason": "end_turn",
            }
        ]
    )

    judged = BedrockHaikuJudge(client=client).evaluate(
        scenario,
        {
            "answer": "Returns within 30 days.",
            "status": "resolved",
            "citations": [{"doc_id": "pol-returns-001"}],
            "tool_calls": [],
        },
    )

    assert judged["status"] == "completed"
    assert judged["judge_version"] == "v0.1-haiku-4.5"
    assert judged["model_id"] == DEFAULT_JUDGE_MODEL_ID
    assert judged["pass"] is True
    assert judged["scores"]["helpfulness"] == 4
    assert judged["cost_usd"] is not None
    assert any("cachePoint" in block for block in client.calls[0]["system"])
    assert judged["usage"]["cache_enabled"] is True


def test_haiku_judge_fails_closed_on_bad_payload():
    scenario = next(
        scenario
        for scenario in load_dataset()["scenarios"]
        if scenario["id"] == "faq-policy-001"
    )
    client = FakeConverseClient(
        [
            {
                "output": {"message": {"content": [{"text": "not-json"}]}},
                "usage": {"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
                "stopReason": "end_turn",
            }
        ]
    )

    judged = BedrockHaikuJudge(client=client).evaluate(scenario, {"answer": "x"})

    assert judged["status"] == "error"
    assert judged["pass"] is None
    assert judged["scores"]["faithfulness"] is None
    assert judged["usage"]["input_tokens"] == 10
    assert judged["cost_usd"] is not None


def test_live_judge_error_incomplete_reasons_are_honest():
    client = FakeConverseClient(
        [
            {
                "output": {
                    "message": {"content": [{"text": "Order VE-1001 shipped."}]}
                },
                "usage": {"inputTokens": 80, "outputTokens": 20, "totalTokens": 100},
                "stopReason": "end_turn",
            },
            {
                "output": {"message": {"content": [{"text": "not-json"}]}},
                "usage": {"inputTokens": 50, "outputTokens": 10, "totalTokens": 60},
                "stopReason": "end_turn",
            },
        ]
    )

    scorecard = run_harness(
        dataset_path=GOLDEN_DATASET_PATH,
        candidate_model_ids=["logical:nova-micro"],
        scenario_ids={"ord-status-001"},
        runner=BedrockCandidateRunner(client=client),
        judge=BedrockHaikuJudge(client=client),
        prompt_version="bedrock-draft-v0.1",
        scorecard_id="scorecard-live-judge-error",
        created_at="2026-07-29T00:00:00+00:00",
    )

    assert scorecard["summary"]["candidates_executed"] is True
    assert scorecard["summary"]["judge_completed"] is False
    assert scorecard["summary"]["overall_pass"] is None
    assert "LLM-as-judge failed closed on one or more runs." in scorecard["incomplete_reasons"]
    assert "local-stub execution" not in " ".join(scorecard["incomplete_reasons"])
    assert scorecard["cost"]["status"] == "measured"
    assert scorecard["results"][0]["judge"]["cost_usd"] is not None


def test_bedrock_candidate_keeps_empty_draft_without_stub_fallback():
    scenario = next(
        scenario
        for scenario in load_dataset()["scenarios"]
        if scenario["id"] == "faq-policy-001"
    )
    client = FakeConverseClient(
        [
            {
                "output": {"message": {"content": [{"text": ""}]}},
                "usage": {"inputTokens": 10, "outputTokens": 0, "totalTokens": 10},
                "stopReason": "end_turn",
            }
        ]
    )

    result = BedrockCandidateRunner(client=client).run(scenario, "logical:nova-micro")

    assert result["output"]["answer"] == ""
    assert "bedrock_draft_empty" in result["output"]["notes"]


def test_live_harness_path_with_injected_adapters():
    client = FakeConverseClient(
        [
            {
                "output": {
                    "message": {"content": [{"text": "Order VE-1001 shipped."}]}
                },
                "usage": {"inputTokens": 80, "outputTokens": 20, "totalTokens": 100},
                "stopReason": "end_turn",
            },
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": json.dumps(
                                    {
                                        "faithfulness": 5,
                                        "helpfulness": 5,
                                        "policy_adherence": 5,
                                        "reason": "ok",
                                    }
                                )
                            }
                        ]
                    }
                },
                "usage": {"inputTokens": 100, "outputTokens": 30, "totalTokens": 130},
                "stopReason": "end_turn",
            },
        ]
    )

    scorecard = run_harness(
        dataset_path=GOLDEN_DATASET_PATH,
        candidate_model_ids=["logical:nova-micro"],
        scenario_ids={"ord-status-001"},
        runner=BedrockCandidateRunner(client=client),
        judge=BedrockHaikuJudge(client=client),
        prompt_version="bedrock-draft-v0.1",
        scorecard_id="scorecard-live-unit",
        created_at="2026-07-29T00:00:00+00:00",
    )

    assert scorecard["execution_mode"] == "bedrock_converse"
    assert scorecard["summary"]["candidates_executed"] is True
    assert scorecard["summary"]["judge_completed"] is True
    assert scorecard["summary"]["overall_pass"] is True
    assert scorecard["cost"]["status"] == "measured"
    assert scorecard["cost"]["total_usd"] is not None
    assert scorecard["incomplete_reasons"] == []
    assert len(client.calls) == 2


def test_cli_live_flag_wires_adapters(monkeypatch, tmp_path, capsys):
    captured: dict = {}

    def fake_run_harness(**kwargs):
        captured.update(kwargs)
        return {
            "scorecard_id": "scorecard-cli-live",
            "schema_version": "v0.1",
        }

    monkeypatch.setattr("evals.harness.run_harness", fake_run_harness)

    exit_code = main(
        [
            "--live",
            "--task-type",
            "order_status",
            "--task-type",
            "faq_policy",
            "--output-dir",
            str(tmp_path),
            "--scorecard-id",
            "scorecard-cli-live",
        ]
    )

    assert exit_code == 0
    assert captured["prompt_version"] == "bedrock-draft-v0.1"
    assert captured["max_scenarios_per_task"] == 1
    assert captured["runner"].execution_mode == "bedrock_converse"
    assert captured["judge"].judge_version == "v0.1-haiku-4.5"
    output_path = Path(capsys.readouterr().out.strip())
    assert output_path == tmp_path / "scorecard-cli-live.json"
    assert output_path.is_file()
