# Eval Strategy

## Goals

Gate prompt, model, and tool changes with a golden suite. Produce versioned scorecards that can later drive the routing table (ADR-003, ADR-004).

## v0.1 minimum

- ≥3 candidate models
- ≥2 task types (e.g. `order_status`, `faq_policy`)
- Programmatic checks + LLM-as-judge
- Scorecard written under `evals/scorecards/` (and later DynamoDB)

## Local-first harness

Run the harness locally while Bedrock model and judge choices remain open:

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

These artifacts are diagnostic only. They do not satisfy the live-model,
LLM-as-judge, or measured-cost acceptance criteria in issue #17. Resolve model
IDs in #24 and judge choice in #25 before producing a release scorecard.

## Judge rubric

The draft rubric is versioned at `evals/rubrics/v0.1_judge.json`. It scores
faithfulness, helpfulness, and policy adherence on a 1–5 scale. Minimum scores
are 4 for all v0.1 task types except `refund_request`, which requires 5.
Programmatic checks remain mandatory; judge scores cannot rescue a
programmatic failure.

## Traceability

`scorecard_id` → `dataset_version` + `prompt_version` + `model_ids` + `judge_version` → informs `routing_table_version`.

## Anti-leakage

Golden eval inputs must never be injected into production prompts or few-shot examples.

## Token amplification

One agent query can trigger **multiple** Bedrock invocations (routing candidates, drafting, LLM-as-judge, multi-model fan-out). Expect roughly **5–10×** tokens relative to a single visible completion. Scorecards must attribute tokens/cost **per model call**, not only per user message.

## Prompt caching and effective pricing

ADR-005 cache checkpoints:

1. Agent static system prompt + tool schema prefix
2. Conversation history segments (when supported)
3. Eval judge rubric prefix

Until scorecards record cache hits, planning and README claims assume **`cache_enabled=false`**. Eval cost scoring may use **effective (cached) pricing** only when the harness measures and stores cache hit data.

## Schedule default-off (dormancy)

EventBridge re-evaluation is **disabled by default** (`enable_reeval_schedule=false`). When false, CDK creates **no** schedule rule. Run evals on-demand via the harness CLI or a manual Step Functions start. See ADR-008 and the runbook.

## Measured metrics only

README/release notes may cite eval pass rates, cost, latency, or caching savings only when present in a scorecard artifact.
