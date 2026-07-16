"""Golden eval dataset schema + local programmatic checks (#8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.loader import GOLDEN_DATASET_PATH, golden_scenario_inputs, load_dataset
from supportrouter.graph import run_agent

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
KB_ROOT = ROOT / "data" / "knowledge_base"


@pytest.fixture(scope="module")
def golden():
    return load_dataset(GOLDEN_DATASET_PATH)


def test_golden_dataset_exists_and_has_version(golden):
    assert GOLDEN_DATASET_PATH.is_file()
    assert golden["dataset_version"] == "v0.1-golden"


def test_golden_covers_required_task_types(golden):
    task_types = {s["task_type"] for s in golden["scenarios"]}
    assert "order_status" in task_types
    assert "faq_policy" in task_types


def test_golden_includes_edge_cases(golden):
    by_id = {s["id"]: s for s in golden["scenarios"]}
    assert by_id["ord-status-missing-id-001"]["expected_outcome"] == "escalated"
    assert by_id["refund-hitl-001"]["expected_outcome"] == "pending_approval"
    assert by_id["unknown-low-conf-001"]["expected_outcome"] == "escalated"
    assert by_id["product-q-001"]["task_type"] == "product_question"


def test_expected_citations_exist_in_kb(golden):
    known_docs = {p.stem for p in KB_ROOT.glob("*.md")}
    # Also accept doc_id from front matter when stem differs (none today).
    for scenario in golden["scenarios"]:
        for doc_id in scenario["expected_citations"]:
            assert doc_id in known_docs or any(
                doc_id in p.read_text(encoding="utf-8") for p in KB_ROOT.glob("*.md")
            ), f"{scenario['id']}: citation {doc_id} not found in knowledge_base"


@pytest.mark.parametrize(
    "scenario",
    load_dataset(GOLDEN_DATASET_PATH)["scenarios"],
    ids=lambda s: s["id"],
)
def test_golden_programmatic_local_agent(scenario):
    """Programmatic checks only (ADR-004); LLM-as-judge lands in #17."""
    result = run_agent(scenario["input"])
    assert result["task_type"] == scenario["task_type"], scenario["id"]
    assert result["status"] == scenario["expected_outcome"], scenario["id"]

    tool_names = [t["name"] for t in (result.get("tool_calls") or [])]
    assert tool_names == scenario["expected_tools"], scenario["id"]

    citation_ids = {c["doc_id"] for c in (result.get("citations") or [])}
    for doc_id in scenario["expected_citations"]:
        assert doc_id in citation_ids, f"{scenario['id']}: missing citation {doc_id}"


def test_golden_inputs_not_leaked_into_runtime_src():
    """Anti-leakage: golden scenario text must not appear in runtime prompts."""
    inputs = golden_scenario_inputs()
    src_files = list(SRC_ROOT.rglob("*.py"))
    assert src_files, "expected runtime python under src/"
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in src_files)
    for text in inputs:
        assert text not in corpus, f"golden input leaked into src/: {text!r}"
