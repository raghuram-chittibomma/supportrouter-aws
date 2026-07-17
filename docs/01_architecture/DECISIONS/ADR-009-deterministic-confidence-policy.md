# ADR-009: Deterministic Evidence-Capped Confidence Policy

## Status

Accepted

## Context

SupportRouter must decide whether to resolve a request or escalate it. Candidate
signals include classifier confidence, retrieval evidence, tool success, and an
LLM's self-rated certainty.

A weighted average is unsafe for v0.1 because a high classifier or self-rating
could offset missing citations or a failed tool call. Self-rated certainty is
also uncalibrated until live model evaluations exist.

## Decision

Use a deterministic **evidence-capped minimum**, implemented by
`score_confidence` in `src/supportrouter/decision.py`.

Start with classifier confidence `c`, then apply the cap for the classified task:

| Task type | Evidence | Cap |
|-----------|----------|-----|
| `faq_policy`, `product_question` | At least one citation | `0.95` |
| `faq_policy`, `product_question` | No citation | `0.45` |
| `order_status`, `return_request`, `refund_request` | Any tool result has `ok=true` | `0.95` |
| `order_status`, `return_request`, `refund_request` | No successful tool result | `0.35` |
| `unknown` | Any | `0.40` |

The normative algorithm is:

```text
score = c
if task_type has a listed evidence_cap:
    score = min(score, evidence_cap)
return round(clamp(score, 0.0, 1.0), 3)
```

Therefore, a task without a listed evidence cap only clamps and rounds `c`.

HITL uses these deterministic rules in order:

1. A `refund_request` with `refund_amount_usd > 100.0` becomes
   `pending_approval`, regardless of confidence.
2. Otherwise, confidence `< 0.55` becomes `escalated`.
3. Otherwise, the outcome is `resolved`.

The boundaries are strict: `$100.00` does not require approval and confidence
`0.55` does not trigger escalation.

LLM self-rated certainty is excluded from v0.1. It may be introduced only after
calibration against versioned eval scorecards; doing so requires a superseding
ADR and new deterministic tests.

## Consequences

- Missing evidence cannot be hidden by a high classifier score.
- The same state always produces the same score and outcome.
- The score is a routing/HITL heuristic, not a calibrated probability.
- Successful evidence cannot raise a weak classifier score; it can only cap it.
- Current caps and thresholds require exact-match unit tests.
- Live evals may show that task-specific thresholds need adjustment. Changes
  must be measured, versioned, and must not rewrite this ADR.
