# SupportRouter

Eval-driven AI customer support agent for **VoltEdge Electronics** (fictional DTC consumer electronics retailer), built on AWS Bedrock + LangGraph with a GitHub-first SDLC.

> **Measured metrics only.** The README will cite autonomous resolution rate, cost per conversation, caching savings, and eval pass rates only after scorecard artifacts exist. Until then: **not measured**.

## Quick start (local first slice)

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
pytest
python -m supportrouter.cli "Where is my order #VE-1001?"
```

## Docs

- [`docs/00_project/AI_ORCHESTRATOR_BRIEF.md`](docs/00_project/AI_ORCHESTRATOR_BRIEF.md) — initiation brief
- [`AGENTS.md`](AGENTS.md) — AI agent operating rules + enterprise-sdlc pointers
- [`docs/01_architecture/ARCHITECTURE.md`](docs/01_architecture/ARCHITECTURE.md) — runtime architecture

## Stack (v0.1)

AWS Bedrock · LangGraph (Python) · Bedrock Knowledge Bases · Lambda tools · DynamoDB · Step Functions (eval plane) · API Gateway · CloudWatch · CDK (Python)

## License

MIT (portfolio / demo)
