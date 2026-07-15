# ADR-005: Prompt Caching Strategy

## Status

Accepted

## Context

Repeated system prefixes, tool schemas, and judge rubrics dominate token cost. Bedrock prompt caching can reduce cost/latency where supported.

## Decision

Cache these stable prefixes when the selected model/region supports it:

1. Agent static system prompt + tool schema prefix.
2. Conversation history segments eligible for cache (per Bedrock rules).
3. Eval judge rubric prefix in the offline eval plane.

Measure cache hit savings in scorecards/observability before claiming README metrics.

## Consequences

- Prompt layout must keep cacheable content stable and ordered per Bedrock guidance.
- If a model lacks caching, router/observability records `cache_enabled=false` — no fabricated savings.
