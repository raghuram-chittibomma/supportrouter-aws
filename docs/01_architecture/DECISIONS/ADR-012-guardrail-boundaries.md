# ADR-012: Guardrail Boundaries and Local Safety Policy

## Status

Accepted

## Context

SupportRouter must screen both customer input and drafted output for sensitive
information, denied topics, and financial advice. The local graph does not call
Bedrock, but safety behavior and adversarial tests must be available before AWS
deployment.

## Decision

Place guardrail nodes at two explicit graph boundaries:

1. after deterministic message validation and before classification
2. after answer drafting and before confidence/HITL decisions

The local boundary uses a deterministic, versioned policy
(`supportrouter-local-guardrail`, `local-v0.1`) that blocks high-risk synthetic
PII patterns, dangerous/self-harm assistance, and financial advice. It records
categories but never matched text. A block replaces content with a fixed safe
message, sets the conversation to `rejected`, and prevents downstream
classification, tool calls, or answer delivery.

The CDK `SupportRouter-Guardrails` stack defines the deployable Bedrock
Guardrail with:

- harmful-content filters on input and output
- PII policies on input and output
- denied dangerous-assistance and financial-advice topics
- an immutable `AWS::Bedrock::GuardrailVersion`

The local policy is a testable fallback, not an assertion that Bedrock
Guardrails ran. When the Bedrock adapter lands, it must use the synthesized
guardrail identifier/version and replace local provider metadata with the live
assessment.

Deterministic application rules remain separate: order-ID validation, routing,
refund thresholds, and schema checks are not delegated to Guardrails.

## Consequences

- Every successful answer crosses both safety boundaries.
- Empty/previously rejected requests record skipped guardrail assessments.
- Session results and terminal traces record guardrail identifier, version, and
  input/output action.
- User-visible policy changes require adversarial eval/test updates.
- The local regex policy is intentionally narrower than managed Bedrock
  detection and must not be described as equivalent coverage.
- The deployable policy spec is SHA-256 fingerprinted into the GuardrailVersion
  resource identity, so policy changes synthesize a new immutable version.
