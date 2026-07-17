# Data Model — SupportRouter

All data is **synthetic** for fictional VoltEdge Electronics.

## Product catalog (`data/sample/catalog.json`)

Fields: `sku`, `name`, `product_type`, `price_usd`, `warranty_months`, `support_themes[]`.

## Orders (DynamoDB `Orders` / local JSON)

| Attribute | Type | Notes |
|-----------|------|--------|
| `order_id` | S (PK) | e.g. `VE-1001` |
| `customer_id` | S | synthetic |
| `status` | S | placed / shipped / delivered / returned |
| `tracking_number` | S | optional |
| `items[]` | L | sku, qty, line_total_usd |
| `shipping_address` | M | synthetic |
| `created_at` | S | ISO-8601 |
| `refund_eligible` | BOOL | |
| `refund_amount_usd` | N | if applicable |

## Sessions (DynamoDB `Sessions`)

| Attribute | Type | Notes |
|-----------|------|--------|
| `session_id` | S (PK) | |
| `messages[]` | L | role, content, ts |
| `task_type` | S | last classified |
| `model_id` | S | selected |
| `status` | S | open / resolved / escalated / pending_approval |
| `confidence` | N | Deterministic evidence-capped score, 0.0–1.0 (ADR-009) |
| `citations[]` | L | doc_id, excerpt |
| `tool_calls[]` | L | name, args, result_ref |
| `cost_usd` | N | measured when available |
| `created_at` / `updated_at` | S | |

## Confidence and HITL policy

Confidence is a deterministic heuristic, not a calibrated probability. The
runtime starts with classifier confidence and applies the evidence cap for the
task type:

| Task family | Successful evidence cap | Missing/failed evidence cap |
|-------------|-------------------------|-----------------------------|
| FAQ / product question | `0.95` with citation | `0.45` without citation |
| Order / return / refund | `0.95` with successful tool result | `0.35` without successful tool result |
| Unknown | `0.40` | `0.40` |

The runtime starts with `score = classifier_confidence`, applies
`score = min(score, cap)` only when the task has a listed cap, then returns
`round(clamp(score, 0, 1), 3)`. An unlisted task type is only clamped and
rounded.

HITL rules are ordered:

1. A `refund_request` with `refund_amount_usd > 100.0` enters
   `pending_approval`.
2. Otherwise, confidence `< 0.55` enters `escalated`.
3. Otherwise, the outcome is `resolved`.

The boundaries are strict: `$100.00` and confidence `0.55` both remain on the
resolved path. See [ADR-009](DECISIONS/ADR-009-deterministic-confidence-policy.md).

## Routing table (DynamoDB `RoutingTable`)

| Attribute | Type | Notes |
|-----------|------|--------|
| `task_type` | S (PK) | |
| `model_id` | S | active selection |
| `quality_score` | N | from scorecard |
| `cost_per_1k_tokens` | N | reference |
| `p95_latency_ms` | N | |
| `routing_table_version` | S | |
| `updated_at` | S | |

## Eval scorecards (DynamoDB / `evals/scorecards/`)

`scorecard_id`, `dataset_version`, `prompt_version`, `judge_version`, `model_id`, `task_type`, programmatic metrics, judge scores, `pass`, `created_at`.

## Approval requests

`approval_id`, `session_id`, `order_id`, `amount_usd`, `status` (pending/approved/rejected), `reason`, timestamps.

## Knowledge base documents

Markdown under `data/knowledge_base/` with YAML front matter: `doc_id`, `product_sku` (optional), `policy_type`, `effective_date`, `title`. Citations return `doc_id` + excerpt.

## Golden eval scenario

```json
{
  "id": "ord-status-001",
  "task_type": "order_status",
  "input": "Where is my order #VE-1001?",
  "expected_tools": ["get_order_status"],
  "expected_citations": [],
  "expected_outcome": "resolved"
}
```
