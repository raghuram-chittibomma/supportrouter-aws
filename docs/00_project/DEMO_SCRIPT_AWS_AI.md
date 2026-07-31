# Demo script — AWS usage + AI engineering (~15–20 min)

**Audience:** hiring managers / AI platform reviewers.  
**Prop use case:** VoltEdge customer support (intentionally simple).  
**Plot:** how an enterprise-shaped AI agent ships on AWS with an eval-gated
control loop.

Companion skim path (repo audit, less talk track):
[`PORTFOLIO_WALKTHROUGH.md`](PORTFOLIO_WALKTHROUGH.md).  
Diagrams:
[`ARCHITECTURE_AWS_DIAGRAM.md`](../01_architecture/ARCHITECTURE_AWS_DIAGRAM.md).  
Ops detail: [`RUNBOOK.md`](../03_operations/RUNBOOK.md).

Synthetic data only. Cite metrics **only** from linked scorecards.

---

## Opening (30–45 sec)

**Say:**

> “The support domain is deliberately boring—order status and FAQ. What I’m
> demoing is AWS for AI applications close to enterprise constraints, plus AI
> engineering: model routing, RAG cost shape, tool IAM, guardrails/HITL, and an
> eval plane that updates production routing policy. Stretch AgentCore is
> dual-run and explicitly not measured.”

**Show:** README “What it demonstrates” + measured table (30 sec).

**Do not claim:** Autonomous resolution rate, runtime chat Bedrock cost, or
AgentCore quality/cost.

---

## Act 1 — Enterprise AWS runtime (~6–7 min)

**Goal:** One user turn maps to a recognizable AWS topology—not a notebook
agent.

### 1.1 System map (2 min)

**Show:**
[`ARCHITECTURE_AWS_DIAGRAM.md`](../01_architecture/ARCHITECTURE_AWS_DIAGRAM.md)
§1 (overview) and §2 (agent loop).

| Beat | Say | Point at |
|------|-----|----------|
| Edge | “Familiar HTTP entry—API Gateway → Chat Lambda.” | APIGW → Chat |
| Orchestration | “LangGraph on Lambda: deterministic graph around LLM calls.” | Chat Lambda |
| Models | “Task type → DynamoDB RoutingTable → Bedrock Converse—not a hard-coded model.” | RoutingTable |
| RAG | “Bedrock Knowledge Bases over **S3 Vectors**. OpenSearch Serverless deliberately out (idle OCU floor).” | KB / S3 Vectors · [ADR-007](../01_architecture/DECISIONS/ADR-007-s3-vectors-over-opensearch.md) |
| Tools | “Three tool Lambdas, separate roles, resource-scoped DynamoDB.” | order / return / refund · [ADR-013](../01_architecture/DECISIONS/ADR-013-lambda-tool-isolation.md) |
| Safety | “Bedrock Guardrails in/out; deterministic confidence; refunds over $100 → Approvals.” | Guardrails + HITL |
| Stretch | “Opt-in AgentCore Runtime + Gateway MCP; Api Lambda remains default edge.” | AgentCore dashed boxes · [ADR-024](../01_architecture/DECISIONS/ADR-024-agentcore-runtime-host-path.md) |

### 1.2 Live path (3–4 min) — pick one

**Prefer A if stacks are up; otherwise B. Do not apologize for B—call it the
portable demo.**

#### Option A — Deployed AWS chat (preferred when live)

```powershell
# CHAT_API_ENDPOINT from Api stack output (see RUNBOOK)
curl -sS -X POST "$CHAT_API_ENDPOINT/chat" `
  -H "Content-Type: application/json" `
  -d '{"message":"Where is my order #VE-1001?"}'
```

**Say while waiting / after response:**

> “Same graph as local: validate → guardrail → classify → route → tool or
> retrieve → draft → confidence/HITL → session write.”

**Optional 60-sec console tour (in order):**

1. API Gateway → `/chat` method  
2. CloudWatch log group for Chat Lambda (one request id)  
3. DynamoDB `RoutingTable` (GetItem story)  
4. Tool Lambda log or Orders table (if tool path)  
5. Budgets / cost tag callout ($20/mo alert)—not a live billing deep-dive  

**Do not claim:** Per-request Bedrock $ for this chat unless a scorecard covers
that exact run.

#### Option B — Local CLI mapped to AWS (default portable)

```powershell
python -m supportrouter.cli "Where is my order #VE-1001?"
python -m supportrouter.cli "What is the VoltEdge return window for unused items?"
```

**Say:**

> “Local stubs keep spend at zero. Each node is the same contract as the AWS
> path—tools, retrieve, route, guardrails—wired to Bedrock/Lambdas when
> `runtime_mode=aws`.”

Gradio UI (`python -m supportrouter.ui`) is **optional garnish**, not the hero.

---

## Act 2 — AI engineering control loop (~6–7 min)

**Goal:** Show the dual plane: runtime serves customers; eval plane governs
models and cost claims.

### 2.1 Eval plane ≠ runtime (2 min)

**Show:** diagram §3 (eval → routing table).

**Say:**

> “Golden scenarios → live Bedrock candidates → LLM-as-judge → versioned
> scorecard. EventBridge re-eval schedule defaults **off**—manual harness for
> dormancy-safe cost.”

**Show files (open, don’t narrate every field):**

| Artifact | Why |
|----------|-----|
| [`evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json`](../../evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json) | Live golden pass + ~$0.0102 Bedrock cost |
| [`evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json`](../../evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json) | Cache vs uncached-equivalent (~31.8% lower on probe) |
| [`evals/scorecards/scorecard-v0.6-agentcore-not-measured.json`](../../evals/scorecards/scorecard-v0.6-agentcore-not-measured.json) | Integrity: stretch path refused as measured |

### 2.2 Closed loop: scorecard → production routing (2–3 min)

**Say:**

> “Enterprises don’t hard-code ‘use Sonnet for everything.’ We generate a
> routing policy from scorecards, adopt it, publish to DynamoDB; chat only
> GetItems.”

**Show / narrate (run only if you intend spend + table write):**

```powershell
# Offline / dry narrative is fine; live publish needs AWS creds + table
python -m evals.generate_routing_policy
# adopt path per RUNBOOK, then:
python scripts/publish_routing_table.py
```

**Point at ADRs:** [022](../01_architecture/DECISIONS/ADR-022-offline-routing-policy-generation.md) /
[023](../01_architecture/DECISIONS/ADR-023-dynamodb-routing-table.md).

### 2.3 Cost & token discipline (1–2 min)

**Say:**

> “One user-visible turn can be 5–10× tokens versus a single completion—
> classify, retrieve/tools, draft, and offline judge fan-out. Prompt caching is
> measured on the judge probe, not waved as a slogan. Runtime drafting cost
> stays not measured when the chat path uses a local stub.”

**Show:** measured table in README + prompt-cache scorecard `cost` fields.

---

## Act 3 — Ops & delivery maturity (~3–4 min)

**Goal:** Same constraints enterprises hit after the prototype works.

| Beat | Show | Say |
|------|------|-----|
| Decisions as ADRs | [`DECISIONS/`](../01_architecture/DECISIONS/) | “Supersede, don’t rewrite history.” |
| Dormancy | [ADR-008](../01_architecture/DECISIONS/ADR-008-dormancy-safe-cost-profile.md) + RUNBOOK teardown | “No AOSS, no standing eval schedule by default, destroy when idle.” |
| Delivery evidence | [Releases](https://github.com/raghuram-chittibomma/supportrouter-aws/releases) v0.1 → v0.6 | “Sequenced milestones; AgentCore is stretch dual-run.” |
| Build-time vs runtime | [`AGENTS.md`](../../AGENTS.md) | “SDLC agents via Enterprise MCP catalog—not in-repo `.agents/` folders.” |

**Do not claim:** Monthly AWS bill figures beyond architecture estimates unless
you open Billing console evidence in-session.

---

## Close (30 sec)

**Say:**

> “I didn’t optimize for an impressive support bot. I optimized for transferable
> platform work: AWS AI services under least privilege and cost caps, plus an
> eval-gated routing loop with honest not-measured boundaries.”

**Leave-behind links:**

1. This script  
2. [`ARCHITECTURE_AWS_DIAGRAM.md`](../01_architecture/ARCHITECTURE_AWS_DIAGRAM.md)  
3. Measured scorecards (table above)  
4. [v0.6.0 release](https://github.com/raghuram-chittibomma/supportrouter-aws/releases/tag/v0.6.0)

---

## Timing cheat sheet

| Block | Minutes | Hero artifact |
|-------|---------|----------------|
| Opening | 0.5 | README measured table |
| Act 1 AWS runtime | 6–7 | Architecture diagrams + one invoke |
| Act 2 AI engineering | 6–7 | Scorecards + routing publish story |
| Act 3 Ops / SDLC | 3–4 | ADRs + releases |
| Close | 0.5 | One-liner |

**If cut to 10 minutes:** Opening → Act 1 diagram only + one CLI → Act 2
scorecards + routing loop narrative → Close. Skip consoles and AgentCore.

**If extended to 25 minutes:** Add AgentCore opt-in story from diagram §4 and
RUNBOOK flags (`enable_agentcore`, `enable_agentcore_gateway`)—still **not
measured**.

---

## Explicit do-not-claim list

| Topic | Status |
|-------|--------|
| Live Bedrock golden overall pass + ~$0.0102 | OK — v0.1 live scorecard |
| Prompt-cache ~31.8% on judge probe | OK — v0.1 cache scorecard |
| Runtime chat Bedrock $/conversation | **not measured** (stub default) |
| AgentCore quality / session cost | **not measured** — v0.6 scorecard |
| Autonomous resolution % in production | **not measured** |
| OpenSearch / always-on eval schedule | **out of design** on purpose |

---

## Prep checklist (day of)

- [ ] Browser tabs: README, this script, `ARCHITECTURE_AWS_DIAGRAM.md`, 3 scorecards, Releases  
- [ ] Local: venv + `pip install -e ".[dev]"`; `pytest -q` green optional  
- [ ] If Option A: `CHAT_API_ENDPOINT` set; one warm request already succeeded  
- [ ] If publish demo: confirm table name / creds; prefer narrative if unsure  
- [ ] Gradio closed unless someone asks for UX  
- [ ] Mentally rehearse opening one-liner (prop vs plot)
