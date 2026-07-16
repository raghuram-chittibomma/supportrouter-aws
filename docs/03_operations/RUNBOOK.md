# Runbook

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
python -m supportrouter.cli "Where is my order #VE-1001?"
```

### Thin demo UI

```bash
python -m supportrouter.ui
# http://127.0.0.1:7860 — Customer chat + Supervisor HITL tabs
```

Supervisor reviews `pending_approval` / `escalated` sessions in the UI (or via CLI helpers). In-memory queue lives only for that local process.

## AWS deploy

```bash
cd infra
cdk bootstrap                 # once per account/region
cdk deploy --all
cd ..
python scripts/reseed.py      # on-demand synthetic data + KB docs upload
```

Cost note: record estimated/measured spend per milestone. Prefer tiny models. **Tear down between demo periods** (ADR-008).

## Teardown (dormancy)

```bash
# Bash
./scripts/teardown.sh

# PowerShell
.\scripts\teardown.ps1
```

Both run `cdk destroy --all` in `infra/` (after confirmation unless `--force`).

### Post-teardown verification checklist

After destroy, confirm in `us-east-1` (or deploy region):

- [ ] No SupportRouter CloudFormation stacks remain (`aws cloudformation list-stacks`)
- [ ] No OpenSearch Serverless collections for this project (`aws opensearchserverless list-collections`) — deleting a KB does **not** always delete AOSS
- [ ] No SupportRouter Bedrock Knowledge Bases remain
- [ ] No SupportRouter S3 Vectors buckets / KB doc buckets left unintended
- [ ] No SupportRouter log groups with **never-expire** retention
- [ ] No SupportRouter VPC or NAT Gateways (we must not create any)
- [ ] EventBridge: no SupportRouter re-eval rules left behind

If an orphaned AOSS collection is found and confirmed unused:

```bash
aws opensearchserverless delete-collection --id <collection-id>
```

## Reseed (cold start after deploy)

```bash
python scripts/reseed.py
```

Uploads synthetic orders/routing fixtures guidance and KB markdown to the configured S3 doc bucket, then triggers Knowledge Base ingestion sync when `KB_ID` / stack outputs are available. **On-demand only** — no standing ingestion schedule.

## Eval schedule toggle (default OFF)

CDK context `enable_reeval_schedule` defaults to `false` (no EventBridge rule created).

```bash
# Enable scheduled re-evals (burns Bedrock tokens on each run)
cd infra
cdk deploy --all -c enable_reeval_schedule=true

# Disable again (default) — rule is not created
cdk deploy --all -c enable_reeval_schedule=false
```

On-demand eval (preferred while dormant):

```bash
python -m evals.harness --dataset evals/datasets/v0.1.jsonl
```

(Module lands with issue #17; command is the target interface.)

## Cost guardrails

- AWS Budget alert: **$20/month**, filtered by tag `Project=supportrouter` (ADR-008)
- Set a real alert inbox: `cdk deploy -c budget_alert_email=you@example.com` (default is a placeholder)
- CloudWatch: ≤ **3** dashboards; log retention **14 days** (7–14 allowed)
- Vector store: **S3 Vectors only** (ADR-007) — never OpenSearch Serverless

## Incident / escalation (product)

Supervisor reviews `pending_approval` / `escalated` sessions via the thin Gradio demo UI (`python -m supportrouter.ui`) or CLI in v0.1.
