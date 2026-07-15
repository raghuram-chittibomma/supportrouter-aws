# ADR-003: Model Candidates and Routing Policy

## Status

Accepted

## Context

SupportRouter must route each task type to an optimal Bedrock model on quality, cost, and latency. Candidates should include Claude (Haiku/Sonnet) and Amazon Nova family.

## Decision

1. **Candidate set (logical IDs; confirm account/region model IDs at implement time):** Claude Haiku, Claude Sonnet, Amazon Nova Micro, Amazon Nova Lite.
2. **Routing rule:** for each task type, select the **cheapest** candidate whose quality score is within **5%** of the best quality score on that task type, subject to a p95 latency cap recorded in the scorecard.
3. **v0.1:** seed the routing table manually; milestone 2 generates updates from scorecards.

## Consequences

- Deterministic lookup at runtime (no LLM in the router).
- Exact Bedrock model IDs tracked in config/scorecards, not hard-coded claims in README.
- Open question issue for account-available model IDs.
