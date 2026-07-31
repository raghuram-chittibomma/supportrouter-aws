# ADR-006: Runtime Host — LangGraph on Lambda (AgentCore Later)

## Status

Accepted (v0.6 stretch path detailed in
[ADR-024](ADR-024-agentcore-runtime-host-path.md); Lambda remains default host)

## Context

Options include Bedrock Agents, LangGraph self-hosted on Lambda, or Bedrock AgentCore Runtime. The required stack specifies LangGraph for the reasoning loop, with AgentCore as a stretch milestone.

## Decision

- **Now:** run the LangGraph agent graph inside a **Lambda** behind API Gateway.
- **Not now:** Bedrock Agents managed graphs.
- **Later (milestone 6):** see [ADR-024](ADR-024-agentcore-runtime-host-path.md) —
  dual-run AgentCore Runtime wrapping the same graph contracts; Gateway MCP
  optional; no cutover of the Lambda chat edge in v0.6.

## Consequences

- Cold starts and package size must be managed (thin deps, optional container image).
- Tool interfaces stay Lambda-invokable for AgentCore/MCP compatibility.
- Eval plane remains separate (Step Functions) regardless of runtime host.
