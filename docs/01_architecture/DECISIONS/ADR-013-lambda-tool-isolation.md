# ADR-013: Lambda Tool Isolation and Synthetic Write Semantics

## Status

Accepted

## Context

Order status, return initiation, and refund preparation need deployable Lambda
interfaces without granting one shared role broad access to all runtime data.
Refund preparation must not be represented as payment execution.

## Decision

Deploy three independent Lambda functions from `tools/`:

1. `get_order_status` — `GetItem` on `Orders` only
2. `initiate_return` — `GetItem` on `Orders`; `GetItem`/`PutItem` on `Returns`
3. `issue_refund` — `GetItem` on `Orders`; `GetItem`/`PutItem` on
   `RefundRequests`

Each function receives its own IAM execution role. DynamoDB and log permissions
are resource-scoped; no role receives `dynamodb:*`, wildcard resources, or an
AWS managed Lambda execution policy.

All tables use on-demand billing and destructive removal for the synthetic demo
environment. Functions run outside a VPC, use 128 MB ARM64 Python runtimes, and
write to pre-created 14-day log groups.

Inputs use `{ "order_id": "VE-####" }`. Return and refund records use
deterministic IDs (`RMA-<order_id>`, `REFUND-<order_id>`) and conditional
`attribute_not_exists` writes. A repeated request returns the existing record as
an idempotent replay.

`issue_refund` only prepares a synthetic request:

- amount `<= $100`: `status=prepared`
- amount `> $100`: `status=pending_approval`
- every record: `execution_status=not_executed`

It has no permission or integration for payment execution and cannot write
sessions, approvals, returns, or unrelated tables. The later HITL persistence
slice may create a separate `ApprovalRequest` for a pending high-value refund.

## Consequences

- A compromised tool role has a narrow data blast radius.
- Local and Lambda handlers expose matching response contracts.
- Orders must be seeded before live invocation; local JSON remains the current
  graph data source until the runtime adapter is wired.
- One synthetic return and refund request per order is the v0.1 idempotency
  scope.
- Live deployment, invocation wiring, and measured Lambda cost remain deferred.
