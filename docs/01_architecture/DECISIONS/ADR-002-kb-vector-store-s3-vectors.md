# ADR-002: Knowledge Base Vector Store = Amazon S3 Vectors

## Status

**Superseded by [ADR-007](ADR-007-s3-vectors-over-opensearch.md)**

## Context

Bedrock Knowledge Bases can use OpenSearch Serverless, Aurora pgvector, S3 Vectors, and others. OpenSearch Serverless often has a high idle cost floor unsuitable for a low-cost portfolio demo.

## Decision

Use **Amazon S3 Vectors** as the vector store behind Bedrock Knowledge Bases for the VoltEdge FAQ/policy corpus.

## Consequences

- Low idle cost; suitable for tiny synthetic corpora.
- Sub-second retrieval is acceptable for demo latency targets.
- If hybrid search or higher QPS is needed later, supersede with OpenSearch via a new ADR.

## Supersession

Retained for history. Operational guardrails (anti-AOSS quick-create, estimated idle-cost comparison, cleanup procedure) live in ADR-007.
