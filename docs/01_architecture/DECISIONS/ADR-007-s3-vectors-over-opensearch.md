# ADR-007: S3 Vectors over OpenSearch Serverless (Idle Cost)

## Status

Accepted (supersedes [ADR-002](ADR-002-kb-vector-store-s3-vectors.md))

## Context

SupportRouter is used actively during build and only intermittently for demos. Near-zero idle cost is a hard requirement.

OpenSearch Serverless (AOSS) typically bills a minimum OCU floor continuously (commonly on the order of ~$175–350+/month) even with zero queries. Amazon S3 Vectors is pay-per-request/storage and is suitable for a small, latency-tolerant knowledge base.

Bedrock Knowledge Base **quick-create** can silently provision an AOSS collection. Deleting a Knowledge Base does **not** always delete that collection.

## Decision

1. Use **Amazon S3 Vectors** as the sole vector store behind Bedrock Knowledge Bases for VoltEdge FAQ/policy docs.
2. **Accept higher retrieval latency** versus AOSS in exchange for **~90% lower idle cost** (estimated until measured against Billing).
3. CDK **must wire S3 Vectors explicitly**. Do **not** use Bedrock console/quick-create paths that default to OpenSearch Serverless.
4. Never create OpenSearch Serverless collections for SupportRouter.

## Estimated idle comparison (not measured)

| Backend | Idle / floor (est.) | Query model |
|---------|---------------------|-------------|
| OpenSearch Serverless | Continuous OCU minimum (~$175–350+/mo typical) | Always-on capacity |
| S3 Vectors | Storage + per-request (near $0 when idle / torn down) | Pay-per-use |

Label all README/release claims **estimated** until Billing or scorecard evidence exists.

## Consequences

- CDK Knowledge Base stack selects S3 Vectors storage configuration only.
- Post-teardown checklist must verify **zero** AOSS collections remain.
- If an AOSS collection is ever discovered:

```bash
aws opensearchserverless list-collections
# Confirm nothing else references the collection, then:
aws opensearchserverless delete-collection --id <collection-id>
```

- If hybrid search / high QPS becomes required later, supersede this ADR (do not edit history).

## Related

- ADR-008 — dormancy-safe ops profile (schedule, budget, teardown)
- Issue #13 — Bedrock KB setup
