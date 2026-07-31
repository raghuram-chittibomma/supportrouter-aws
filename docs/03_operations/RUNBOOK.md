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
  until Bedrock usage is present

Default sink is process-local memory for tests/CLI/UI. Inside the chat Lambda,
`LoggingTraceSink` is activated automatically so one JSON object per line lands
in `/aws/lambda/supportrouter-chat` (Logs Insights).

### CloudWatch Observability stack (#71 / ADR-008 / ADR-011)

Deploy (us-east-1; activate `.venv` first so CDK's `python app.py` resolves `aws_cdk`):

```powershell
.\.venv\Scripts\Activate.ps1
cd infra
npx cdk deploy SupportRouter-Observability
```

Redeploy the chat Lambda after observability code changes so `LoggingTraceSink` is active:

```powershell
npx cdk deploy SupportRouter-Api
```

Open dashboards (console → CloudWatch → Dashboards):

| Dashboard | Purpose |
|-----------|---------|
| `supportrouter-runtime` | Chat + tool Lambda invocations, errors, duration, throttles |
| `supportrouter-cost-signals` | Bedrock invocation counts / latency / errors (not dollar spend) |
| `supportrouter-evals` | Eval-plane notes; schedule stays OFF by default |

Log groups:

| Log group | Writers today |
|-----------|----------------|
| `/aws/lambda/supportrouter-chat` | Chat Lambda structured traces (`LoggingTraceSink`) |
| `/supportrouter/supportrouter/agent` | Reserved — no writer yet |
| `/supportrouter/supportrouter/evals` | Reserved — harness/CLI does not ship here yet |

Alarms (no SNS actions): `supportrouter-chat-errors`, `supportrouter-chat-throttles`.

Tear down Observability only:

```powershell
cd infra
npx cdk destroy SupportRouter-Observability
```

Full dormancy teardown (all stacks): `.\scripts\teardown.ps1` — confirm no
never-expire log groups remain afterward.

**Cost note:** Three dashboards + 14-day log retention are dormancy-safe idle
cost; spend scales with log ingestion and Lambda/Bedrock traffic. No Bedrock
calls from this stack alone. Monthly budget alert remains on
`SupportRouter-CostGuardrails` ($20, tag `Project=supportrouter`).

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

### Prompt caching (ADR-021)

Versioned cacheable prefixes with Converse `cachePoint`:

- agent static system + tool schemas + padding (`agent-prefix-v0.3`)
- eval judge system + rubric + padding (`v0.1-haiku-4.5`)

AWS draft and live eval paths set `prompt_cache=True`. Local stubs stay
`cache_enabled=false` / `cache_status=not_configured`. Scorecards aggregate
`cache_read_tokens` / `cache_write_tokens` and optional `cache_comparison`
(measured vs uncached-equivalent). Measure judge hit/miss with:

```powershell
python scripts/measure_prompt_cache.py
```

Cite README/release caching savings only from a scorecard under `evals/scorecards/`.

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
- [ ] No `SupportRouter-EvalSchedule` stack (or confirm `ReevalScheduleEnabled=false` and no `supportrouter-reeval-schedule` EventBridge rule)
- [ ] EventBridge: no SupportRouter re-eval rules left behind
- [ ] No SupportRouter log groups with **never-expire** retention
- [ ] No SupportRouter VPC or NAT Gateways (we must not create any)

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

## Eval schedule (`SupportRouter-EvalSchedule`) — default OFF

**Intent:** keep the stack/scaffolding deployed if you want, but **do not** run
automatic Bedrock re-evals until you choose to. Weekly EventBridge is opt-in
only (ADR-008).

| Mode | How | Bedrock spend |
|------|-----|---------------|
| **Manual (preferred)** | `python -m evals.harness` / `--live` when you want a run | Only that run |
| **Schedule OFF (default)** | Deploy without enabling the flag — **no** EventBridge rule | None from schedule |
| **Schedule ON (explicit)** | Redeploy with `-c enable_reeval_schedule=true` | Weekly stub/target until disabled |

Deploy scaffolding with schedule disabled (us-east-1; activate `.venv` first):

```powershell
.\.venv\Scripts\Activate.ps1
cd infra
npx cdk deploy SupportRouter-EvalSchedule
# ReevalScheduleEnabled output must be "false"; no rule named supportrouter-reeval-schedule
```

Enable a standing weekly rule **only when you want it** (cost risk: each fire
can invoke Bedrock candidates + judge once the stub is wired to the live
harness — measure before claiming savings or quality):

```powershell
cd infra
npx cdk deploy SupportRouter-EvalSchedule -c enable_reeval_schedule=true
```

Turn the schedule back off (removes the EventBridge rule; does not invent a
disabled rule):

```powershell
npx cdk deploy SupportRouter-EvalSchedule -c enable_reeval_schedule=false
```

Optional one-shot of the **placeholder** Step Functions machine (no Bedrock
today — Pass stub only):

```powershell
$arn = aws cloudformation describe-stacks `
  --stack-name SupportRouter-EvalSchedule `
  --query "Stacks[0].Outputs[?OutputKey=='EvalStateMachineArn'].OutputValue" `
  --output text
aws stepfunctions start-execution --state-machine-arn $arn
```

On-demand eval (real scorecards; preferred while dormant):

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

## Routing policy from scorecards (ADR-003 / ADR-022)

Offline transform (no Bedrock). Prefer a measured live scorecard:

```powershell
python -m evals.generate_routing_policy `
  --scorecard evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json `
  --seed data/sample/routing_table.json `
  --out routing_table.generated.json
```

- Refuses incomplete/local-stub scorecards unless `--allow-incomplete`.
- Regenerates routes only for task types present in the scorecard; `--seed`
  copies through missing task types (e.g. `unknown`).
- Does **not** overwrite `data/sample/routing_table.json` unless `--out` points
  there. Inspect the generated file before adopting.
- Optional knobs: `--quality-tolerance 0.05`, `--p95-latency-cap-ms 12000`.

**Cost note:** generation is an offline JSON transform (not measured). Cite
routing quality/cost/latency only from the source scorecard + generated
artifact.

## Cost guardrails

- AWS Budget alert: **$20/month**, filtered by tag `Project=supportrouter` (ADR-008)
- Set a real alert inbox: `cdk deploy -c budget_alert_email=you@example.com` (default is a placeholder)
- CloudWatch: ≤ **3** dashboards; log retention **14 days** (7–14 allowed)
- Vector store: **S3 Vectors only** (ADR-007) — never OpenSearch Serverless

## Incident / escalation (product)

Supervisor decides pending refund approvals via the Gradio demo UI
(`python -m supportrouter.ui`) or CLI (`list-pending` / `decide`). Escalation
disposition is not part of the v0.1 slice.
