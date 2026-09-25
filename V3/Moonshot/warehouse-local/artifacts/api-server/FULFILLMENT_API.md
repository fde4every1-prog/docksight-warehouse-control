# Fulfillment POC API contract

> **Archived policy-v1 reference — not the active API contract.**
> The old calculations, planner and executor are retired. All new orders use
> policy v2, per-SKU sub-orders and free-stock accounting, including requests
> with an explicit warehouse. The current unified PRD,
> architecture and decision record is [CONTROL_TOWER.md](CONTROL_TOWER.md).
> In v2, acceptance debits all three source quantities and credits reservations;
> Pick releases reservations without another source debit. Do not apply the
> historical WMS-only ATP formula or full-order payload rule to v2.

This is a shared, unauthenticated proof of concept. Every file under
`brownfield/.../data` is an immutable reference snapshot. The fulfillment
database is separate (`.local/fulfillment.sqlite`), and all plans,
reservations, task completions, assignments, and scenario overlays are
simulated only. This API does not certify live feasibility, connect to
controllers, or actuate robots.
Safety-ineligible resources remain visible through the resource browser and
are annotated with their exclusion reasons by the client or plan.

## Catalog and source browsers

`GET /api/fulfillment/catalog`

Returns:

```json
{
  "warehouses": [{"warehouse_id": "DC-01", "...": "..."}],
  "skus": [{"sku": "SKU-00001", "...": "..."}],
  "datasets": [{
    "name": "robots",
    "count": 712,
    "fields": ["robot_id", "..."],
    "planning_impact": "Direct planner input: ...",
    "source_field_count": 13,
    "api_field_count": 13,
    "missing_columns": []
  }],
  "counts": {"warehouses": 18, "skus": 1200, "robots": 712},
  "scenario": {"revision": 0, "modified_count": 0},
  "scenario_revision": 0,
  "scenario_modified_count": 0,
  "source_audit": [{"dataset": "robots", "source_row_count": 712,
                    "source_fields": ["..."], "api_fields": ["..."],
                    "missing_columns": []}],
  "assumptions": ["..."]
}
```

`warehouses` contains all 18 supplied reference rows and `skus` all 1,200
supplied reference rows. `datasets` covers every supplied source dataset:
`warehouses`, `skus`, `vendors`, `robots`, `robot_aliases`, `inventory`,
`tasks`, `maintenance`, `priorities`, `zones`, `telemetry`,
`vision_observations`, `safety_events`, `events`, `charging_state`,
`control_assets`, `labor_capacity`, `orders`, and `shipments`.

The source audit is over the complete raw files (not a first-row/header
sample). Exact imported row/union-field counts are:

| dataset | rows | union fields |
|---|---:|---:|
| warehouses | 18 | 8 |
| skus | 1,200 | 7 |
| vendors | 10 | 5 |
| robots | 712 | 13 |
| robot_aliases | 2,136 | 3 |
| inventory | 9,360 | 10 |
| tasks | 8,732 | 10 |
| maintenance | 520 | 8 |
| priorities | 216 | 4 |
| zones | 216 | 7 |
| telemetry | 12,896 | 9 |
| vision_observations | 214 | 7 |
| safety_events | 1,170 | 8 |
| events | 7,474 | 8 |
| charging_state | 712 | 7 |
| control_assets | 918 | 6 |
| labor_capacity | 54 | 7 |
| orders | 3,500 | 9 |
| shipments | 3,500 | 7 |

`missing_columns` is `[]` for every dataset: `fields` and `api_fields` are
the union of every key in every original row, including nested JSONL event
records, and every resource row contains those source fields (missing values
are `null`). Computed browser annotations are additional row properties and
are not counted as source columns.

`GET /api/fulfillment/resources/{dataset}?warehouse_id=DC-01`

Returns an envelope with all matching raw snapshot rows (not a first-N sample):

```json
{
  "rows": [{"...source fields...": "...",
            "_scenario_row_id": 0, "_scenario_modified": false}],
  "total": 123,
  "fields": ["...union of every original source key..."],
  "editable_fields": ["..."],
  "field_types": {"wms_qty": "number", "inventory_status": "string"},
  "excluded_fields": {
    "warehouse_id": "Identity/reference key; editing it would break source relationships."
  },
  "planning_impact": "Direct planner input: ...",
  "revision": 0,
  "scenario_modified_count": 0
}
```

`fields` is calculated from complete original rows, not the first row. Every
row has a stable zero-based `_scenario_row_id`, even when
`warehouse_id` filtering is used. `_scenario_modified` indicates whether
that row has a SQLite overlay. `field_types` is one of `string`, `number`,
`boolean`, or `json`. CSV values remain source strings in returned rows even
when their control type is `number` or `boolean`; JSONL nested JSON fields
(for example `payload_json`) accept JSON objects/arrays. Computed inventory
metrics (`available_to_promise`, `poc_reserved`, and `poc_consumed`) are
never editable and are not source fields.

`editable_fields` excludes identity/reference keys (including IDs, `sku`,
`warehouse_id`, relationship zones/locations, `shift`, and `source`);
`excluded_fields` and `excluded_field_reasons` explain each exclusion.
Unknown fields, identity/reference fields, invalid types, invalid numeric
domains, non-finite numbers, and malformed JSON return HTTP 422.

`planning_impact` is deliberately dataset-specific. The planner consumes
`inventory` (WMS ATP fields), `robots` (eligibility/capacity fields),
`maintenance` (robot exclusion fields), `labor_capacity` (shared worker
pools), and `control_assets` (clear available pack stations). `warehouses`
and `skus` are only order-input validation context. `robot_aliases`, `tasks`,
`priorities`, `zones`, `telemetry`, `vision_observations`, `safety_events`,
`events`, `charging_state`, `orders`, and `shipments` are context-only for
this POC planner; editing them does not alter scheduling.

### Persistent scenario overrides

`PATCH /api/fulfillment/resources/{dataset}/{row_id}` edits a source row
without changing the imported file:

```json
{"values": {"wms_qty": 25, "reserved_qty": 3}, "revision": 0}
```

`values` is a non-empty partial object of editable source fields. The
response contains the updated `row`, the resource contract fields above,
and the new `revision` / `scenario_modified_count`. A successful mutation
increments the global scenario revision. Concurrent or stale writes return
HTTP 409 with the current revision; clients should refetch the resource
envelope and retry. Validation and revision checks are atomic, so invalid
requests never create a partial overlay.

`DELETE /api/fulfillment/resources/{dataset}/{row_id}?revision=1` resets one
row. `DELETE /api/fulfillment/scenario?revision=2` resets all rows and
returns the new revision and zero modified count. Both operations use the
same optimistic revision and return HTTP 409 while any order is `planned`,
`queued`, or `running`, with an actionable instruction to cancel or finish
that order first. Held and completed orders do not block a reset. Resetting
source overlays does not reverse already consumed POC stock: completed pick
effects remain in SQLite and only imported source values are restored.

## State and order schemas

`GET /api/fulfillment/state` returns:

```json
{
  "orders": [order],
  "tasks": [task],
  "alerts": [{"warehouse_id": "DC-01", "sku": "SKU-00001", "available": 4, "threshold": 10}],
  "config": {
    "min_stock_threshold": 10,
    "unit_weight_kg": 1,
    "staging_capacity": 10,
    "shift": "1"
  },
  "scenario_revision": 0,
  "scenario_modified_count": 0,
  "server_time": "2026-09-11T12:00:00Z",
  "assumptions": ["..."]
}
```

`order` is:

```json
{
  "id": "FUL-...",
  "warehouse_id": "DC-01",
  "priority": "standard",
  "ship_by": "2026-09-12T12:00:00Z",
  "status": "held",
  "created_at": "2026-09-11T12:00:00Z",
  "lines": [{"sku": "SKU-00001", "quantity": 2}],
  "plan": {},
  "issues": ["..."]
}
```

`GET /api/fulfillment/orders/{id}` returns the full order plus
`events:[{"at":"...","message":"..."}]` and `tasks:[task]`.

`task` is:

```json
{
  "id": "TS-...",
  "order_id": "FUL-...",
  "stage": "pick",
  "status": "pending",
  "resource_id": null,
  "resource_type": null,
  "started_at": null,
  "due_at": null,
  "completed_at": null,
  "auxiliary_resources": [{"resource_id": "WORKER-DC-01-1", "resource_type": "worker"}]
}
```

Stages are `pick`, `transfer`, `pack`, and `dispatch`. Tasks are persistent
and execute in that order. Each acquired task is simulated by a dummy
completion after the shared configured duration (45 seconds by default) from
its persisted `started_at`; startup recovery completes due tasks once (never
twice) using the persisted `due_at`, so a restart or later configuration
change cannot reset the timer or duplicate inventory effects.

### Weight and payload rules

`inventory.weight_kg` is synthetic per-unit demo data, not a measured physical
weight. For every SKU requested by an order, every inventory row for that SKU
across all warehouses must have the same positive, finite `weight_kg`. A
missing, non-finite, non-positive, or inconsistent value is a validation
failure; the planner never falls back to a global unit weight.

For a new order, an explicit `POST /api/fulfillment/orders/{id}/retry`, or a
persona recovery action that recalculates the order, the planner reads the
current inventory weights and recalculates the complete order. The pick and
transfer robot payload is the unsplit full-order payload, calculated as the
sum of each line's quantity times its SKU weight. Manual fallback is also
bounded by `manual_payload_limit_kg` using that same full-order payload.
Existing reservations, persisted plans, and completed work are otherwise
unchanged; recalculation must not replay completed work or duplicate stock
effects.

Each newly calculated plan includes:

```json
{
  "payload_kg": 12.5,
  "total_expected_weight_kg": 12.5,
  "weight_source": "inventory.weight_kg",
  "weight_label": "Synthetic demo SKU weights; not measured physical weights",
  "weight_lines": [
    {"sku": "SKU-00001", "quantity": 2, "unit_weight_kg": 5, "line_weight_kg": 10},
    {"sku": "SKU-00002", "quantity": 1, "unit_weight_kg": 2.5, "line_weight_kg": 2.5}
  ]
}
```

`unit_weight_kg_assumption` is not emitted on new plans. The global
`config.unit_weight_kg` setting remains in the state and config contracts only
for backward compatibility; it is deprecated, has no planning effect, and is
not a fallback.

## Commands

`POST /api/fulfillment/orders`

Body:

```json
{
  "warehouse_id": "DC-01",
  "priority": "standard",
  "ship_by": "2026-09-12T12:00:00Z",
  "lines": [{"sku": "SKU-00001", "quantity": 2}],
  "request_id": "uuid"
}
```

`ship_by` must be a future UTC ISO-8601 timestamp, quantities must be positive
integers, the warehouse and every SKU must be known. `request_id` is an
idempotency key: repeating it returns the original order without another
reservation. The response is the full `order`. Creation validates, attempts an
all-or-nothing reservation, and creates the complete four-stage plan for
review. A feasible order is returned as `planned`; a shortage or
capacity/deadline issue is returned as `held` with actionable issues and no
partial reservation. A `planned` order is not queued or started until
explicitly released.

The FDE Bazaar intake API requires every new request to include a known,
nonblank `warehouse_id`. For Core requests carrying both that explicit
warehouse and `order_source: "fde_bazaar"`, Control Tower checks every
requested SKU quantity against eligible `AVAILABLE`, nonblocked inventory
using the sum of each location's
`min(wms_qty, erp_qty, vision_qty)` in that warehouse. This check and the
existing location reservation path run in the same `BEGIN IMMEDIATE`
transaction. If any line is short, the API returns 422 with
`warehouse_id`, `sku`, `requested`, and `available`; no order, sub-order, task,
progress, reservation, or movement is created, and stock in another warehouse
is never used. Eligible quantities may still be combined across multiple
zones/locations in the selected warehouse. An already accepted idempotent
request is returned before current inventory is rechecked, including legacy
requests whose warehouse was omitted. Pre-policy durable Bazaar outbox
messages that omitted `warehouse_id` retain the legacy automatic allocation
path so deployment does not strand already accepted upstream work; their
original idempotency fingerprint is not rewritten.

`POST /api/fulfillment/orders/{id}/start` releases an already `planned` order
to the executor (`queued`). It does not replan or reserve. The review window
therefore runs from successful POST through explicit `start`.

`POST /api/fulfillment/orders/{id}/retry` retries a `held` order with the
current snapshot/configuration, reserving and replanning but never
auto-starting it. `POST /api/fulfillment/orders/{id}/cancel` cancels only
before any task starts and releases its POC reservations.
Commands return the full order. Invalid commands return actionable HTTP 409
or 422 errors.

## Config

`PUT /api/fulfillment/config` is admin-persona only and accepts any of:

```json
{
  "min_stock_threshold": 10,
  "unit_weight_kg": 1,
  "staging_capacity": 10,
  "shift": "1",
  "manual_payload_limit_kg": 25,
  "task_duration_seconds": 45
}
```

Bounds are validated. Config is persisted in SQLite and affects new plans;
`min_stock_threshold` is retained only for backward compatibility and no
longer drives low-stock alerts. `unit_weight_kg` is also retained only for
backward compatibility (deprecated, with no planning effect),
`staging_capacity` bounds active dispatch staging slots, `shift` must be one of
the supplied labor shifts, and
`manual_payload_limit_kg` bounds explicit manual fallback.
`task_duration_seconds` is a whole number from 1 through 86400 shared by robot
and control-asset stages. It is captured on each new assignment without
changing running deadlines or paused recovery metadata. This configurable
simulator delay is not an observed handling-rate metric. Inventory weights are
synthetic demo values and must be
present and consistent rather than replaced by an assumption. All other
missing topology/rate values remain explicit assumptions rather than invented
operational facts.

The initial shift is the first configured source value (`"1"` in the supplied
snapshot). Accepted values are read from the complete `labor_capacity` source
(`"1"`, `"2"`, and `"3"` in this snapshot), not hard-coded as a numeric
operational assumption.

The planner uses explicit demo-only compatibility assumptions: pick robots are
`AGV`, `AMR`, `CASE_PICKER`, or `FORK_AMR`; transfer robots are `AGV`, `AMR`,
`FORK_AMR`, `PALLET_MOVER`, or `TUGGER`; each robot must also meet planned
payload capacity. Robot pick/transfer tasks reserve a shared
`certified_robot_operators` plus `actual_workers` slot, pack reserves both a
clear `PACK_STATION` (or explicit manual fallback) and `pack_staff` plus
`actual_workers`, and dispatch reserves a staging slot plus an actual worker.
These mappings are planning assumptions, not live topology or safety
certification.

## Demand forecasts

`GET /api/fulfillment/demand-forecasts` returns every operational
warehouse/SKU inventory pair. Optional `warehouse_id` and case-insensitive
`search` filters are supported. Availability is current free availability:
the sum across locations of nonnegative `min(wms_qty, erp_qty, vision_qty)`.
Those source quantities already represent free stock, so reservations are not
subtracted a second time. This reporting definition is distinct from the
planner's stricter eligible `allocatable_qty`; allocation safety is unchanged.

At 06:00 Asia/Kolkata each day, the service persists an idempotent snapshot.
Its transparent statistical baseline is mean ordered units per completed IST
calendar day, using at most 60 days and including zero-demand days. The global
earliest eligible order date within that window determines the short-history denominator.
Predictions are `ceil(mean * 7)` and `ceil(mean * 30)`. This is a statistical
baseline, not a trained machine-learning model. Canonical demand comes from
`sub_orders.quantity` and the parent order's original creation timestamp;
allocations and tasks are never counted. Cancelled parent or child demand is
excluded; rejected demand remains included under the existing model.
Warehouse-unassigned units are not invented or apportioned and are reported as
`excluded_unassigned_units`.

Coverage is `short_history` when a warehouse/SKU has demand in a global
1–59-day observed window, `observed` once that window reaches 60 days, and
`no_history` when that SKU has no attributable demand in the window. A
`no_history` item retains the global `history_days` for transparency while its
predictions are zero.

The persisted seven-day prediction replaces the fixed low-stock threshold and
uses strict `available_qty < forecast_7d`. If generation fails, the previous
valid run remains readable and is marked `stale`; there is no fixed-threshold
fallback.

### Saved forecast explanations

`GET /api/fulfillment/demand-forecasts/detail?warehouse_id=W1&sku=A&run_id=DFR-…`
returns the exact saved warehouse/SKU pair. Omit `run_id` to select the latest
run; an unknown run or mismatched pair returns 404, never a different selection.
The list and detail both return `run.id` and the same run metadata. Archived
superseded run IDs are also supported, with live (not historical) stock.

The response contains `run`, `item` (the list item shape), `history_available`,
`history`, `projection`, `stock_checked_at` (UTC ISO timestamp), and
`minimum_replenishment = max(0, forecast_7d - available_qty)`. Stock uses the
same warehouse-wide free-source-minimum sum as the list and low-stock alert,
not individual-location stock or planner eligibility.

New runs capture sparse daily inputs in `demand_forecast_daily_inputs` during
the same canonical aggregation and caller transaction as run/items. The
`demand_forecast_captures` marker distinguishes a captured empty window from
legacy runs with no recorded evidence. Evidence is immutable, keyed by run ID,
and retained with that ID when a run and its items enter the superseded archive.
Normal generation remains idempotent and does not backfill old runs.

`history` zero-fills all saved effective IST calendar days; its ordered units
sum to the saved `history_units`. `rolling_7d` is null for the first six days
and thereafter the trailing seven-calendar-day arithmetic mean. The rolling
series is explanatory, not the forecast model. No-history items may have
zero-filled global history days; a captured globally empty window has an empty
array with `history_available: true`. Legacy evidence is an empty array with
`history_available: false`; later order changes never reconstruct it.

`projection` has exactly 30 daily points starting on `forecast_date`, each
equal to saved `item.daily_demand`. Saved horizon totals use ceiling rounding,
not repeated daily totals or an invented trend. Legacy run metadata retains
its original lookback (30 days for v1). Coverage remains explicitly unverified:
zero filling expresses the model's calendar assumption, not proof of observed
source completeness. Preserve no/short-history, stale and unassigned warnings.

### Required operational refresh (main workspace, offline only)

**This implementation does not refresh operational data.** Existing operational
runs without captured inputs need an explicitly authorized main-workspace
maintenance refresh. Opening a chart never generates or refreshes a run.

1. Identify the actual operational `FULFILLMENT_DB_PATH` (default:
   `artifacts/api-server/.local/fulfillment.sqlite`). Stop **all** API workers
   and other database writers; do not run this against a subagent copy.
2. From the main workspace run the established backup-producing CLI, replacing
   the example with the verified absolute path:

   ```sh
   python artifacts/api-server/demand_forecast.py \
     --db /absolute/path/to/fulfillment.sqlite --refresh-current
   ```

3. The CLI fails closed on the shared operational maintenance lock, creates
   a consistent SQLite backup in the database directory's `backups/` folder,
   then runs the refresh under `BEGIN IMMEDIATE`. Keep its JSON output
   (`backup`, `run_id`, `superseded_run_id`) as maintenance evidence.
   It archives the current scheduled business-date run and saved item values;
   any captured daily inputs/marker remain addressable by the superseded ID.
   Legacy missing evidence stays missing. A failed refresh rolls back.
4. Verify the backup exists, the new run has captured evidence, and the old ID
   still resolves. Restart workers and check list/detail reconciliation.
   The scheduled business date is determined by the real 06:00 IST boundary;
   if no run exists for that date the CLI creates one without superseding
   older dates. Refresh is intentionally explicit, not idempotent; do not
   repeat casually. Normal scheduler generation remains idempotent.

The command changes forecast storage only, not order or inventory quantities.
If recovery is necessary, stop all writers again and restore the verified
SQLite backup through the normal offline recovery process (including safe
handling of SQLite WAL/SHM sidecars), rather than overwriting a live database.
