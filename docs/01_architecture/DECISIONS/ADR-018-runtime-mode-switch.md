# ADR-018: Local vs AWS Runtime Mode Switch

## Status

Accepted

## Context

v0.1 shipped with AWS platform pieces (KB, tools Lambdas, chat edge, HITL
tables) while the agent graph still defaulted to local stubs for drafting,
tools, and retrieval. Operators need a dormancy-safe default and an explicit
way to exercise the Bedrock path from the Gradio UI without making AWS the
only option.

## Decision

1. Introduce `runtime_mode`: `local` (default) or `aws`.
2. Selection sources (first wins for a single request):
   - Request field / Gradio radio / CLI `--runtime-mode`
   - Else `SUPPORTROUTER_RUNTIME_MODE` env (chat Lambda defaults to `local`)
3. **local:** local stub draft, `tools_local`, local KB retrieve; cost
   `not_measured` for drafting.
4. **aws:** Bedrock Converse draft using routed model → inference profile,
   Tools Lambda invokes, Bedrock KB retrieve when `SUPPORTROUTER_KB_ID` is set
   (otherwise local retrieve with an explicit note).
5. Responses always echo `runtime_mode`, `actual_model_id`, and cost honesty
   fields. Classifier/router remain deterministic in both modes for v0.1.
6. Chat Lambda IAM gains Converse/Retrieve and scoped `lambda:InvokeFunction`
   on the three tool functions, in addition to HITL DynamoDB access.

## Consequences

- Demos can stay free on Local; AWS mode is opt-in and budget-visible.
- Managed Bedrock Guardrails remain a follow-up (local deterministic policy
  still wraps both modes).
- Prompt caching and measured chat cost/conversation still require further
  scorecard work beyond draft token estimates.
