# Architecture — SupportRouter

## Recommendation

**Option B: LangGraph-on-Lambda runtime + separate offline eval plane** (Step Functions fan-out, scorecards, later routing-policy generator). Preserves a clean path to Bedrock AgentCore Runtime without rewriting tools/KB/router contracts.

## Runtime plane

```
API Gateway → Support Lambda (LangGraph)
  → validate / Guardrails (input)
  → task-type classifier
  → model router (DynamoDB routing table)
  → retrieve (Bedrock Knowledge Bases) and/or tools (order / return / refund Lambdas)
  → draft response
  → Guardrails (output)
  → confidence score
  → HITL decision (refund > $100 or low confidence)
  → response { answer, citations, confidence, status }
  → session + cost trace (DynamoDB / CloudWatch)
```

## Eval plane

```
EventBridge (schedule/manual) → Step Functions Map
  → run golden scenarios × candidate models
  → programmatic metrics + LLM-as-judge
  → EvalScorecards
  → (m2+) routing policy generator → RoutingTable version
```

## Requirement → component mapping

| Requirement theme | Components |
|-------------------|------------|
| FAQ/policy answers | Classifier, KB retriever, agent, citations |
| Order status | Classifier, router, order tool, agent |
| Returns | Return tool, agent, KB policies |
| Refunds | Refund tool, HITL ($100), Guardrails |
| Product questions | KB retriever, agent |
| Escalation | Confidence scorer, HITL decision |
| Cost optimization | Model router, prompt caching, observability |
| Quality proof | Eval plane, scorecards, golden scenarios |
| Safety | Bedrock Guardrails, deterministic validation |
| IaC / ops | CDK, teardown, CloudWatch |

## ADRs

See [`DECISIONS/`](DECISIONS/).

## Future migration

Keep tool contracts, KB corpus, routing table schema, and eval harness stable. Milestone 6 may host the agent graph on AgentCore Runtime and expose Lambda tools via MCP without changing domain logic.
