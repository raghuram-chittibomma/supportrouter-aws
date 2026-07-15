# ADR-006: Runtime Host — LangGraph on Lambda (AgentCore Later)

## Status

Accepted

## Context

Options include Bedrock Agents, LangGraph self-hosted on Lambda, or Bedrock AgentCore Runtime. The required stack specifies LangGraph for the reasoning loop, with AgentCore as a stretch milestone.

## Decision

- **Now:** run the LangGraph agent graph inside a **Lambda** behind API Gateway.
- **Not now:** Bedrock Agents managed graphs.
- **Later (milestone 6):** migrate the same graph/tool/KB contracts to **Bedrock AgentCore Runtime** and optionally expose Lambda tools via MCP.

## Consequences

- Cold starts and package size must be managed (thin deps, optional container image).
- Tool interfaces stay Lambda-invokable for AgentCore/MCP compatibility.
- Eval plane remains separate (Step Functions) regardless of runtime host.
