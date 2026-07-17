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
# Supervisor: Refresh queue → click a queue row → Approve/Reject selected session
```

Supervisor reviews `pending_approval` / `escalated` sessions in the UI.
Approve/Reject is restricted to explicit pending refund approval records;
escalations are view-only in this local slice. Approval decisions are
idempotent, conflicting retries are rejected, and the UI explicitly reports
that no refund was executed.

Sessions and approval records live only in the local process and are lost on
restart. DynamoDB persistence for sessions/`ApprovalRequest` decisions and real
refund execution are deferred to the AWS completion of #16.

### Lambda tool contracts

`SupportRouter-Tools` synthesizes three separate Python Lambdas and IAM roles:

- `get_order_status`: read `Orders`
- `initiate_return`: read `Orders`, write `Returns`
- `issue_refund`: read `Orders`, write `RefundRequests`

Invoke payloads use `{"order_id": "VE-####"}`. Return/refund writes are
conditional and idempotent. Refund responses and records always report
`execution_status=not_executed`; this stack has no payment integration.

The current local graph still uses `src/supportrouter/tools_local.py`. Live
Lambda invocation waits for the runtime adapter, and the deployed `Orders`
table must be seeded with synthetic fixtures before use. `scripts/reseed.py`
does not load DynamoDB Orders yet; that remains in #13 rather than this tools
slice.

### Local observability

Each local agent run emits structured JSON events with:

- `correlation_id` linking the request to `session_id`
- per-step traces for validate/input guardrail/classify/route/retrieve|tools/
  draft/output guardrail/confidence/HITL
- step-local status (`ok`, `skipped`, `error`) separate from conversation outcome
- explicit `usage` and `cost_usd` fields that remain `null` / `not_measured`

Default sink is process-local memory for tests. JSON-line logging is available
for CloudWatch Logs Insights once the agent Lambda is deployed. The CDK
Observability stack already creates the three dormancy-safe dashboards as stubs
(`supportrouter-runtime`, `supportrouter-cost-signals`, `supportrouter-evals`).

### Guardrail behavior

Local runs apply the versioned deterministic policy at input and output
boundaries. A block returns a fixed safe message, records only category names,
sets `status=rejected`, and prevents downstream processing. It does not retain
or emit matched sensitive text; the demo UI replaces the blocked user turn with
`[redacted: guardrail-blocked input]`. Local matching is a narrow demo-regex
fallback, not production-equivalent PII or safety coverage.

The `SupportRouter-Guardrails` CDK stack synthesizes the managed Bedrock policy
and immutable version. Local traces identify
`supportrouter-local-guardrail/local-v0.2`; this means the deterministic fallback
ran, not that AWS evaluated the content. After deployment, record the stack's
`GuardrailIdentifier` and `GuardrailVersion` outputs in the runtime adapter.

### Prompt caching hooks

Versioned cacheable prefixes are available for:

- agent static system instructions + tool schemas (`agent-prefix-v0.1`)
- eval judge system instructions + rubric (`v0.1-rubric-draft`)

These are identity/digest contracts until a Bedrock adapter consumes
`CacheablePrefix.blocks`. Request messages, session IDs, correlation IDs, and
scenario inputs are appended outside these stable prefixes. Local runs and
scorecards report `cache_enabled=false`, `cache_status=not_configured`, and null
cache token counts. Agent results and scorecards include the applicable prefix
version and SHA-256 digest. Conversation-end events forward cache read/write
usage when a future provider adapter supplies it. Do not claim cache savings
until a supported Bedrock model/region returns measured cache-read/write usage.

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
- [ ] No `supportrouter-orders`, `supportrouter-returns`, or
  `supportrouter-refundrequests` tables remain
- [ ] No `supportrouter-get-order-status`, `supportrouter-initiate-return`, or
  `supportrouter-issue-refund` Lambdas remain
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

Uploads synthetic fixture guidance and KB markdown to the configured S3 doc
bucket, then triggers Knowledge Base ingestion sync when `KB_ID` / stack outputs
are available. It does **not** currently write the DynamoDB `Orders` table.
**On-demand only** — no standing ingestion schedule.

Use the managed KB in a local CLI run:

```bash
export SUPPORTROUTER_RETRIEVER=bedrock
export SUPPORTROUTER_KB_ID=<KnowledgeBaseId stack output>
export AWS_DEFAULT_REGION=us-east-1
python -m supportrouter.cli "Does PowerDock Duo support video over USB-C?"
```

PowerShell uses `$env:SUPPORTROUTER_RETRIEVER = "bedrock"` and
`$env:SUPPORTROUTER_KB_ID = "<id>"`; set `$env:AWS_DEFAULT_REGION` to the
Knowledge Base region. Local retrieval remains the default when these variables
are absent. Managed retrieval is billable and does not silently fall back to
local documents on an AWS error.

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
python -m evals.harness \
  --dataset evals/datasets/v0.1_golden.json \
  --task-type order_status \
  --task-type faq_policy
```

The local harness writes a scorecard under `evals/scorecards/`, but clearly
marks candidate execution, judge metrics, token usage, cost, and overall pass
as incomplete. Do not use local-stub scorecards for routing or release claims.
Live Bedrock completion remains gated by issues #24 and #25.

## Cost guardrails

- AWS Budget alert: **$20/month**, filtered by tag `Project=supportrouter` (ADR-008)
- Set a real alert inbox: `cdk deploy -c budget_alert_email=you@example.com` (default is a placeholder)
- CloudWatch: ≤ **3** dashboards; log retention **14 days** (7–14 allowed)
- Vector store: **S3 Vectors only** (ADR-007) — never OpenSearch Serverless

## Incident / escalation (product)

Supervisor decides pending refund approvals and views escalated sessions via
the thin Gradio demo UI (`python -m supportrouter.ui`). Escalation disposition
and a supervisor CLI are not part of the local v0.1 slice.
