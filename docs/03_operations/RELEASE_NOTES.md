# Release Notes

Canonical releases: [GitHub Releases](https://github.com/raghuram-chittibomma/supportrouter-aws/releases).
This file mirrors **measured** results only. Unmeasured claims stay explicit.

## Unreleased — EvalSchedule opt-in (#75)

### Shipped

- `SupportRouter-EvalSchedule` deployed with schedule **disabled** by default
  (no EventBridge rule; stub Step Functions + 14-day log group only).
- RUNBOOK: manual harness preferred; enable/disable via
  `enable_reeval_schedule`; teardown names this stack; cost risk called out.

### Cost note

Zero Bedrock from this stack while the schedule is off. Enabling the weekly
rule is intentional and can incur eval/judge tokens once the stub targets a
live harness — measure before claiming. Prefer `python -m evals.harness [--live]`
for on-demand runs.

## Unreleased — Observability dashboards (#71)

### Shipped

- `SupportRouter-Observability`: ≤3 CloudWatch dashboards with Lambda/Bedrock
  metric widgets, 14-day log groups, chat error/throttle alarms (no SNS).
- Chat Lambda activates `LoggingTraceSink` so structured traces land in
  `/aws/lambda/supportrouter-chat`. Dedicated agent/evals log groups remain
  reserved (documented gap).

### Cost note

Dashboards + 14-day retention are dormancy-safe idle cost; ingestion scales with
traffic. No Bedrock spend from this stack alone. Dollar budget remains
`SupportRouter-CostGuardrails` ($20/mo).

## Unreleased — Prompt caching measurement (#72)

### Measured metrics

| Metric | Value | Evidence |
|--------|-------|----------|
| Judge prefix cache status (cold write + warm read) | `hit_and_write` | [`scorecard-v0.1-prompt-cache-2026-07-30.json`](../../evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json) |
| Cache write / read tokens (that run) | `5109` write, `5109` read | same scorecard |
| Measured vs uncached-equivalent cost (2 Converse calls) | `$0.00712915` vs `$0.01045` (**~31.8%** lower) | same scorecard `cache_comparison` |

Basis: Haiku 4.5 on-demand rates with cache write/read pricing; uncached-equivalent prices all input tokens at the full input rate (ADR-021).

### Explicitly not measured

| Metric | Status |
|--------|--------|
| Runtime chat drafting cache savings | not measured (depends on AWS draft traffic within TTL) |
| Conversation-history caching | deferred (ADR-005 / ADR-021) |

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
| Prompt-caching savings | see Unreleased (#72) measured scorecard; v0.1.0 release assumed `cache_enabled=false` |
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
