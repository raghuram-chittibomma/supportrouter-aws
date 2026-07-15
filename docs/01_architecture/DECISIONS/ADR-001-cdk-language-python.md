# ADR-001: CDK Language = Python

## Status

Accepted

## Context

SupportRouter runtime and evals are Python (LangGraph, pytest). The team is one person for a portfolio demo. CDK supports TypeScript and Python.

## Decision

Use **AWS CDK with Python** for all infrastructure.

## Consequences

- Single language across `src/`, `tools/`, `infra/`, `evals/`, `tests/`.
- Share types/schemas more easily between app and IaC helpers.
- TypeScript CDK ecosystem examples may need translation.
