# Runbook

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
python -m supportrouter.cli "Where is my order #VE-1001?"
```

## AWS deploy (when infra slice lands)

```bash
cd infra
cdk deploy --all
# teardown
../scripts/teardown.sh
```

Cost note: always record estimated/measured spend for the milestone. Prefer tiny models and tear down demos when idle.

## Eval harness (later slices)

```bash
python -m evals.harness --dataset evals/datasets/v0.1.jsonl
```

## Incident / escalation (product)

Supervisor reviews `pending_approval` / `escalated` sessions (CLI in v0.1).
