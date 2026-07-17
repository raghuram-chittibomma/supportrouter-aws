# Architecture — SupportRouter

## Recommendation

**Option B: LangGraph-on-Lambda runtime + separate offline eval plane** (Step Functions fan-out, scorecards, later routing-policy generator). Preserves a clean path to Bedrock AgentCore Runtime without rewriting tools/KB/router contracts.

## Runtime plane

```
API Gateway → Support Lambda (LangGraph)
  → validate / Guardrails (input)
  → task-type classifier
  → model router (DynamoDB routing table)
  → retrieve (Bedrock Knowledge Bases over S3 Vectors) and/or tools (order / return / refund Lambdas)
  → draft response
  → Guardrails (output)
  → deterministic evidence-capped confidence score (ADR-009)
  → refund approval decision when amount > $100 (ADR-010)
  → low-confidence escalation (separate from refund approval)
  → response { answer, citations, confidence, status }
  → session + cost trace (DynamoDB / CloudWatch)
```

**Vector store:** Amazon **S3 Vectors** behind Bedrock Knowledge Bases ([ADR-007](DECISIONS/ADR-007-s3-vectors-over-opensearch.md)). OpenSearch Serverless is forbidden for SupportRouter (idle OCU floor).

Retrieval defaults to the deterministic local corpus. The same citation
contract can use the managed KB explicitly with
`SUPPORTROUTER_RETRIEVER=bedrock` and `SUPPORTROUTER_KB_ID=<id>`. Managed
retrieval failures are surfaced rather than silently falling back to local
results. The KB role scopes S3 Vectors permissions to its bucket and index.

## Eval plane

```
EventBridge (OPTIONAL schedule; default OFF) or manual → Step Functions Map
  → run golden scenarios × candidate models
  → programmatic metrics + LLM-as-judge
  → EvalScorecards
  → (m2+) routing policy generator → RoutingTable version
```

CDK context `enable_reeval_schedule` defaults to `false` — **no EventBridge rule is created** when false ([ADR-008](DECISIONS/ADR-008-dormancy-safe-cost-profile.md)).

## Cost profile

Near-zero idle cost is a hard requirement. App is used during build and intermittently for demos.

| Mode | Expected cost | Assumptions |
|------|---------------|-------------|
| **Dormant month** | ~$0–2 (estimated) | `cdk destroy` completed; no AOSS; no eval schedule; no NAT/VPC |
| **Active demo month** | Low tens of USD; Budget alert **$20/mo** | Intermittent Lambda/API Gateway/Bedrock; tiny KB on S3 Vectors; manual evals; `cache_enabled=false` until measured |

**Always-on landmines to avoid:** OpenSearch Serverless, NAT Gateways, never-expire log groups, standing eval/ingestion schedules, >3 CloudWatch dashboards.

**Token amplification:** One user-visible agent turn can trigger multiple Bedrock calls (classify/draft/judge/fan-out), often **5–10×** tokens versus a single completion. See [EVAL_STRATEGY.md](../02_testing/EVAL_STRATEGY.md).

All figures above are **estimated** until Billing/scorecard evidence exists (measured-metrics-only rule).

## Requirement → component mapping

| Requirement theme | Components |
|-------------------|------------|
| FAQ/policy answers | Classifier, KB retriever (S3 Vectors), agent, citations |
| Order status | Classifier, router, order tool, agent |
| Returns | Return tool, agent, KB policies |
| Refunds | Refund tool, HITL ($100), Guardrails |
| Product questions | KB retriever, agent |
| Escalation | Confidence scorer; view-only locally (disposition later) |
| Cost optimization | Model router, prompt caching, dormancy ops, observability |
| Quality proof | Eval plane, scorecards, golden scenarios |
| Safety | Bedrock Guardrails, deterministic local boundary, application validation |
| IaC / ops | CDK (no VPC), teardown/reseed, CloudWatch retention, Budget |

## ADRs

See [`DECISIONS/`](DECISIONS/). Key ADRs: **007** (S3 Vectors), **008**
(dormancy), **009** (deterministic confidence policy), **010** (refund approval
lifecycle), **011** (structured observability events), **012** (guardrail
boundaries), **013** (Lambda tool isolation), **014** (HTTP chat edge).

Local runtime emits structured step traces with request `correlation_id` →
`session_id` linkage. Token/cost fields are always present and stay
`not_measured` until Bedrock usage is recorded.

Local input/output guardrail nodes provide deterministic test coverage without
claiming managed Guardrails execution. The deployable Bedrock policy and
version are synthesized by `SupportRouter-Guardrails`; live invocation is
deferred to the Bedrock runtime adapter.

The three order tools are independently deployable Lambdas with separate roles
and resource-scoped DynamoDB access (ADR-013). The local graph still invokes
contract-compatible in-process stubs until the runtime Lambda adapter lands.

A thin HTTP chat edge (`SupportRouter-Api`) and the CLI both wrap the same
`run_agent` call (ADR-014). The edge is a throttled HTTP API in front of a chat
Lambda whose role can only write its own logs; drafting remains a local stub, so
no Bedrock/DynamoDB permissions are granted and cost stays `not_measured`.

## Future migration

Keep tool contracts, KB corpus, routing table schema, and eval harness stable. Milestone 6 may host the agent graph on AgentCore Runtime and expose Lambda tools via MCP without changing domain logic.
