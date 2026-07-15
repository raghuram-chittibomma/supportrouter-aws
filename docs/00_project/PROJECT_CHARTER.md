# Project Charter — SupportRouter

## Mission

Deliver a portfolio-grade, eval-driven AWS customer support agent for fictional VoltEdge Electronics that demonstrates production disciplines (routing, RAG, tools, guardrails, HITL, observability, IaC) and an AI-assisted GitHub-first SDLC.

## Success criteria (v0.1)

- End-to-end demo: classify → route → (retrieve/tools) → respond with citations/confidence/status.
- Refunds &gt; $100 create approval requests; low confidence escalates.
- Eval harness produces a scorecard for ≥3 models × ≥2 task types.
- All AWS resources via CDK; teardown script available.
- README claims only measured metrics (or explicitly "not measured").
- Traceability: brief → issues → PRs → tests/evals → release.

## In scope / out of scope

See [`AI_ORCHESTRATOR_BRIEF.md`](AI_ORCHESTRATOR_BRIEF.md) v0.1 scope and [`PRODUCT_BRIEF.md`](PRODUCT_BRIEF.md).

## Constraints

Synthetic data only · measured metrics only · low AWS cost · least-privilege IAM · ADRs for significant decisions · no build-time agent defs in-repo.

## Stakeholders

Portfolio author (owner) · fictional VoltEdge support org · hiring-manager audience.
