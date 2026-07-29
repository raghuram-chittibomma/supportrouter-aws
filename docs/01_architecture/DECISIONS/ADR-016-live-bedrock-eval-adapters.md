# ADR-016: Live Bedrock Eval Adapters

## Status

Accepted

## Context

Issue #17 requires a harness that fans out ≥3 candidate models across ≥2 task
types with programmatic checks, LLM-as-judge scores, and measured cost. The
local-stub harness (#17 foundation) validated mechanics without invoking Bedrock.
Issues #24 and #25 resolved account inference profiles and selected Claude Haiku
4.5 as the judge.

## Decision

1. Keep **local-stub as the default** harness path (`python -m evals.harness`).
2. Add an explicit **`--live`** path that:
   - Maps logical IDs (`logical:nova-micro`, `logical:nova-lite`,
     `logical:claude-haiku`) to account inference profiles.
   - Runs the local agent graph for classify / tools / retrieve.
   - Drafts the customer answer via Bedrock Runtime **Converse** under the
     requested candidate model (`BedrockCandidateRunner`).
   - Judges with Claude Haiku 4.5 against `evals/rubrics/v0.1_judge.json`
     (`BedrockHaikuJudge`).
3. Cap live runs by default to **one scenario per task type** unless
   `--scenario-id` or `--max-scenarios-per-task` overrides, to control cost.
4. Estimate `cost_usd` from Converse token usage × published on-demand rates.
   Scorecards record `cost.basis` and never invent billing extracts.
5. Chat Lambda drafting remains local-stub until a separate product slice wires
   Bedrock into the runtime edge.

## Consequences

- Live scorecards can claim candidates executed, judge completed, and measured
  (token-derived) cost when incomplete_reasons is empty.
- Rubric bumps require a new `judge_version` (now `v0.1-haiku-4.5`).
- Runtime chat cost stays `not_measured` until drafting leaves the stub path.
