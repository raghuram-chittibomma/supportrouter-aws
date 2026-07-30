# Release Notes

Canonical releases: [GitHub Releases](https://github.com/raghuram-chittibomma/supportrouter-aws/releases).
This file mirrors **measured** results only. Unmeasured claims stay explicit.

## v0.1.0 — Eval-Routed Agent Demo (2026-07-29)

Technical delivery for milestone **v0.1 Eval-Routed Agent Demo**: classify →
route → retrieve/tools → draft → confidence → HITL, plus a measured live
Bedrock eval scorecard. Chat drafting remains a **local stub** (no Bedrock
invoke on the chat Lambda). Product walkthrough stories (#44–#50) are tracked
separately for demo acceptance.

### Measured metrics

| Metric | Value | Evidence |
|--------|-------|----------|
| Golden eval overall pass (3 models × 2 tasks, capped) | `true` | [`scorecard-v0.1-live-bedrock-2026-07-29.json`](../../evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json) |
| Programmatic pass rate (that run) | `1.0` (6/6) | same scorecard `summary` |
| Live eval Bedrock cost | `$0.0102` | same scorecard `cost.total_usd`; basis: tokens × published on-demand rates |
| Chat Lambda cold start (Init Duration) | `2204 ms` | CloudWatch REPORT for `supportrouter-chat` on 2026-07-17 |
| Chat API end-to-end (cold) | `~3892 ms` | first live `POST /chat` |
| Chat API end-to-end (warm) | `~407 ms` | second live `POST /chat` |

### Explicitly not measured

| Metric | Status |
|--------|--------|
| Autonomous resolution rate (production-like traffic) | not measured |
| Cost per conversation (runtime chat drafting) | not measured (local stub) |
| Prompt-caching savings | not measured (`cache_enabled=false`) |
| Idle cost (dormant month) | estimated ~$0–2 (ADR-008; not a billing extract) |

### What shipped

- **Runtime:** LangGraph agent with deterministic confidence (ADR-009), refund HITL threshold (ADR-010/017), local + managed KB retrieve path, isolated Lambda tools.
- **Edge:** HTTP `POST /chat` (ADR-014/015) with Sessions + ApprovalRequests DynamoDB persistence; CLI `list-pending` / `decide`.
- **Eval:** Local-stub harness default; `--live` Bedrock Converse candidates + Haiku 4.5 judge (ADR-016); scorecard artifact under `evals/scorecards/`.
- **Cost guardrails:** $20/mo budget tag `Project=supportrouter`; dormancy-safe CDK defaults (ADR-008); OpenSearch Serverless forbidden (ADR-007).

### Release-readiness notes

- Implementation issues for the technical demo path are closed; open milestone items are product stories (#44–#50) for walkthrough acceptance (deferred from this release tag).
- Synthetic data only; no real customer content.
- Cost note for this release process: **not measured** beyond the linked scorecard token estimate.

## Prior notes

Earlier “Unreleased / dormancy-safe revision” content is superseded by **v0.1.0** above.
