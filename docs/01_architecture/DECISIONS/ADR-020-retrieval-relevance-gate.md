# ADR-020: Deterministic Retrieval Relevance Gate

## Status

Accepted

## Context

Local keyword retrieve returned top-k documents whenever any token overlapped,
so unsupported FAQ questions (e.g. teleportation) still received citations and
resolved with a grounded-looking answer. ADR-009 treats citation **presence**
as strong evidence; it does not judge citation quality.

## Decision

1. After provider retrieve (local or Bedrock), filter citations with a
   deterministic score threshold:
   - Local / local_fallback: `score >= 4` (integer keyword overlap)
   - Bedrock: `score >= 0.4` (managed similarity float)
2. Filtering runs inside `retrieve()` so all callers share the contract.
3. Empty citations after filtering remain “no evidence”: FAQ/product confidence
   caps at 0.45 and HITL escalates (`confidence < 0.55`) per ADR-009.
4. No LLM relevance judge in v0.3; thresholds are constants that can be tuned
   with retrieval evals / scorecards.

## Consequences

- Unsupported / weakly overlapping questions escalate instead of resolving.
- Supported returns-policy and PowerDock questions still resolve with valid
  `doc_id`s when scores clear the gate.
- Graph notes may include `retrieve:relevance_empty` when nothing survives.
- Threshold changes require test and eval updates.
