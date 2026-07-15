# SupportRouter — AI Orchestrator Brief

Durable handoff brief for AI-assisted delivery. Intent lives here and in GitHub — not only in chat history.

## Project name

**SupportRouter**

## Fictional business context

**VoltEdge Electronics** is a fully fictional direct-to-consumer consumer-electronics retailer. Product line examples: PulseBuds Pro (earbuds), BoomBar 300 (speaker), HomeLink Hub (smart-home), SwiftRoute AX2 (Wi-Fi router), ClearCam 4K (webcam), TypeCraft 87 (keyboard), PowerDock Duo (USB-C dock). Support scenarios include order status, shipping changes, damaged/missing shipments, returns/refunds, warranty, compatibility, setup/troubleshooting, promotions/payments, and account/policy questions.

## Purpose

1. Build a working **eval-driven agentic AI application on AWS** the way a real organization would.
2. Demonstrate that the **full SDLC** can be driven with AI agents, GitHub Issues/Projects, repo documentation, ADRs, PRs, tests, evaluations, and release tracking.

## Business goal

Reduce support cost and response time for VoltEdge by resolving routine tickets autonomously at the **lowest viable model cost**, while keeping humans in the loop for consequential or low-confidence actions — and **prove it with evaluation data**.

## Target users

| Role | Primary need |
|------|----------------|
| Customer (Maya) | Fast, accurate answers with citations |
| Support supervisor (Jordan) | Approve refunds above threshold; handle escalations |
| Platform engineer (Priya) | Operate evals, routing policy, dashboards |
| Hiring manager (Alex) | Audit portfolio repo for disciplined SDLC + measured claims |

## v0.1 scope

Complete but small end-to-end slice:

- User submits a support message (CLI and/or simple chat endpoint).
- System classifies task type (FAQ/policy, order status, return, refund, product question).
- Router selects model from routing table (seeded initially; later produced by eval pipeline).
- Agent retrieves synthetic policy/FAQ via Knowledge Bases when useful.
- Agent calls Lambda tools against synthetic order data when needed.
- Refunds above **$100** produce an approval request instead of direct execution.
- Guardrails filter I/O; low confidence triggers escalation.
- Response includes cited sources, confidence, and resolved/escalated status.
- Initial eval harness scores ≥3 candidate models on ≥2 task types and writes a scorecard.
- Tests, golden scenarios, cost notes, and release notes included.

**Out of v0.1:** Bedrock AgentCore Runtime, Lambda-via-MCP, full auto routing-policy generator, rich supervisor UI, multi-language, real payments, multi-account prod hardening.

## GitHub-first SDLC rule

GitHub owns backlog, issues, AC, milestones, Project board, labels, PRs, and releases. Local docs exist only when GitHub has no suitable place, the artifact must version with code, or it is a durable engineering document.

## Source-of-truth rules

| Concern | Truth |
|---------|--------|
| Requirements / AC | GitHub Issues |
| Architecture / ADRs | `docs/01_architecture/` |
| Backlog / status | GitHub Issues + Project |
| Evals / tests | `evals/`, `tests/`, scorecards |
| Releases | GitHub Releases (+ mirrored measured notes) |
| Initiation intent | This brief |
| Build-time agents/skills | `enterprise_sdlc_mcp` catalog |

## Build-time vs runtime

- **Build-time SDLC agents** (Product Analyst, Solution Architect, etc.) are reusable assistant roles for delivery. Served by enterprise-sdlc MCP. **Not** part of the application runtime. Definitions never live in `.agents/` or `.skills/` in this repo.
- **Runtime product components** (classifier, model router, LangGraph agent, RAG, Lambda tools, guardrails, confidence, HITL, eval plane, prompt cache, observability) live under `src/`, `infra/`, `tools/`, `evals/`.

## Required AWS stack

Bedrock (Claude Haiku/Sonnet + Nova family as routing candidates) · LangGraph (Python) · Bedrock Knowledge Bases over S3 · Lambda tools · DynamoDB · Step Functions · EventBridge · Bedrock Guardrails · Bedrock prompt caching · API Gateway + Lambda · CloudWatch · CDK (all resources) · pytest + GitHub Actions. Stretch (later): AgentCore Runtime + MCP tool exposure.

## Synthetic-data-only rule

All company data is synthetic: catalog, personas, orders, conversations, FAQ/policy, warranty/shipping rules, golden evals, templates. No real policies, customers, transcripts, manuals, or proprietary content.

## Measured-metrics-only rule

Every metric claim in README/release notes must be backed by eval pipeline artifacts. Never claim a metric that was not measured.

## Constraints

- Practical for a single-person portfolio/demo; domain logic stays trivial (three tools, one policy corpus); sophistication is in agentic machinery.
- Keep AWS costs low; teardown scripts; cost-estimate note every milestone.
- Least-privilege IAM per Lambda tool.
- ADR for every significant technical decision; supersede, never rewrite history.
- Assumptions explicit; open questions tracked as GitHub issues.

## Expected artifacts and workflow

Issue (DoR) → branch `issue-<n>-slug` → PR (`Closes #<n>`) → CI (pytest + golden evals) → `independent_code_review` → merge → milestone → GitHub Release with measured notes.

Durable docs: brief, charter, product brief, architecture, data model, ADRs, eval/test strategy, runbook, release notes, thin `AGENTS.md` + `sdlc.project.yaml`.

## Assumptions

- English only for v0.1.
- Single AWS account; region `us-east-1`.
- Refund HITL threshold = $100 USD.
- Routing table seeded until milestone 2 policy generator.
- CLI acceptable for supervisor approve in v0.1.
- Public GitHub repo under `raghuram-chittibomma/supportrouter-aws`.

## Open questions

Tracked as GitHub issues labeled `flag:open-question` (exact Bedrock model IDs in account, judge model, confidence weights, KB chunking, supervisor UX, prompt-cache regional support).

## How AI agents and MCP tools are used

- **Main Orchestrator** (this Cursor session) coordinates delivery; one code-modifier per slice.
- **Enterprise SDLC MCP** supplies `list_agents` / `get_agent` / `list_skills` / `get_skill` / `get_project_manifest` and review prompts `architecture_review` / `independent_code_review`.
- GitHub CLI / GitHub MCP for issues and Projects; AWS docs MCP (when configured) for API accuracy; never invent Bedrock/CDK behavior.
- New build-time agents/skills are proposed for approval then registered in the enterprise-sdlc catalog — never as standalone repo markdown under `.agents/` or `.skills/`.
