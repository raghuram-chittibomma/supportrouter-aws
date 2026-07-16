# SupportRouter infrastructure (Python CDK)

## Stacks

| Stack | Purpose |
|-------|---------|
| `SupportRouter-CostGuardrails` | AWS Budget ~$20/mo (ADR-008) |
| `SupportRouter-KnowledgeBase` | Bedrock KB on **S3 Vectors** only (ADR-007) |
| `SupportRouter-Observability` | ≤3 dashboards, 14-day log retention |
| `SupportRouter-EvalSchedule` | Eval stub SFN; EventBridge rule **only** if `enable_reeval_schedule=true` |

## Commands

```bash
cd infra
python -m pip install -r requirements.txt
npx cdk synth
npx cdk deploy --all
# Enable weekly re-eval (costs Bedrock tokens):
npx cdk deploy SupportRouter-EvalSchedule -c enable_reeval_schedule=true
```

No VPC / NAT. Tear down with `../scripts/teardown.ps1` or `../scripts/teardown.sh`.
