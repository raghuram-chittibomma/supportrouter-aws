# Release Notes

Canonical releases: GitHub Releases. This file mirrors **measured** results only.

## Unreleased / dormancy-safe revision

| Metric | Value | Evidence |
|--------|-------|----------|
| Autonomous resolution rate | not measured | — |
| Cost per conversation | not measured | — |
| Prompt-caching savings | not measured | — |
| Chat Lambda cold start | measured 2204 ms Init Duration | CloudWatch REPORT for `supportrouter-chat` on 2026-07-17 |
| Chat API end-to-end (cold) | measured ~3892 ms | first live `POST /chat` |
| Chat API end-to-end (warm) | measured ~407 ms | second live `POST /chat` |
| Idle cost (dormant month) | estimated ~$0–2 | ADR-008 assumptions; stacks destroyed |
| OpenSearch Serverless | forbidden | ADR-007; synth tests assert no AOSS |

Infra: CDK stacks for CostGuardrails, KnowledgeBase (S3 Vectors), versioned
Bedrock Guardrails, isolated Lambda tools/on-demand DynamoDB, a throttled HTTP
chat edge (`SupportRouter-Api`, ADR-014), Observability (≤3 dashboards, 14d
logs), and EvalSchedule (rule only if `enable_reeval_schedule=true`).

Edge: CLI (`supportrouter.cli`, now with `--session-id`) and an HTTP chat Lambda
(`supportrouter.api.handler`) both wrap `run_agent`. Drafting is a local stub, so
the edge grants no Bedrock/DynamoDB permissions and cost stays `not_measured`.
The chat Lambda asset now includes pinned ARM64 runtime dependencies and
synthetic fixtures (ADR-015), enabling live local-stub invocation.
