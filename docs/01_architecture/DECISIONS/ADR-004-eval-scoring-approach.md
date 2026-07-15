# ADR-004: Eval Scoring Approach

## Status

Accepted

## Context

Every prompt/model/tool change should be gated by evaluations. Pure LLM-as-judge is noisy; pure string matching is brittle for generative answers.

## Decision

Combine:

1. **Programmatic metrics:** expected tool names/args shape, expected resolve/escalate/pending_approval outcome, required citation `doc_id`s when applicable, refund threshold behavior.
2. **LLM-as-judge:** rubric scoring faithfulness, helpfulness, and policy adherence against synthetic ground truth.

A scenario **passes** only if programmatic checks pass **and** judge scores meet per-task-type thresholds in `EVAL_STRATEGY.md`.

## Consequences

- Eval harness must emit both metric classes into scorecards.
- Judge model/version is part of eval traceability.
- Rubric changes require a new `judge_version` and do not rewrite old scorecards.
