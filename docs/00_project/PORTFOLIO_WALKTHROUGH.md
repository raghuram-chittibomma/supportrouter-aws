# Portfolio walkthrough (≈5–10 minutes)

For **Alex** (hiring manager): how to audit SupportRouter without reading every
PR. Synthetic VoltEdge data only; cite metrics only from linked scorecards.

**Live demo (15–20 min, AWS + AI engineering talk track):** use
[`DEMO_SCRIPT_AWS_AI.md`](DEMO_SCRIPT_AWS_AI.md) instead—this file is the quiet
repo-audit path; that script is the spoken demo.

## 1. Front door (2 min)

1. Skim [`README.md`](../../README.md) — problem, AI engineering themes, measured
   table, delivery through **v0.6.0**.
2. Open
   [Releases](https://github.com/raghuram-chittibomma/supportrouter-aws/releases)
   — `v0.1.0` → `v0.5.0` → `v0.6.0` and the **not measured** callouts.
3. Glance at [`AGENTS.md`](../../AGENTS.md) — GitHub-first SDLC, synthetic-only,
   measured-metrics-only, build-time agents via Enterprise SDLC MCP (not in-repo
   `.agents/`).

## 2. Architecture (2 min)

1. [`ARCHITECTURE_AWS_DIAGRAM.md`](../01_architecture/ARCHITECTURE_AWS_DIAGRAM.md)
   — overview + AI agent loop (AWS path).
2. Optional depth: [`ARCHITECTURE.md`](../01_architecture/ARCHITECTURE.md) and
   ADRs under [`DECISIONS/`](../01_architecture/DECISIONS/) (especially **007**
   S3 Vectors, **009** confidence, **021** prompt cache, **022/023** routing,
   **024** AgentCore).

## 3. Local demo (2–3 min)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
python -m supportrouter.cli "Where is my order #VE-1001?"
python -m supportrouter.cli "What is the VoltEdge return window for unused items?"
```

Optional UI: `pip install -e ".[ui]"` then `python -m supportrouter.ui`.

Expect classify → route → tools or retrieve → draft → confidence/HITL path.
Drafting may be local stub; do not claim runtime Bedrock chat cost unless a
scorecard says so.

## 4. Proof of quality & cost discipline (2 min)

| Artifact | Why it matters |
|----------|----------------|
| [`evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json`](../../evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json) | Live golden pass + ~$0.0102 Bedrock cost |
| [`evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json`](../../evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json) | Measured cache savings (~31.8% on probe) |
| [`evals/scorecards/scorecard-v0.6-agentcore-not-measured.json`](../../evals/scorecards/scorecard-v0.6-agentcore-not-measured.json) | Explicit decline to claim AgentCore metrics |
| [`docs/03_operations/RELEASE_NOTES.md`](../03_operations/RELEASE_NOTES.md) | Release narrative bound to evidence |

Routing policy loop (offline): scorecard →
`python -m evals.generate_routing_policy` → adopt →
`python scripts/publish_routing_table.py` (RUNBOOK).

## 5. What “good SDLC” looks like here (1 min)

- Work traced to GitHub issues/milestones; PRs say `Closes #<n>`.
- Significant choices in ADRs (history superseded, not rewritten).
- CI on PRs; independent code-review expectation in `AGENTS.md`.
- Teardown / dormancy called out in RUNBOOK (ADR-008).

## Out of scope for this walkthrough

Full `cdk deploy --all`, live AgentCore invoke, or new Bedrock spend. Ops
detail: [`docs/03_operations/RUNBOOK.md`](../03_operations/RUNBOOK.md).
