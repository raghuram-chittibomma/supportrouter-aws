# Release Notes

Canonical releases: [GitHub Releases](https://github.com/raghuram-chittibomma/supportrouter-aws/releases).
This file mirrors **measured** results only. Unmeasured claims stay explicit.

## Unreleased — Portfolio demo talk track (#107)

### Shipped

- [`docs/00_project/DEMO_SCRIPT_AWS_AI.md`](../../docs/00_project/DEMO_SCRIPT_AWS_AI.md)
  — timed (~15–20 min) demo: AWS runtime → AI engineering loop → ops; show/say/
  do-not-claim lines; linked from README + portfolio walkthrough.

### Cost note

Docs only (not measured).

## Unreleased — Portfolio front door (#105)

### Shipped

- README rewritten for hiring-manager audit path (measured table, v0.6 status,
  links to walkthrough + AWS diagrams + releases).
- [`docs/00_project/PORTFOLIO_WALKTHROUGH.md`](../../docs/00_project/PORTFOLIO_WALKTHROUGH.md)
  (~5–10 min).

### Cost note

Docs only (not measured).

## v0.6.0 — AgentCore dual-run stretch (2026-07-31)

Milestone **v0.6 AgentCore / MCP Stretch** (ADR-024): opt-in AgentCore Runtime
+ optional Gateway MCP over tool Lambdas, without cutting over the Api Lambda
chat edge.

### Shipped

- **ADR-024 / #92:** dual-run host path (keep Api; SigV4 demos; us-east-1).
- **#94:** `SupportRouter-AgentCore` (`-c enable_agentcore=true`) — HTTP Runtime
  via code asset + `BedrockAgentCoreApp` wrapping `run_agent`; 120s idle timeout.
- **#93:** `SupportRouter-AgentCoreGateway` (`-c enable_agentcore_gateway=true`) —
  IAM-auth MCP targets for order/return/refund Lambdas (`target___tool` names).
- **#95:** Local adapter smoke (`faq-policy-001`) + explicit not-measured
  scorecard.

### Explicitly not measured

| Metric | Status | Evidence |
|--------|--------|----------|
| AgentCore Runtime session cost | not measured | [`scorecard-v0.6-agentcore-not-measured`](../../evals/scorecards/scorecard-v0.6-agentcore-not-measured.json) |
| AgentCore Gateway invoke cost | not measured | same |
| AgentCore golden quality / judge pass | not measured | same |
| Local adapter smoke (faq-policy-001) | wiring only | `tests/test_agentcore_smoke.py` |

Do not equate AgentCore host quality with
[`scorecard-v0.1-live-bedrock-2026-07-29`](../../evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json).

### Release-readiness notes

- Milestone v0.6: **0 open issues** (closed on GitHub).
- Synthetic data only; Api Lambda remains the default demo edge.
- Destroy AgentCore stacks when dormant (ADR-008); context flags default **off**.
- Cost note for this release process: **not measured** beyond linked scorecards.

## v0.5.0 — Routing + platform hardening (2026-07-31)

Cumulative release of milestones **v0.2–v0.5** on `main` after
[v0.1.0](https://github.com/raghuram-chittibomma/supportrouter-aws/releases/tag/v0.1.0).
Delivery order on GitHub was interleaved; this tag is the first post-v0.1.0
GitHub Release that includes all of that work.

### v0.2 — Routing policy generator

- Offline `python -m evals.generate_routing_policy` (ADR-022) from measured
  scorecards; `--adopt --yes` for the JSON seed.
- DynamoDB `supportrouter-routingtable` +
  `python scripts/publish_routing_table.py` + chat `GetItem` lookup (ADR-023 /
  #88). File seed remains the local fallback.
- Seed version in tree:
  `generated-from-scorecard-v0.1-live-bedrock-2026-07-29`.

**Cost note:** generate/adopt offline (not measured as Bedrock). DynamoDB
publish is on-demand PutItem only (not measured as Bedrock). Routing
quality/cost/latency claims must cite the source scorecard.

### v0.3 — Guardrails + draft honesty + retrieval relevance

- Managed Bedrock Guardrails in the runtime graph (#70).
- Draft honesty: stop overclaiming refund/return execution (#73).
- Escalate when KB evidence is weak (#74).

**Cost note:** Guardrail ApplyGuardrail tokens/calls not separately scored in
this release; cite live scorecards for Bedrock spend.

### v0.4 — Prompt caching + observability

#### Measured metrics (#72)

| Metric | Value | Evidence |
|--------|-------|----------|
| Judge prefix cache status (cold write + warm read) | `hit_and_write` | [`scorecard-v0.1-prompt-cache-2026-07-30.json`](../../evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json) |
| Cache write / read tokens (that run) | `5109` write, `5109` read | same scorecard |
| Measured vs uncached-equivalent cost (2 Converse calls) | `$0.00712915` vs `$0.01045` (**~31.8%** lower) | same scorecard `cache_comparison` |

Basis: Haiku 4.5 on-demand rates with cache write/read pricing; uncached-equivalent prices all input tokens at the full input rate (ADR-021).

#### Explicitly not measured

| Metric | Status |
|--------|--------|
| Runtime chat drafting cache savings | not measured (depends on AWS draft traffic within TTL) |
| Conversation-history caching | deferred (ADR-005 / ADR-021) |

#### Observability (#71)

- `SupportRouter-Observability`: ≤3 CloudWatch dashboards with Lambda/Bedrock
  metric widgets, 14-day log groups, chat error/throttle alarms (no SNS).
- Chat Lambda `LoggingTraceSink` → `/aws/lambda/supportrouter-chat`.

**Cost note:** Dashboards + 14-day retention are dormancy-safe idle cost;
ingestion scales with traffic. No Bedrock spend from Observability alone.
Dollar budget remains `SupportRouter-CostGuardrails` ($20/mo).

### v0.5 — EvalSchedule opt-in (#75)

- `SupportRouter-EvalSchedule` deployed with schedule **disabled** by default
  (no EventBridge rule; stub Step Functions + 14-day log group only).
- Prefer `python -m evals.harness [--live]`; enable weekly only with
  `enable_reeval_schedule=true`.

**Cost note:** Zero Bedrock from this stack while the schedule is off.

### Release-readiness notes

- Milestones v0.2–v0.5: **0 open issues** (closed on GitHub).
- Synthetic data only; no real customer content.
- Follow-on stretch shipped as **v0.6.0** (AgentCore dual-run).
- Cost note for this release process: **not measured** beyond linked scorecards.

## v0.1.0 — Eval-Routed Agent Demo (2026-07-29)

Technical delivery for milestone **v0.1 Eval-Routed Agent Demo**: classify →
route → retrieve/tools → draft → confidence → HITL, plus a measured live
Bedrock eval scorecard. Chat drafting remains a **local stub** (no Bedrock
invoke on the chat Lambda) unless a later runtime mode enables it.

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
| Prompt-caching savings | see **v0.5.0** (#72) measured scorecard; v0.1.0 assumed `cache_enabled=false` |
| Idle cost (dormant month) | estimated ~$0–2 (ADR-008; not a billing extract) |

### What shipped

- **Runtime:** LangGraph agent with deterministic confidence (ADR-009), refund HITL threshold (ADR-010/017), local + managed KB retrieve path, isolated Lambda tools.
- **Edge:** HTTP `POST /chat` (ADR-014/015) with Sessions + ApprovalRequests DynamoDB persistence; CLI `list-pending` / `decide`.
- **Eval:** Local-stub harness default; `--live` Bedrock Converse candidates + Haiku 4.5 judge (ADR-016); scorecard artifact under `evals/scorecards/`.
- **Cost guardrails:** $20/mo budget tag `Project=supportrouter`; dormancy-safe CDK defaults (ADR-008); OpenSearch Serverless forbidden (ADR-007).

### Release-readiness notes

- Implementation issues for the technical demo path are closed.
- Synthetic data only; no real customer content.
- Cost note for this release process: **not measured** beyond the linked scorecard token estimate.

## Prior notes

Earlier “Unreleased / dormancy-safe revision” content is superseded by **v0.1.0**
and **v0.5.0** above.
