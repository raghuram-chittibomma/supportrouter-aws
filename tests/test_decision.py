"""Unit tests for confidence scoring and HITL decisions."""

from supportrouter.decision import hitl_decision, score_confidence


def test_hitl_refund_above_threshold():
    status, reason = hitl_decision(
        task_type="refund_request",
        confidence=0.95,
        refund_amount_usd=159.99,
    )
    assert status == "pending_approval"
    assert reason == "Refund $159.99 exceeds $100 threshold"


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
    assert reason == "Confidence 0.40 below 0.55"


def test_hitl_at_confidence_threshold_resolves():
    assert hitl_decision(
        task_type="faq_policy",
        confidence=0.55,
        refund_amount_usd=None,
    ) == ("resolved", None)


def test_hitl_refund_without_amount_uses_confidence_path():
    assert hitl_decision(
        task_type="refund_request",
        confidence=0.4,
        refund_amount_usd=None,
    ) == ("escalated", "Confidence 0.40 below 0.55")


def test_hitl_refund_threshold_wins_over_low_confidence():
    assert hitl_decision(
        task_type="refund_request",
        confidence=0.1,
        refund_amount_usd=100.01,
    ) == ("pending_approval", "Refund $100.01 exceeds $100 threshold")


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


def test_score_confidence_product_question_uses_citation_signal():
    assert score_confidence(
        classifier_confidence=0.9,
        task_type="product_question",
        citations=[],
        tool_calls=[],
    ) == 0.45
    assert score_confidence(
        classifier_confidence=0.99,
        task_type="product_question",
        citations=[{"doc_id": "faq-powerdock-001"}],
        tool_calls=[],
    ) == 0.95


def test_score_confidence_tool_task_uses_tool_success_signal():
    assert score_confidence(
        classifier_confidence=0.9,
        task_type="order_status",
        citations=[],
        tool_calls=[{"result": {"ok": True}}],
    ) == 0.9
    assert score_confidence(
        classifier_confidence=0.9,
        task_type="order_status",
        citations=[],
        tool_calls=[{"result": {"ok": False}}],
    ) == 0.35


def test_score_confidence_unknown_is_capped():
    assert score_confidence(
        classifier_confidence=0.9,
        task_type="unknown",
        citations=[],
        tool_calls=[],
    ) == 0.4


def test_score_confidence_unlisted_task_only_clamps_and_rounds():
    assert score_confidence(
        classifier_confidence=0.87654,
        task_type="future_task",
        citations=[],
        tool_calls=[],
    ) == 0.877


def test_score_confidence_clamps_and_rounds():
    assert score_confidence(
        classifier_confidence=1.5,
        task_type="faq_policy",
        citations=[{"doc_id": "x"}],
        tool_calls=[],
    ) == 0.95
    assert score_confidence(
        classifier_confidence=-0.2,
        task_type="faq_policy",
        citations=[{"doc_id": "x"}],
        tool_calls=[],
    ) == 0.0
    assert score_confidence(
        classifier_confidence=0.87654,
        task_type="faq_policy",
        citations=[{"doc_id": "x"}],
        tool_calls=[],
    ) == 0.877
