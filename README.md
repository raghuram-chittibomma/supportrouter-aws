# SupportRouter

Eval-driven AI customer support agent for **VoltEdge Electronics** (fictional DTC consumer electronics retailer), built on AWS Bedrock + LangGraph with a GitHub-first SDLC.

> **Measured metrics only.** Cite autonomous resolution rate, cost per conversation, caching savings, and eval pass rates only from scorecard or release-note evidence.
>
> Live v0.1 golden eval (3 models × `order_status` + `faq_policy`, capped): **overall_pass=true**, Bedrock cost **~$0.0102** (tokens × published rates). Evidence: [`evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json`](evals/scorecards/scorecard-v0.1-live-bedrock-2026-07-29.json). Judge prompt-cache hit/miss (Haiku 4.5): measured cost **~$0.00713** vs uncached-equivalent **~$0.01045** (~31.8% lower) on a 2-call write+read probe — [`evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json`](evals/scorecards/scorecard-v0.1-prompt-cache-2026-07-30.json). Runtime chat drafting cost remains **not measured** (local stub). See [`docs/03_operations/RELEASE_NOTES.md`](docs/03_operations/RELEASE_NOTES.md).

## Quick start (local LangGraph agent)

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
pytest
python -m supportrouter.cli "Where is my order #VE-1001?"
# → order_status, seeded model, local tool lookup, status resolved
```

### Thin demo UI (Gradio)

```bash
pip install -e ".[ui]"   # or .[dev] which includes Gradio
python -m supportrouter.ui
# open http://127.0.0.1:7860
# Tabs: Customer chat | Supervisor (HITL)
```

Local-only process — **no always-on AWS UI hosting**. Cost note: not measured.

Runtime path (local stubs for drafting; optional DynamoDB HITL persistence when table env vars are set): validate → classify → route → retrieve|tools → draft → confidence → HITL.


## Docs

- [`docs/00_project/AI_ORCHESTRATOR_BRIEF.md`](docs/00_project/AI_ORCHESTRATOR_BRIEF.md) — initiation brief
- [`AGENTS.md`](AGENTS.md) — AI agent operating rules + enterprise-sdlc pointers
- [`docs/01_architecture/ARCHITECTURE.md`](docs/01_architecture/ARCHITECTURE.md) — runtime architecture

## Stack (v0.1)

AWS Bedrock · LangGraph (Python) · Bedrock Knowledge Bases · Lambda tools · DynamoDB · Step Functions (eval plane) · API Gateway · CloudWatch · CDK (Python)

## License

MIT (portfolio / demo)
