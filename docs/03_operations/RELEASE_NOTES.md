# Release Notes

Canonical releases: GitHub Releases. This file mirrors **measured** results only.

## Unreleased / dormancy-safe revision

| Metric | Value | Evidence |
|--------|-------|----------|
| Autonomous resolution rate | not measured | — |
| Cost per conversation | not measured | — |
| Prompt-caching savings | not measured | — |
| Idle cost (dormant month) | estimated ~$0–2 | ADR-008 assumptions; stacks destroyed |
| OpenSearch Serverless | forbidden | ADR-007; synth tests assert no AOSS |

Infra: CDK stacks for CostGuardrails, KnowledgeBase (S3 Vectors), versioned
Bedrock Guardrails, Observability (≤3 dashboards, 14d logs), and EvalSchedule
(rule only if `enable_reeval_schedule=true`).
