# SupportRouter infrastructure (Python CDK)

## Stacks

| Stack | Purpose |
|-------|---------|
| `SupportRouter-CostGuardrails` | AWS Budget ~$20/mo (ADR-008) |
| `SupportRouter-KnowledgeBase` | Bedrock KB on **S3 Vectors** only (ADR-007) |
| `SupportRouter-Guardrails` | Versioned Bedrock input/output safety policy (ADR-012) |
| `SupportRouter-Tools` | Three isolated Lambda tools + on-demand DynamoDB tables (ADR-013) |
| `SupportRouter-Api` | Throttled HTTP API + chat Lambda over the agent graph (ADR-014) |
| `SupportRouter-Observability` | ≤3 dashboards, 14-day log retention |
| `SupportRouter-EvalSchedule` | Eval stub SFN always; EventBridge weekly rule **only** if `enable_reeval_schedule=true` (default **false** — manual harness preferred) |

## Commands

```bash
cd infra
python -m pip install -r requirements.txt
npx cdk synth
npx cdk deploy --all
# Schedule stays OFF by default (no EventBridge rule).
# Prefer on-demand: python -m evals.harness [--live]
# Enable weekly re-eval only when intentional (costs Bedrock once harness is wired):
npx cdk deploy SupportRouter-EvalSchedule -c enable_reeval_schedule=true
# Disable again (removes the rule):
npx cdk deploy SupportRouter-EvalSchedule -c enable_reeval_schedule=false
```

No VPC / NAT. Tear down with `../scripts/teardown.ps1` or `../scripts/teardown.sh`.
