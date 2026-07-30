# ADR-019: Dual-Provider Guardrails (Local + Bedrock ApplyGuardrail)

## Status

Accepted (supersedes the “adapter pending” clause of
[ADR-012](ADR-012-guardrail-boundaries.md); boundary placement unchanged)

## Context

v0.1 deployed `SupportRouter-Guardrails` but the runtime graph only called the
local deterministic policy. Operators selecting `runtime_mode=aws` expected the
managed Bedrock Guardrail to screen input and output.

## Decision

1. Keep the two graph boundaries from ADR-012 (post-validate input; post-draft
   output).
2. **`runtime_mode=local`:** continue to use `assess_text` /
   `local_deterministic` (`supportrouter-local-guardrail` / `local-v0.2`).
3. **`runtime_mode=aws`:** call Bedrock `ApplyGuardrail` with
   `SUPPORTROUTER_GUARDRAIL_ID` and `SUPPORTROUTER_GUARDRAIL_VERSION` (CDK stack
   outputs). Map `GUARDRAIL_INTERVENED` → `blocked`; `NONE` → `allowed`.
4. Missing ID/version in aws mode fails closed (`blocked` /
   `guardrail_misconfigured`) rather than silently falling back to local.
5. Result metadata `guardrail.provider` is `bedrock` or `local_deterministic`
   from the live assessments.
6. Chat Lambda IAM gains `bedrock:ApplyGuardrail` scoped to the deployed
   guardrail ARN; ApiStack injects the ID/version env vars.
7. Guardrails API spend is **not measured** in chat cost fields until a
   scorecard covers it (draft token cost remains separate).

## Consequences

- Local adversarial eval harness stays on deterministic policy and must not
  claim managed execution.
- AWS demos require env vars (chat Lambda or Gradio/CLI shell) pointing at the
  deployed guardrail (`3hkym9cgw048` / version `1` in the demo account).
- Local and Bedrock policies are intentionally not claimed to be equivalent.
