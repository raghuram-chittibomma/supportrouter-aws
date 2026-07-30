"""Retrieval relevance gate tests (#74 / ADR-020)."""

from __future__ import annotations

from supportrouter.graph import run_agent
from supportrouter.retrieve import (
    BEDROCK_MIN_RELEVANCE_SCORE,
    LOCAL_MIN_RELEVANCE_SCORE,
    filter_relevant_citations,
    retrieve,
)


def test_filter_relevant_citations_local_threshold():
    citations = [
        {"doc_id": "strong", "title": "s", "excerpt": "e", "score": 8},
        {"doc_id": "weak", "title": "w", "excerpt": "e", "score": 2},
    ]
    kept = filter_relevant_citations(citations, provider="local")
    assert [c["doc_id"] for c in kept] == ["strong"]
    assert LOCAL_MIN_RELEVANCE_SCORE == 4


def test_filter_relevant_citations_bedrock_threshold():
    citations = [
        {"doc_id": "strong", "title": "s", "excerpt": "e", "score": 0.55},
        {"doc_id": "weak", "title": "w", "excerpt": "e", "score": 0.2},
    ]
    kept = filter_relevant_citations(citations, provider="bedrock")
    assert [c["doc_id"] for c in kept] == ["strong"]
    assert BEDROCK_MIN_RELEVANCE_SCORE == 0.4


def test_supported_faq_still_resolves_with_returns_doc():
    result = run_agent(
        "What is the VoltEdge policy for unused items still in original packaging within 30 days?",
        runtime_mode="local",
    )
    assert result["task_type"] == "faq_policy"
    assert result["status"] == "resolved"
    doc_ids = {c["doc_id"] for c in result.get("citations") or []}
    assert "pol-returns-001" in doc_ids
    assert all(
        float(c["score"]) >= LOCAL_MIN_RELEVANCE_SCORE
        for c in result.get("citations") or []
    )


def test_supported_product_still_resolves_with_powerdock_doc():
    result = run_agent(
        "Is the PowerDock Duo compatible with USB-C laptops that support DisplayPort Alt Mode?",
        runtime_mode="local",
    )
    assert result["task_type"] == "product_question"
    assert result["status"] == "resolved"
    doc_ids = {c["doc_id"] for c in result.get("citations") or []}
    assert "faq-powerdock-001" in doc_ids


def test_unsupported_faq_escalates_without_weak_citations():
    result = run_agent(
        "What is your policy on teleporting packages to Mars?",
        runtime_mode="local",
    )
    assert result["task_type"] == "faq_policy"
    assert result["status"] == "escalated"
    assert result.get("citations") == []
    assert "retrieve:relevance_empty" in result["notes"]
    assert result.get("hitl_reason")


def test_local_retrieve_filters_weak_keyword_hits():
    weak = retrieve(
        "What is your policy on teleporting packages to Mars?",
        "faq_policy",
        provider="local",
    )
    assert weak == []
    strong = retrieve(
        "What is the VoltEdge policy for unused items still in original packaging within 30 days?",
        "faq_policy",
        provider="local",
    )
    assert strong
    assert strong[0]["doc_id"] == "pol-returns-001"
