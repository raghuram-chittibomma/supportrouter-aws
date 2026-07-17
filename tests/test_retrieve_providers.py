"""Provider-selection tests for local and managed Knowledge Base retrieval."""

from __future__ import annotations

import pytest

from supportrouter import retrieve as retrieval


class FakeBedrockClient:
    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response or {"retrievalResults": []}
        self.error = error
        self.calls: list[dict] = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def test_bedrock_retriever_maps_results_to_citation_contract(monkeypatch) -> None:
    client = FakeBedrockClient(
        {
            "retrievalResults": [
                {
                    "content": {"text": "Returns are accepted within 30 days."},
                    "location": {
                        "s3Location": {
                            "uri": "s3://synthetic/knowledge_base/pol-returns-001.md"
                        }
                    },
                    "score": 0.87,
                }
            ]
        }
    )
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "bedrock")
    monkeypatch.setenv("SUPPORTROUTER_KB_ID", "KB123")
    monkeypatch.setattr(retrieval, "_bedrock_client", lambda: client)

    citations = retrieval.retrieve("What is the return window?", "faq_policy", limit=3)

    assert citations == [
        {
            "doc_id": "pol-returns-001",
            "title": "pol-returns-001",
            "excerpt": "Returns are accepted within 30 days.",
            "score": 0.87,
        }
    ]
    assert client.calls == [
        {
            "knowledgeBaseId": "KB123",
            "retrievalQuery": {"text": "What is the return window?"},
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {"numberOfResults": 3}
            },
        }
    ]


def test_bedrock_retriever_removes_flattened_front_matter(monkeypatch) -> None:
    client = FakeBedrockClient(
        {
            "retrievalResults": [
                {
                    "content": {
                        "text": (
                            "---\r doc_id: faq-powerdock-001 policy_type: faq "
                            "title: PowerDock Duo Compatibility (Synthetic) --- "
                            "# PowerDock Duo Compatibility Supports video over USB-C."
                        )
                    },
                    "location": {
                        "s3Location": {"uri": "s3://synthetic/unrelated-name.md"}
                    },
                    "score": 0.91,
                }
            ]
        }
    )
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "bedrock")
    monkeypatch.setenv("SUPPORTROUTER_KB_ID", "KB123")
    monkeypatch.setattr(retrieval, "_bedrock_client", lambda: client)

    citation = retrieval.retrieve("compatible?", "product_question")[0]

    assert citation["doc_id"] == "faq-powerdock-001"
    assert citation["title"] == "PowerDock Duo Compatibility (Synthetic)"
    assert citation["excerpt"] == (
        "# PowerDock Duo Compatibility Supports video over USB-C."
    )


def test_bedrock_retriever_removes_multiline_front_matter(monkeypatch) -> None:
    client = FakeBedrockClient(
        {
            "retrievalResults": [
                {
                    "content": {
                        "text": (
                            "---\n"
                            "doc_id: pol-returns-001\n"
                            "policy_type: returns\n"
                            "title: VoltEdge Returns Policy (Synthetic)\n"
                            "---\n"
                            "# Returns Policy\nReturns are accepted within 30 days."
                        )
                    },
                    "location": {
                        "s3Location": {"uri": "s3://synthetic/pol-returns-001.md"}
                    },
                    "score": 0.88,
                }
            ]
        }
    )
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "bedrock")
    monkeypatch.setenv("SUPPORTROUTER_KB_ID", "KB123")
    monkeypatch.setattr(retrieval, "_bedrock_client", lambda: client)

    citation = retrieval.retrieve("return window", "faq_policy")[0]

    assert citation["doc_id"] == "pol-returns-001"
    assert citation["title"] == "VoltEdge Returns Policy (Synthetic)"
    assert citation["excerpt"] == (
        "# Returns Policy Returns are accepted within 30 days."
    )


def test_bedrock_retriever_requires_knowledge_base_id(monkeypatch) -> None:
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "bedrock")
    monkeypatch.delenv("SUPPORTROUTER_KB_ID", raising=False)

    with pytest.raises(RuntimeError, match="SUPPORTROUTER_KB_ID is required"):
        retrieval.retrieve("question", "faq_policy")


def test_unknown_retriever_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "mystery")

    with pytest.raises(ValueError, match="must be 'local' or 'bedrock'"):
        retrieval.retrieve("question", "faq_policy")


def test_blank_retriever_value_defaults_to_local(monkeypatch) -> None:
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "   ")

    citations = retrieval.retrieve(
        "Is PowerDock Duo compatible with my laptop?",
        "product_question",
    )

    assert citations[0]["doc_id"] == "faq-powerdock-001"


def test_configured_bedrock_failure_does_not_silently_fallback(monkeypatch) -> None:
    client = FakeBedrockClient(error=RuntimeError("managed retrieval failed"))
    monkeypatch.setenv("SUPPORTROUTER_RETRIEVER", "bedrock")
    monkeypatch.setenv("SUPPORTROUTER_KB_ID", "KB123")
    monkeypatch.setattr(retrieval, "_bedrock_client", lambda: client)

    with pytest.raises(RuntimeError, match="managed retrieval failed"):
        retrieval.retrieve("question", "faq_policy")
