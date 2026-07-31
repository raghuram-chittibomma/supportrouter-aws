# ADR-024: AgentCore Runtime Host Path (v0.6 Stretch)

## Status

Accepted (extends ADR-006 “later” clause for milestone v0.6; does **not**
replace LangGraph-on-Lambda as the default host)

## Context

ADR-006 chose LangGraph on Lambda behind API Gateway, with AgentCore Runtime
as a later stretch. Milestone **v0.6** (#91) asks Priya to run SupportRouter on
AgentCore **without rewriting** tool/KB/router contracts.

AWS AgentCore splits concerns:

| Capability | Role for SupportRouter |
|------------|------------------------|
| **AgentCore Runtime** | Host the agent container (framework-agnostic; LangGraph supported via `BedrockAgentCoreApp` + `@entrypoint`) |
| **AgentCore Gateway** | Optional MCP façade over existing Lambda tools |
| **AgentCore Identity** | Inbound/outbound auth; optional for portfolio SigV4 demos |

Runtime service contract (HTTP): container listens on port **8080**,
`POST /invocations` (plus health). MCP servers use port **8000** `/mcp` — that
path is for tool/MCP *servers*, not our primary graph host.

Region **us-east-1** is in the AgentCore Runtime regional set. CDK L2 exists as
`aws_cdk.aws_bedrockagentcore` (`Runtime`, artifacts from ECR / code deploy).

## Decision

### 1. Dual-run (keep Lambda edge)

- **Keep** `SupportRouter-Api` (API Gateway → chat Lambda → `run_agent`) as the
  default demo and dormancy path.
- **Add** an opt-in AgentCore Runtime deployment that wraps the **same**
  `run_agent` / graph contracts behind `BedrockAgentCoreApp`.
- **Do not** cut over or delete the Lambda chat path in v0.6.

### 2. Runtime packaging

- Package an **ARM64** container (AgentCore requirement) with the SupportRouter
  runtime deps + a thin entrypoint that:
  - Maps Runtime payload → existing chat/agent request shape
  - Calls `run_agent(...)`
  - Returns JSON compatible with the HTTP contract
- Push image to **ECR**; register with AgentCore Runtime (CDK preferred over
  one-off starter-toolkit launches for teardown parity with ADR-008).

### 3. Tools: Lambda invoke first; Gateway MCP optional

- **v0.6 MVP:** AgentCore-hosted graph keeps today’s tool path (invoke the
  three tool Lambdas / env-wired adapters). Contracts stay Lambda-shaped
  (ADR-013).
- **Optional follow-on (#93):** AgentCore Gateway exposes the same Lambdas as
  MCP tools. Not required to claim “AgentCore host” for #91; required only to
  claim “Lambda-via-MCP.”

### 4. Auth (demo)

- Default inbound auth for the stretch path: **SigV4**
  (`InvokeAgentRuntime`) for operators/demos.
- Cognito / OAuth Identity IdP wiring is **out of v0.6** unless a later issue
  needs end-user auth.

### 5. Eval plane unchanged

- Offline harness, scorecards, routing publish remain separate (ADR-016/022/023).
- AgentCore quality/cost claims need #95 evidence or explicit **not measured**
  ([`scorecard-v0.6-agentcore-not-measured`](../../../evals/scorecards/scorecard-v0.6-agentcore-not-measured.json)).

## Keep / drop vs current Api path

| Keep | Add (opt-in) | Drop / defer |
|------|--------------|--------------|
| Api Gateway + chat Lambda | AgentCore Runtime + ECR image | Sole cutover to AgentCore |
| Tools Lambdas + DynamoDB tables | Thin `BedrockAgentCoreApp` adapter | Rewriting tool handlers |
| KB / Guardrails / RoutingTable | RUNBOOK invoke via `InvokeAgentRuntime` | Cognito IdP (defer) |
| CLI HITL + Sessions | Teardown stack name(s) | Gateway MCP as MVP blocker |
| Eval harness | Short idle session timeout for demos | Claiming cost savings without scorecard |

## Cost / risk (not measured)

Published list prices (commercial; verify at deploy time on the [AgentCore
pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) page):

- **Runtime:** ~$0.0895 / vCPU-hour (active CPU) + ~$0.00945 / GB-hour
  (peak memory while session alive). No session ⇒ no Runtime CPU/memory bill;
  I/O wait does not bill CPU.
- **Gateway (if used):** per-invocation + optional tool-index monthly fees —
  avoid leaving indexed Gateway targets idle; prefer destroy.
- **ECR** image storage is a small always-on cost if the stack is left up —
  destroy with teardown when dormant (ADR-008).

SupportRouter must **not** claim AgentCore is cheaper than Lambda until a
measured scorecard/billing extract exists (#95). Idle-month target remains
near-zero via `cdk destroy` of the AgentCore stack when not demoing.

## Implementation sequence (updates #93–#95)

1. **#94** — CDK `SupportRouter-AgentCore` (Runtime + ECR), thin entrypoint,
   RUNBOOK, teardown; tools still Lambda-invoke.
2. **#93** — Optional Gateway MCP targets for the three Lambdas.
3. **#95** — Smoke eval / explicit not-measured release note.

## Consequences

- ADR-006 “later” is now specified; Lambda remains the default host.
- Domain seams (classifier, router, tools, KB, guardrails, confidence, HITL)
  stay stable; only the host adapter is new.
- Stretch work is cost-sensitive: opt-in stack + destroy-friendly defaults.
