# Runbook

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
python -m supportrouter.cli "Where is my order #VE-1001?"
python -m supportrouter.cli --runtime-mode aws "Where is my order #VE-1001?"
python -m supportrouter.cli --session-id demo-1 "Any update on VE-1001?"
python -m supportrouter.cli list-pending
python -m supportrouter.cli decide <session_id> approve --note "ok"
```

### Thin demo UI

```bash
python -m supportrouter.ui
# http://127.0.0.1:7860 — Customer chat + Supervisor HITL tabs
# Customer tab: Local (stubs) vs AWS (Bedrock) runtime mode switch
# Supervisor: Refresh queue → click a queue row → Approve/Reject selected session
```

Customer chat defaults to **Local** (no Bedrock spend). **AWS** mode uses Bedrock
Converse drafting, Tools Lambdas, and KB retrieve when configured (ADR-018).
Supervisor reviews `pending_approval` / `escalated` sessions in the UI or via
CLI `list-pending` / `decide`. Approve/Reject is restricted to explicit pending
refund approval records; escalations are view-only in this slice. Approval
decisions are idempotent, conflicting retries are rejected, and both paths
report that no refund was executed (`execution_status=not_executed`).

**Local Gradio/CLI AWS mode** needs AWS credentials and a region. Tool Lambda
names default to the CDK `supportrouter-*` functions when env vars are unset.
Optional KB retrieve:

```powershell
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:SUPPORTROUTER_KB_ID = "CFGK5X8ZUN"   # KnowledgeBaseId stack output
python -m supportrouter.ui
```

Without DynamoDB env vars, sessions live only in the local process and are lost
on restart. With `SESSIONS_TABLE_NAME` and `APPROVALS_TABLE_NAME` set (ApiStack
outputs after deploy), the same repository API persists to DynamoDB (ADR-017).
Refund **execution** remains out of scope.

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

### HTTP chat edge

`SupportRouter-Api` fronts the agent graph with a throttled HTTP API and a chat
Lambda (`supportrouter.api.handler`). The route is unauthenticated by design for
the synthetic demo; the throttle (10 rps / burst 20), a 16 KiB body cap, and a
4000-char `message` cap bound abuse. CDK bundles pinned Linux ARM64 runtime
dependencies plus the synthetic local fixtures (ADR-015). After deployment,
call the stack's `ChatApiEndpoint` output:

```bash
curl -sS -X POST "$CHAT_API_ENDPOINT/chat" \
  -H "content-type: application/json" \
  -d '{"message": "Where is my order VE-1001?", "session_id": "demo-1"}'
```

Contract: `POST /chat` with `{"message", "session_id"?}`. Returns `200` with the
agent result, `400` for bad input, `422` when the agent rejects a turn (e.g. a
guardrail block), and `500` on internal error. Every response includes an
`x-correlation-id` header for trace correlation. Drafting is still a local stub,
so the Lambda role only writes logs and cost stays `not_measured`. Bedrock
drafting, managed Guardrails, and remote Lambda-tool invocation remain deferred.

The first CDK build downloads the pinned dependencies listed in
`infra/chat_runtime_requirements.txt`; local bundling cross-installs CPython 3.12
Linux ARM64 wheels without Docker. Set
`SUPPORTROUTER_FORCE_DOCKER_BUNDLING=1` to force the equivalent Docker path;
CDK also falls back to it if local installation fails.

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

Guardrail nodes run after validate (input) and after draft (output)
([ADR-012](../01_architecture/DECISIONS/ADR-012-guardrail-boundaries.md),
[ADR-019](../01_architecture/DECISIONS/ADR-019-dual-provider-guardrails.md)).

- **`runtime_mode=local`:** versioned deterministic policy
  (`supportrouter-local-guardrail` / `local-v0.2`). A block returns a fixed safe
  message, records category names only, sets `status=rejected`, and prevents
  downstream processing. The demo UI replaces the blocked user turn with
  `[redacted: guardrail-blocked input]`.
- **`runtime_mode=aws`:** Bedrock `ApplyGuardrail` using
  `SUPPORTROUTER_GUARDRAIL_ID` and `SUPPORTROUTER_GUARDRAIL_VERSION` (CDK
  `SupportRouter-Guardrails` outputs; demo account currently
  `3hkym9cgw048` / `1`). Missing IDs fail closed. Result metadata
  `guardrail.provider` is `bedrock`. Guardrails API spend is **not measured**
  in chat `cost_usd` yet.

Local adversarial evals must not claim managed Bedrock execution.

```powershell
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:SUPPORTROUTER_GUARDRAIL_ID = "3hkym9cgw048"
$env:SUPPORTROUTER_GUARDRAIL_VERSION = "1"
python -m supportrouter.ui
```

### Prompt caching hooks

Versioned cacheable prefixes are available for:

- agent static system instructions + tool schemas (`agent-prefix-v0.1`)
- eval judge system instructions + rubric (`v0.1-haiku-4.5`)

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
# Local-stub (no Bedrock spend)
python -m evals.harness \
  --dataset evals/datasets/v0.1_golden.json \
  --task-type order_status \
  --task-type faq_policy

# Live Bedrock drafts + Haiku 4.5 judge (capped to 1 scenario/task by default)
python -m evals.harness --live \
  --task-type order_status \
  --task-type faq_policy
```

Local-stub scorecards mark candidate execution, judge metrics, token usage,
cost, and overall pass as incomplete — do not use them for routing or release
claims. Live runs (`--live`, ADR-016) record executed candidates, completed
judge scores, and token-derived cost estimates.

## Cost guardrails

- AWS Budget alert: **$20/month**, filtered by tag `Project=supportrouter` (ADR-008)
- Set a real alert inbox: `cdk deploy -c budget_alert_email=you@example.com` (default is a placeholder)
- CloudWatch: ≤ **3** dashboards; log retention **14 days** (7–14 allowed)
- Vector store: **S3 Vectors only** (ADR-007) — never OpenSearch Serverless

## Incident / escalation (product)

Supervisor decides pending refund approvals via the Gradio demo UI
(`python -m supportrouter.ui`) or CLI (`list-pending` / `decide`). Escalation
disposition is not part of the v0.1 slice.
