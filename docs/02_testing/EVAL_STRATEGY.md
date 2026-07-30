# Eval Strategy

## Goals

Gate prompt, model, and tool changes with a golden suite. Produce versioned scorecards that can later drive the routing table (ADR-003, ADR-004).

## v0.1 minimum

- ≥3 candidate models
- ≥2 task types (e.g. `order_status`, `faq_policy`)
- Programmatic checks + LLM-as-judge
- Scorecard written under `evals/scorecards/` (and later DynamoDB)

## Local-first harness

Default (no Bedrock spend):

```bash
python -m evals.harness \
  --task-type order_status \
  --task-type faq_policy
```

The default local run fans out three **logical** candidate IDs to validate
harness mechanics. It executes the same deterministic local agent for each
candidate and records:

- `execution_mode=local_stub`
- `candidate_executed=false`
- judge status `not_run`
- token usage and cost as `null` / `not_measured`
- overall pass as `null`

## Live Bedrock harness (ADR-016)

After #24/#25 model and judge choices:

```bash
python -m evals.harness --live \
  --task-type order_status \
  --task-type faq_policy
```

`--live` invokes Bedrock Converse for each candidate draft and Claude Haiku 4.5
as judge. By default it caps to **one scenario per task type** (override with
`--max-scenarios-per-task` or `--scenario-id`). Cost is estimated from token
usage × published on-demand rates and stored on the scorecard.

## Guardrail adversarial set

`evals/datasets/v0.1_guardrails.json` versions synthetic input/output cases for
PII, dangerous and self-harm assistance, financial advice, and support-domain
negative controls. `evals.guardrail_harness.run_guardrail_harness` produces the
local deterministic gate and explicitly records
`managed_guardrail_executed=false`. Managed Bedrock Guardrail assessments must
run against the same cases when the live runtime adapter is enabled.

## Judge rubric

The active rubric is versioned at `evals/rubrics/v0.1_judge.json`
(`judge_version=v0.1-haiku-4.5`, Claude Haiku 4.5). It scores faithfulness,
helpfulness, and policy adherence on a 1–5 scale. Minimum scores are 4 for all
v0.1 task types except `refund_request`, which requires 5. Programmatic checks
remain mandatory; judge scores cannot rescue a programmatic failure.

## Traceability

`scorecard_id` → `dataset_version` + `prompt_version` + `model_ids` + `judge_version` → informs `routing_table_version`.

## Anti-leakage

Golden eval inputs must never be injected into production prompts or few-shot examples.

## Token amplification

One agent query can trigger **multiple** Bedrock invocations (routing candidates, drafting, LLM-as-judge, multi-model fan-out). Expect roughly **5–10×** tokens relative to a single visible completion. Scorecards must attribute tokens/cost **per model call**, not only per user message.

## Prompt caching and effective pricing

ADR-005 / ADR-021 cache checkpoints:

1. Agent static system prompt + tool schema prefix (+ deterministic padding)
2. Conversation history segments (when supported; deferred)
3. Eval judge rubric prefix (+ deterministic padding)

AWS Converse paths send `cachePoint` and record cache read/write tokens.
Local stubs remain **`cache_enabled=false`**. Cite caching savings in README /
release notes only from a measured scorecard artifact (see
`scripts/measure_prompt_cache.py`).

## Schedule default-off (dormancy)

EventBridge re-evaluation is **disabled by default** (`enable_reeval_schedule=false`). When false, CDK creates **no** schedule rule. Run evals on-demand via the harness CLI or a manual Step Functions start. See ADR-008 and the runbook.

## Measured metrics only

README/release notes may cite eval pass rates, cost, latency, or caching savings only when present in a scorecard artifact.
