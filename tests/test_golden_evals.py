"""Golden eval dataset schema + local programmatic checks (#8)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

import pytest

from evals.loader import (
    ALLOWED_TOOLS,
    GOLDEN_DATASET_PATH,
    golden_scenario_inputs,
    load_dataset,
    validate_dataset,
)
from supportrouter.graph import run_agent

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
KB_ROOT = ROOT / "data" / "knowledge_base"
DOC_ID_RE = re.compile(r"^doc_id:\s*(\S+)\s*$", re.MULTILINE)


@pytest.fixture(scope="module")
def golden() -> dict:
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
    known_docs = _knowledge_docs()
    for scenario in golden["scenarios"]:
        for doc_id in scenario["expected_citations"]:
            assert doc_id in known_docs, (
                f"{scenario['id']}: citation {doc_id} not found in knowledge_base"
            )


def test_cited_docs_contain_expected_answer_facts(golden):
    """Ground truth facts provide a semantic check independent of retrieval output."""
    known_docs = _knowledge_docs()
    for scenario in golden["scenarios"]:
        facts = scenario.get("expected_answer_facts", [])
        cited_text = "\n".join(
            known_docs[doc_id] for doc_id in scenario["expected_citations"]
        ).lower()
        for fact in facts:
            assert fact.lower() in cited_text, (
                f"{scenario['id']}: fact {fact!r} absent from expected citations"
            )


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
    callable_tools = [name for name in tool_names if name in ALLOWED_TOOLS]
    tool_errors = [name for name in tool_names if name not in ALLOWED_TOOLS]
    assert callable_tools == scenario["expected_tools"], scenario["id"]
    expected_error = scenario.get("expected_tool_error")
    assert tool_errors == ([expected_error] if expected_error else []), scenario["id"]

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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("task_type", "order_stats", "task_type"),
        ("expected_tools", [None], "non-empty strings"),
        ("expected_tools", ["send_email"], "unsupported expected_tools"),
        ("expected_citations", [""], "non-empty strings"),
        ("expected_outcome", "complete", "expected_outcome"),
    ],
)
def test_dataset_validation_rejects_invalid_ground_truth(field, value, message):
    data = _minimal_dataset()
    data["scenarios"][0][field] = value
    with pytest.raises(ValueError, match=message):
        validate_dataset(data)


def test_dataset_validation_rejects_unknown_scenario_fields():
    data = _minimal_dataset()
    data["scenarios"][0]["expected_tool"] = "get_order_status"
    with pytest.raises(ValueError, match="unknown keys"):
        validate_dataset(data)


def test_dataset_validation_rejects_duplicate_ids():
    data = _minimal_dataset()
    data["scenarios"].append(deepcopy(data["scenarios"][0]))
    with pytest.raises(ValueError, match="duplicate scenario id"):
        validate_dataset(data)


def test_dataset_validation_separates_tool_errors_from_callable_tools():
    data = _minimal_dataset()
    scenario = data["scenarios"][0]
    scenario["expected_tool_error"] = "missing_order_id"
    with pytest.raises(ValueError, match="cannot be combined"):
        validate_dataset(data)


def _knowledge_docs() -> dict[str, str]:
    documents: dict[str, str] = {}
    for path in KB_ROOT.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        match = DOC_ID_RE.search(text)
        assert match, f"{path}: missing doc_id front matter"
        documents[match.group(1)] = text
    return documents


def _minimal_dataset() -> dict:
    return {
        "dataset_version": "test",
        "scenarios": [
            {
                "id": "valid-001",
                "task_type": "order_status",
                "input": "Synthetic test input",
                "expected_tools": ["get_order_status"],
                "expected_citations": [],
                "expected_outcome": "resolved",
            }
        ],
    }
