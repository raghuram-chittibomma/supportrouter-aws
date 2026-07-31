# ADR-022: Offline Routing-Policy Generation from Scorecards

## Status

Accepted (implements ADR-003 milestone-2 path; file-based only)

## Context

ADR-003 defines candidate selection (cheapest within 5% of best quality under a
p95 latency cap) but leaves the numeric quality formula and latency default
unspecified. Runtime still loads `data/sample/routing_table.json`; DynamoDB
publish remains deferred. Priya needs an offline, testable transform from a
measured scorecard to a candidate routing table without Bedrock spend.

## Decision

1. **Input:** a versioned scorecard JSON. Refuse `local_stub` / incomplete
   scorecards unless `--allow-incomplete` (not for release claims).
2. **Quality:** `mean(faithfulness, helpfulness, policy_adherence) / 5.0` over
   completed judge rows, aggregated per `(task_type, routing model_id)`.
3. **Latency:** p95 of `wall_time_ms` per candidate; default cap **12000 ms**
   (NFR tools path), overridable via CLI.
4. **Cost ranking:** mean measured `cost_usd` per candidate (fallback:
   published input `$/1K` tokens). Table still records `cost_per_1k_tokens`
   from published rates for the chosen model.
5. **Selection:** among candidates under the latency cap, take those within
   `quality_tolerance` (default 0.05) of the best quality; pick the cheapest.
6. **Output:** routing-table-shaped JSON with
   `routing_table_version=generated-from-<scorecard_id>`, selection audit
   trail, and optional keep-seed for task types absent from the scorecard.
   Does not overwrite the seed file unless the operator points `--out` at it.
7. **CLI:** `python -m evals.generate_routing_policy`.

DynamoDB RoutingTable publish is out of scope (follow-on).

## Consequences

- Routing policy updates are reproducible from scorecard artifacts.
- Partial scorecards (few task types) only regenerate covered routes unless a
  seed table is supplied for passthrough.
- README/release notes must cite the source scorecard when claiming a generated
  policy; the transform itself is not a measured cost event.
