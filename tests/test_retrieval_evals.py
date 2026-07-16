"""Local retrieval regression until Bedrock KB scorecards exist (#8/#13/#17)."""

from __future__ import annotations

import json
from pathlib import Path

from supportrouter.retrieve import retrieve

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "datasets" / "v0.1_retrieval.json"


def test_retrieval_golden_scenarios_local_stub():
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    for scenario in data["scenarios"]:
        citations = retrieve(scenario["input"], scenario["task_type"])
        doc_ids = {c["doc_id"] for c in citations}
        for expected in scenario["expected_citations"]:
            assert expected in doc_ids, f"{scenario['id']}: missing citation {expected}"
