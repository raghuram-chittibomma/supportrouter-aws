# ADR-010: Refund Approval Lifecycle and Persistence Seam

## Status

Accepted

## Context

Refunds above `$100` require human approval, while low-confidence requests are
escalations. Treating both as the same Approve/Reject queue obscures their
different semantics and makes retries, concurrent decisions, and future
DynamoDB persistence unsafe.

The local demo must prove the approval lifecycle without claiming durable
persistence or executing a real refund.

## Decision

Model high-value refund approval as an explicit `ApprovalRequest`, separate from
the support session and from low-confidence escalation.

The lifecycle is:

```text
pending → approved
pending → rejected
```

- Creation is deterministic for a session: `approval-<session_id>`.
- Identity fields (`session_id`, `order_id`, `amount_usd`, `reason`) are
  immutable after creation.
- Re-saving the same pending session is idempotent and cannot replace approval
  identity fields.
- Repeating the same terminal decision is idempotent.
- A conflicting terminal decision is rejected.
- Approval `approved` maps the session to `resolved`.
- Approval `rejected` maps the session to `rejected`.
- `execution_status` remains `not_executed` in the local slice. Approval does
  not imply that a refund was executed.
- Low-confidence escalations remain view-only locally and do not create an
  `ApprovalRequest`. Escalation disposition is a separate future workflow.

The local repository uses in-memory dictionaries and a process-local lock. The
AWS implementation will retain the contract and use DynamoDB conditional
writes:

- Create only when `attribute_not_exists(approval_id)`.
- Decide only when `status = pending` (and optionally `version = :expected`).
- If the stored status already equals the requested terminal status, return the
  existing record as an idempotent success.
- Update the approval and denormalized session status transactionally.

## Consequences

- The local UI safely demonstrates approval decisions without payment claims.
- Decisions survive concurrent threads in one process, but not process restart
  or multiple workers.
- DynamoDB durability, cross-process concurrency, IAM, and refund execution
  remain part of the AWS tools/HITL work (#14/#16).
- Escalations can be inspected in v0.1 but need a separate disposition contract
  before supervisors can resolve them.
