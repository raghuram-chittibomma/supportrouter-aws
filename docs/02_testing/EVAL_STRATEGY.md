# Eval Strategy

## Goals

Gate prompt, model, and tool changes with a golden suite. Produce versioned scorecards that can later drive the routing table (ADR-003, ADR-004).

## v0.1 minimum

- ≥3 candidate models
- ≥2 task types (e.g. `order_status`, `faq_policy`)
- Programmatic checks + LLM-as-judge
- Scorecard written under `evals/scorecards/` (and later DynamoDB)

## Traceability

`scorecard_id` → `dataset_version` + `prompt_version` + `model_ids` + `judge_version` → informs `routing_table_version`.

## Anti-leakage

Golden eval inputs must never be injected into production prompts or few-shot examples.

## Measured metrics only

README/release notes may cite eval pass rates, cost, latency, or caching savings only when present in a scorecard artifact.
