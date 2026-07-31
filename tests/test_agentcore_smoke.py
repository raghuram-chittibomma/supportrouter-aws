"""Local AgentCore host smoke against a golden scenario (#95 / ADR-024).

Runs ``handle_agentcore_payload`` → ``run_agent`` (no AgentCore deploy, no
Bedrock). Proves adapter wiring only — quality/cost remain **not measured**
(see ``evals/scorecards/scorecard-v0.6-agentcore-not-measured.json``).
"""

from __future__ import annotations

import json
from pathlib import Path

from supportrouter.agentcore_adapter import handle_agentcore_payload

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evals" / "datasets" / "v0.1_golden.json"
SMOKE_SCORECARD = (
    ROOT / "evals" / "scorecards" / "scorecard-v0.6-agentcore-not-measured.json"
)
SMOKE_SCENARIO_ID = "faq-policy-001"


def _scenario(scenario_id: str) -> dict:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for row in payload["scenarios"]:
        if row["id"] == scenario_id:
            return row
    raise KeyError(scenario_id)


def test_agentcore_local_smoke_faq_policy_scenario():
    scenario = _scenario(SMOKE_SCENARIO_ID)
    result = handle_agentcore_payload(
        {"prompt": scenario["input"], "runtime_mode": "local"}
    )
    assert "error" not in result
    assert result.get("task_type") == scenario["task_type"]
    assert result.get("status") == scenario["expected_outcome"]
    assert isinstance(result.get("answer"), str) and result["answer"].strip()
    expected_docs = set(scenario.get("expected_citations") or [])
    if expected_docs:
        cited = {
            c.get("doc_id")
            for c in (result.get("citations") or [])
            if isinstance(c, dict)
        }
        assert expected_docs.issubset(cited)


def test_agentcore_not_measured_scorecard_artifact_exists():
    card = json.loads(SMOKE_SCORECARD.read_text(encoding="utf-8"))
    assert card["scorecard_id"] == "scorecard-v0.6-agentcore-not-measured"
    assert card["cost"]["status"] == "not_measured"
    assert card["quality"]["status"] == "not_measured"
    assert card["summary"]["candidates_executed"] is False
    assert card["summary"]["smoke_scenario_id"] == SMOKE_SCENARIO_ID
    assert card["incomplete_reasons"]
