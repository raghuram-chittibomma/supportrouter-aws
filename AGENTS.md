# AGENTS.md — Instructions for AI Coding Agents

Read this before making changes. Full initiation context: [`docs/00_project/AI_ORCHESTRATOR_BRIEF.md`](docs/00_project/AI_ORCHESTRATOR_BRIEF.md).

## Project in one paragraph

**SupportRouter** is an eval-driven AI customer support agent for the fictional DTC retailer **VoltEdge Electronics**. It classifies support intents, routes each task type to the lowest-viable Bedrock model, answers via RAG + Lambda tools over synthetic data, escalates or seeks human approval when needed, and proves quality/cost claims with a golden evaluation suite. It is also a demonstration of an AI-assisted, GitHub-first SDLC on AWS.

## Golden rules

1. **GitHub is the source of truth for delivery tracking.** Issues, Projects, milestones, labels, and PRs track backlog and status. Do not create local markdown that duplicates issue tracking.
2. **Synthetic data only.** Never use real customer, company, policy, transcript, or proprietary content. All VoltEdge catalog, orders, personas, FAQ/policy docs, and eval scenarios are fictional.
3. **Measured metrics only.** Never claim autonomous resolution rate, cost per conversation, caching savings, or eval pass rates unless backed by an eval scorecard artifact.
4. **Build-time SDLC agents ≠ runtime product components.** Build-time roles are served only by the **Enterprise SDLC MCP** server. Runtime components live under `src/`, `infra/`, `tools/`, and `evals/`.
5. **Prefer deterministic logic for rules; LLM reasoning for language.** Validation, routing-table lookup, refund-threshold checks, and quality gates are deterministic. Use LLMs for intent classification (when not stubbed), drafting, judging, and ambiguity.
6. **One agent modifies application code per implementation slice** unless explicitly instructed otherwise.
7. **Every change traces to a GitHub issue.** Branch `issue-<n>-slug`; PR includes `Closes #<n>`.
8. **Tests and evals are part of Done.** Behavior changes need `tests/` coverage and, where relevant, `evals/` scenarios/scorecards.
9. **Every significant technical decision gets an ADR** under `docs/01_architecture/DECISIONS/`. Never rewrite ADR history — supersede.
10. **No `.agents/` or `.skills/` folders in this repo.** Build-time agent and skill definitions live only in the enterprise-sdlc catalog.

## Enterprise SDLC MCP (build-time)

Configured in [`.cursor/mcp.json`](.cursor/mcp.json). Project manifest: [`sdlc.project.yaml`](sdlc.project.yaml).

| Need | MCP call |
|------|----------|
| List agents | `list_agents` |
| Agent role | `get_agent("<id>")` |
| List skills | `list_skills` |
| Skill checklist | `get_skill("<id>")` |
| Project manifest | `get_project_manifest` |
| Independent code review | MCP prompt `independent_code_review` |
| Architecture review | MCP prompt `architecture_review` |

### Agents this project uses

| Agent ID | When |
|----------|------|
| `product-analyst` | Requirements tightening, product brief clarity |
| `solution-architect` | Architecture, ADRs, data model; Phase 2 `architecture_review` gate |
| `implementation-planner` | Slice planning, backlog issue drafting |
| `test-eval-designer` | Tests and eval scenarios (`tests/`, `evals/` only) |
| `code-reviewer` | Pre-merge via `independent_code_review` (fresh subagent) |
| `refactor-reviewer` | Structural/architecture concerns as needed |
| `documentation-agent` | README, runbook, release notes hygiene |
| `release-manager` | Release readiness, measured metrics check |

### Skills this project uses

**Existing catalog:** `requirement-tightening`, `github-backlog-creation`, `github-issue-quality-review`, `architecture-review`, `rag-retrieval-design-review`, `langgraph-workflow-review`, `test-eval-design`, `pr-code-review`, `release-readiness-review`, `readme-runbook-documentation`.

**SupportRouter-oriented catalog skills (registered for AWS stack):** `cdk-stack-review`, `iam-least-privilege-review`, `synthetic-data-design`, `eval-scenario-design`, `llm-as-judge-rubric-design`, `bedrock-guardrails-review`, `prompt-caching-review`, `observability-dashboard-review`, `dynamodb-data-model-review`.

Low relevance here: `postgresql-schema-review`, `database-migration-review`, `fastapi-service-review` (prior triage stack).

## Where things live

- `docs/00_project/` — initiation brief, charter, product brief
- `docs/01_architecture/` — architecture, data model, ADRs
- `docs/02_testing/` — test and eval strategy
- `docs/03_operations/` — runbook, release notes
- `src/supportrouter/` — runtime agent (classifier, router, LangGraph, confidence)
- `tools/` — Lambda tool handlers
- `infra/` — AWS CDK
- `evals/` — datasets, harness, scorecards, rubrics
- `data/sample/`, `data/knowledge_base/` — synthetic fixtures
- `scripts/` — synthetic data generation, teardown
- `tests/` — pytest
- `.github/` — workflows and templates

## Before opening a PR

- Map the change to an open GitHub issue in the current milestone.
- Run `pytest` and relevant golden evals.
- Update docs/ADRs if design changed.
- Include a cost note (measured or explicitly "not measured").
- Confirm synthetic-data-only and no unmeasured README claims.

## Before merging a PR

1. Call `get_agent("code-reviewer")` and `get_skill("pr-code-review")`, or use prompt `independent_code_review`.
2. Launch a **fresh-context** Code Reviewer subagent with the PR diff.
3. Address or explicitly defer findings; only then merge.
4. For architecture changes, also run `architecture_review` with the Solution Architect / Refactor Reviewer path.
