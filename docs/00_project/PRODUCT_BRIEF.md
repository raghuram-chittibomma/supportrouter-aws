# Product Brief — SupportRouter (VoltEdge)

## Problem statement

VoltEdge support volume is dominated by routine order, return, FAQ, and compatibility questions. Using one large model for every turn wastes money; consequential actions (large refunds) need human oversight; quality must be proven with evaluations, not anecdotes.

## Personas

| Persona | Goals |
|---------|--------|
| **Maya** (customer) | Resolve order/return/FAQ questions quickly with trustworthy answers |
| **Jordan** (supervisor) | Approve high-value refunds; clear escalations with context |
| **Priya** (platform engineer) | Run evals, understand routing policy, watch cost/latency |
| **Alex** (hiring manager) | See disciplined SDLC and measured claims in the repo |

## Core workflows

1. FAQ/policy Q&A with citations  
2. Order status via tool  
3. Return initiation  
4. Refund ≤$100 auto / &gt;$100 HITL  
5. Product compatibility via RAG  
6. Low-confidence escalation  
7. Offline eval → scorecard → (later) routing update  

## Functional requirements (summary)

Authoritative acceptance criteria live in GitHub Issues. Themes:

- Classify task type deterministically (stub) then optionally with LLM.
- Route via DynamoDB routing table lookup.
- Retrieve KB snippets; call order/return/refund tools.
- Guardrails + confidence + HITL threshold.
- Eval harness writes versioned scorecards.

## Non-functional requirements (targets)

| NFR | Target |
|-----|--------|
| Latency | p95 &lt; 8s FAQ; &lt; 12s with tools (measure in evals) |
| Cost | Document per-conversation budget per milestone; measure |
| Quality | Judge + programmatic gates per task type before routing changes |
| Security | Guardrails (PII, denied topics, no financial advice); least-privilege IAM |
| Deploy | One-command CDK deploy + teardown |

## Assumptions & open questions

See [`AI_ORCHESTRATOR_BRIEF.md`](AI_ORCHESTRATOR_BRIEF.md). Open questions tracked as GitHub issues with `flag:open-question`.
