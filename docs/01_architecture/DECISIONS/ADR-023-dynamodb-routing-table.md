# ADR-023: DynamoDB RoutingTable Publish and Lookup

## Status

Accepted (completes ADR-022 DynamoDB deferral for v0.2)

## Context

PRODUCT and ARCHITECTURE specify routing via DynamoDB. ADR-022 delivered
offline generation and file-seed adopt; runtime still read
`data/sample/routing_table.json` only. Operators need a pay-per-request table
and a publish path so AWS chat can use scorecard-adopted routes without
scanning.

## Decision

1. **Table:** `supportrouter-routingtable` in `SupportRouter-Api`, PK
   `task_type` (S), on-demand billing, AWS-managed encryption, DESTROY with
   stack (DATA_MODEL attributes: `model_id`, `quality_score`,
   `cost_per_1k_tokens`, `p95_latency_ms`, `routing_table_version`,
   `updated_at`).
2. **Lookup:** chat Lambda `GetItem` by `task_type` when
   `SUPPORTROUTER_ROUTING_TABLE_NAME` is set; fall back to `unknown` item;
   no Scan. Explicit `table_path` still forces file mode (tests).
3. **Publish:** operator CLI `python scripts/publish_routing_table.py` (and
   optional reseed hook) uses caller credentials to `PutItem` each route.
   Chat role does **not** get write on RoutingTable.
4. **Local default:** without the env var, JSON seed remains the source of
   truth (Gradio/CLI offline).

## Consequences

- File adopt + Dynamo publish are separate steps: adopt seed, then publish.
- Teardown via `cdk destroy` removes the table with Api stack.
- Scorecard → generator → adopt → publish is the full v0.2 policy path.
