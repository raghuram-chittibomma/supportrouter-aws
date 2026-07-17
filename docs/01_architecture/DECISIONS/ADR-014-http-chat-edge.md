# ADR-014: HTTP Chat Edge over the Agent Graph

## Status

Accepted

## Context

The agent graph needs a network entry point for demos and future clients, plus a
local CLI for developer loops. The edge must stay dormancy-safe, must not widen
the runtime blast radius, and must be honest that drafting is still a local stub
(no Bedrock invocation, no measured cost).

## Decision

Expose the graph through two thin adapters over the same `run_agent` call:

1. **CLI** (`python -m supportrouter.cli`) — accepts a message and an optional
   `--session-id`, prints the JSON result.
2. **HTTP chat Lambda** (`supportrouter.api.handler`) — parses an API Gateway
   HTTP API (payload format 2.0) proxy event, validates input, runs the agent,
   and returns a proxy response.

The adapter is deterministic and side-effect-free beyond the agent call:

- `POST /chat` with body `{"message": "...", "session_id": "..."?}`.
- `400` for missing/oversized/malformed body or blank fields; `422` when the
  agent returns `status=rejected` (e.g. guardrail block); `500` for unexpected
  errors, with no internal detail leaked.
- Every response carries an `x-correlation-id` header matching the trace id.
- `message` is capped at 4000 characters as a cost/DoS guardrail.

Infrastructure (`SupportRouter-Api`) uses an **HTTP API**, not REST, for
pay-per-request pricing with no idle floor. The default stage is throttled
(rate 10 rps, burst 20) to bound request cost. The chat Lambda runs outside a
VPC on a 128–256 MB ARM64 Python runtime with a 14-day log group. Its execution
role can only write its own logs: no DynamoDB, Bedrock, or S3 permissions,
because the agent still uses local stubs.

## Consequences

- The chat edge and CLI share one code path, so behavior stays consistent.
- A compromised edge role can do nothing beyond writing its own logs.
- Throttling plus body (16 KiB) and message (4000 char) caps keep a dormant
  deployment cheap and bound abuse of the public route.
- The route is unauthenticated by design for the synthetic demo. Authentication
  (e.g. IAM or a JWT authorizer) is deferred with the runtime adapter.
- The HTTP response is a curated projection (answer, citations, confidence,
  status, ids, guardrail summary), not the full internal agent dict.
- The Lambda asset packages `src/` (excluding the gradio UI module). A live
  deploy still requires bundling runtime dependencies (`langgraph`) via a layer
  or container image; that packaging, live invocation wiring, Bedrock wiring, and
  measured latency/cost are tracked in issue #57.
- When the Bedrock runtime adapter lands, the edge gains only the specific
  model/tool permissions it then needs, preserving least privilege.
