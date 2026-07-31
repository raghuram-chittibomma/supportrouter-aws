# SupportRouter — AWS architecture diagrams (AI + AWS)

AWS path only (`runtime_mode=aws`). Local stubs omitted. Open this file in the
editor/preview so each diagram can render at full width.

---

## 1. System overview

```mermaid
flowchart LR
  Client([Client]) --> APIGW[API Gateway<br/>POST /chat]
  APIGW --> Chat[Chat Lambda<br/>LangGraph]

  Chat --> Bedrock[Bedrock<br/>Converse · Guardrails · KB]
  Chat --> Tools[Tool Lambdas<br/>order · return · refund]
  Chat --> DDB[(DynamoDB<br/>Sessions · Approvals · RoutingTable)]

  Bedrock --> S3V[(S3 Vectors)]
  Tools --> ToolDDB[(Orders · Returns · Refunds)]

  Eval[Eval harness --live] --> Bedrock
  Eval --> SC[Scorecards]
  SC --> Gen[Routing policy gen]
  Gen --> DDB

  Obs[CloudWatch + Budgets] --- Chat
  Obs --- Bedrock

  AC{{AgentCore Runtime<br/>opt-in}} -.-> Chat
  GW{{AgentCore Gateway MCP<br/>opt-in}} -.-> Tools
```

---

## 2. AI agent loop on Chat Lambda

```mermaid
flowchart TB
  IN[HTTP message] --> VAL[Validate]
  VAL --> GIN[Guardrails IN<br/>ApplyGuardrail]
  GIN --> CLS[Classify task_type]
  CLS --> RTR[Route model<br/>RoutingTable GetItem]
  RTR --> NEED{Context?}

  NEED -->|RAG| KB[Bedrock KB Retrieve<br/>S3 Vectors]
  NEED -->|Tools| TL[Invoke tool Lambda]

  KB --> DR[Draft via Converse<br/>+ prompt cache]
  TL --> DR
  DR --> GOUT[Guardrails OUT]
  GOUT --> CF[Confidence score<br/>deterministic]
  CF --> HITL{Refund &gt; $100?}
  HITL -->|yes| AP[ApprovalRequests]
  HITL -->|no| ESC{Low confidence?}
  ESC -->|yes| ES[status=escalated]
  ESC -->|no| OK[status=resolved]
  AP --> RESP[JSON response]
  ES --> RESP
  OK --> RESP
  RESP --> SESS[Sessions PutItem]
```

---

## 3. Eval plane → routing table

```mermaid
flowchart LR
  Gold[Golden scenarios] --> Harness[evals.harness --live]
  Harness --> Cand[Candidate models<br/>Converse fan-out]
  Harness --> Judge[LLM-as-judge<br/>Haiku 4.5 + cache]
  Cand --> SC[Scorecard JSON]
  Judge --> SC
  SC --> Gen[generate_routing_policy]
  Gen --> Pub[publish_routing_table]
  Pub --> RT[(RoutingTable)]
  RT --> Chat[Chat Lambda router]

  EB{{EventBridge<br/>default OFF}} -.-> Harness
```

---

## 4. Opt-in AgentCore stretch

```mermaid
flowchart TB
  Op[Operator SigV4] -->|InvokeAgentRuntime| ACR[AgentCore Runtime<br/>enable_agentcore=true]
  ACR --> Same[Same run_agent graph]
  Same --> Tools[Tool Lambdas]
  Same --> Bedrock[Bedrock]

  MCP[MCP client] -->|tools/call| ACG[AgentCore Gateway<br/>enable_agentcore_gateway=true]
  ACG -->|order-status___get_order_status etc.| Tools

  Note[Api Gateway + Chat Lambda<br/>remain default edge]
```

---

## AI engineering map

| Concern | AWS / component |
|---------|-----------------|
| Classification | Classifier → `task_type` |
| Model routing | DynamoDB `RoutingTable` |
| RAG | Bedrock KB + S3 Vectors |
| Tool use | 3 Lambdas + tool DynamoDB |
| Drafting + cache | Bedrock Converse + `cachePoint` |
| Safety | Bedrock Guardrails |
| Confidence / HITL | Deterministic policy + Approvals table |
| Eval / judge | Live harness + Haiku judge |
| Policy update | Scorecard → generator → publish |
| Dual-run / MCP | AgentCore Runtime / Gateway (opt-in) |
| Ops | CloudWatch, Budgets, CDK |
