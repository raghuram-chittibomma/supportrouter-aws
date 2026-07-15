# Test Strategy

## Principles

- Deterministic logic (classifier stub rules, routing-table lookup, refund threshold, validation) uses exact-match unit tests.
- LLM-backed logic uses shape/constraint assertions, not brittle exact-text matching.
- Synthetic fixtures only; no network unless marked `@pytest.mark.llm` or `@pytest.mark.aws`.
- Tests live under `tests/`; never under `src/`.

## Layers

| Layer | Scope |
|-------|--------|
| Unit | Classifier, router, schemas, HITL threshold, confidence helpers |
| Integration | Graph nodes with mocked Bedrock/KB/tools |
| Contract | Lambda tool I/O schemas |
| Smoke | CLI happy path without Bedrock (first slice) |

## Definition of Done (tests)

New runtime behavior includes tests; CI runs `pytest` on every PR.
