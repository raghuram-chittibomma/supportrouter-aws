# ADR-017: HITL Session and Approval DynamoDB Persistence

## Status

Accepted

## Context

ADR-010 defined the `ApprovalRequest` lifecycle and DynamoDB conditional-write
seam. Local memory repositories satisfied the demo UI, but issue #16 requires
persisted approval requests and a supervisor decision path that survives process
restart. The chat Lambda previously had logs-only IAM (ADR-014/015).

## Decision

1. Create on-demand DynamoDB tables `supportrouter-sessions` and
   `supportrouter-approvalrequests` in `ApiStack`.
2. Select the DynamoDB repository when `SESSIONS_TABLE_NAME` and
   `APPROVALS_TABLE_NAME` are set; otherwise keep the in-memory backend.
3. Persist after each chat turn via `save_session` in the HTTP adapter and CLI.
4. Use conditional `PutItem` for approval create and `TransactWriteItems` for
   decide (approval + session status), preserving ADR-010 idempotency rules.
5. Provide CLI `list-pending` and `decide` for the v0.1 supervisor path.
   Escalations remain view-only; `execution_status` stays `not_executed`.
6. Grant the chat role scoped DynamoDB ``GetItem``/``PutItem`` on those two
   tables only — still no Bedrock invoke permissions (drafting remains local
   stub). Supervisor CLI ``list-pending``/``decide`` uses caller credentials for
   ``Scan``/``TransactWriteItems``.

## Consequences

- HITL approvals survive Lambda cold starts and local CLI against the same tables.
- Refund execution remains out of scope.
- Cost remains `not_measured` for chat drafting; DynamoDB on-demand idle cost is
  near zero when unused.
