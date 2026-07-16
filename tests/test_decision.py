"""Unit tests for confidence scoring and HITL decisions."""

from supportrouter.decision import hitl_decision, score_confidence


def test_hitl_refund_above_threshold():
    status, reason = hitl_decision(
        task_type="refund_request",
        confidence=0.95,
        refund_amount_usd=159.99,
    )
    assert status == "pending_approval"
    assert reason is not None
    assert "100" in reason


def test_hitl_refund_at_threshold_resolves():
    status, reason = hitl_decision(
        task_type="refund_request",
        confidence=0.95,
        refund_amount_usd=100.0,
    )
    assert status == "resolved"
    assert reason is None


def test_hitl_low_confidence_escalates():
    status, reason = hitl_decision(
        task_type="faq_policy",
        confidence=0.4,
        refund_amount_usd=None,
    )
    assert status == "escalated"
    assert reason is not None


def test_score_confidence_requires_citations_for_faq():
    assert score_confidence(
        classifier_confidence=0.9,
        task_type="faq_policy",
        citations=[],
        tool_calls=[],
    ) == 0.45
    assert score_confidence(
        classifier_confidence=0.9,
        task_type="faq_policy",
        citations=[{"doc_id": "x"}],
        tool_calls=[],
    ) == 0.9
