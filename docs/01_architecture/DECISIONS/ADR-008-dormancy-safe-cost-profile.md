# ADR-008: Dormancy-Safe Cost Profile

## Status

Accepted

## Context

SupportRouter must have near-zero idle cost between demo periods. Almost the whole stack is pay-per-use (Lambda, Step Functions, EventBridge, API Gateway, DynamoDB on-demand, S3, Bedrock invocation, Guardrails). Remaining risk is accidental always-on capacity (AOSS, VPC/NAT, never-expire logs, scheduled Bedrock evals, unbounded dashboards).

## Decision

1. **Lifecycle:** Prefer `cdk destroy` between demo periods and redeploy on demand. Provide `scripts/teardown` + `scripts/reseed` so cold-start takes minutes.
2. **Eval schedule:** CDK context flag `enable_reeval_schedule` defaults to **`false`**. When false, **do not create** an EventBridge rule (not merely disable it). Manual/on-demand eval remains available.
3. **Budget:** Provision an AWS Budgets alert at **$20/month** via CDK (`CfnBudget`), filtered by cost allocation tag **`Project=supportrouter`** (resources must carry that tag). On a single-purpose demo account this still approximates project spend; replace the placeholder notification email via CDK context `budget_alert_email` before relying on alerts.
4. **CloudWatch:** At most **3** dashboards. Log group retention **7–14 days** (default **14**), never “never expire” for SupportRouter log groups.
5. **Network:** SupportRouter stacks create **no custom VPC and no NAT Gateway**.
6. **Reseed / KB ingestion:** On-demand only (script after deploy). No standing ingestion EventBridge schedule while dormant.
7. **Prompt caching (ADR-005):** Keep checkpoints (agent static prefix, conversation history, eval judge rubric). Until measured, cost planning assumes `cache_enabled=false`. Eval cost scoring may use effective/cached pricing only when scorecards record it.

## Active vs dormant cost model (estimated)

| Mode | Expected | Assumptions |
|------|----------|-------------|
| Dormant month | ~$0–2 | Stacks destroyed; no AOSS; no schedule; no NAT |
| Active demo month | Low tens of USD (alert at $20) | Intermittent Lambda/API/Bedrock; tiny S3 Vectors KB; manual evals; no cache savings assumed |

## Consequences

- RUNBOOK documents enable/disable schedule one-liners and post-teardown verification.
- EVAL_STRATEGY documents token amplification (one agent query → multiple model calls, often 5–10× visible tokens) and schedule default-off.
- Observability and CDK slices must enforce retention and dashboard caps.

## Related

- ADR-007 — S3 Vectors / anti-AOSS
- ADR-005 — prompt caching strategy
- ADR-006 — LangGraph on Lambda
