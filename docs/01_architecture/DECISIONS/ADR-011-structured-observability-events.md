# ADR-011: Structured Observability Event Contract

## Status

Accepted

## Context

SupportRouter needs request-to-session correlation, per-step traces, and honest
token/cost fields before the runtime is deployed. Local stubs cannot provide
Bedrock usage or measured cost, and runtime and eval traffic must remain
distinguishable.

## Decision

Emit versioned structured events with these event types:

- `conversation.start`
- `agent.step`
- `conversation.end`
- `hitl.decision`

Every event includes `correlation_id`, `session_id`, `plane` (`runtime` or
`eval`), token-usage fields, `cost_usd`, and `cost_status`.

Agent-step status is local to the step:

- `ok` — node completed its work
- `skipped` — node short-circuited because an earlier validation error exists
- `error` — node raised an exception

Conversation outcome remains on conversation events and is not reused as step
status. Every `conversation.start` has a terminal `conversation.end`, including
exceptions.

Until Bedrock is invoked, token fields and `cost_usd` remain null and
`cost_status=not_measured`. Runtime code must not estimate or fabricate them.

The local default sink is in-memory for deterministic tests and demos.
`LoggingTraceSink` writes one JSON object per log line for later Lambda /
CloudWatch Logs Insights wiring. Eval harness runs set `plane=eval`; normal
CLI/UI calls default to `plane=runtime`.

## Consequences

- Local behavior can be tested without AWS or network access.
- Event consumers must honor `schema_version`.
- The in-memory sink is process-local and unbounded; the chat Lambda selects
  `LoggingTraceSink` at import when `AWS_LAMBDA_FUNCTION_NAME` is set (#71).
  Structured JSON lands in `/aws/lambda/supportrouter-chat`. Dedicated
  `/supportrouter/.../agent` and `/evals` log groups remain reserved until a
  writer is wired.
- Live metric widgets and chat error/throttle alarms ship on
  `SupportRouter-Observability` (≤3 dashboards, 14-day retention). Dollar spend
  and cache savings still come from budgets/scorecards, not dashboard widgets.
- Message content is not logged; only minimized attributes such as character
  counts, task type, model ID, and result counts are emitted.
