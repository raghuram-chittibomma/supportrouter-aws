# ADR-021: Bedrock Converse Prompt Caching Wiring

## Status

Accepted (supersedes ADR-005 implementation posture; ADR-005 intent retained)

## Context

ADR-005 decided to cache agent system/tool prefixes, eligible history, and the
eval judge rubric when supported, and to measure savings before README claims.
v0.1 scored `cache_status=not_configured` because Converse never sent a
`cachePoint` and never mapped `cacheReadInputTokens` / `cacheWriteInputTokens`.

Claude Haiku 4.5 (judge default) requires ≥4096 tokens per checkpoint; Nova
Micro/Lite require ~1536. Unpadded system/rubric text is far below those
minima, so a bare `cachePoint` would succeed with no write/read activity.

## Decision

1. **API shape:** `converse_text(..., prompt_cache=True)` appends
   `{"cachePoint": {"type": "default"}}` to Converse `system` blocks and maps
   Bedrock cache usage into `cache_enabled`, `cache_status`,
   `cache_read_tokens`, and `cache_write_tokens`.
2. **Prefixes:** Agent (`agent-prefix-v0.3`) and judge (`eval-judge-rubric`)
   prefixes include deterministic synthetic **cache padding** sized to clear
   the **strictest** supported model minimum in the routing table (Claude
   Haiku 4.5 ≥4096 tokens). Request-specific content stays in the user message.
3. **Call sites:** AWS agent draft, live eval candidate draft, and Haiku judge
   enable prompt caching. Local stubs remain `cache_status=not_configured`.
4. **Status values:** `not_configured` | `write` | `hit` | `hit_and_write` |
   `below_minimum`. Never fabricate hits.
5. **Cost:** Scorecards price uncached input + cache write + cache read at
   published rates, and optionally compare to an **uncached-equivalent**
   (all input tokens at full input rate). README/release notes cite savings
   **only** from a measured artifact under `evals/scorecards/`.
6. **Measurement:** `python -m scripts.measure_prompt_cache` records cold write
   then warm read for the judge prefix.

Conversation-history caching remains deferred (ADR-005 item 2).

## Consequences

- Cold requests pay cache-write rates for the padded prefix; warm hits reduce
  effective input cost when reads occur within TTL.
- Padding increases minimum prompt size; it is versioned and byte-stable.
- ADR-005 remains the product intent; this ADR records the Converse wiring and
  measurement contract.
