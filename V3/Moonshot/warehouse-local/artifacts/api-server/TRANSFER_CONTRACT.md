# DC-01 transfer batching API contract

Base path: `/api/batching/transfer`. All timestamps are RFC 3339 UTC strings (`Z`). Snapshot and scenario IDs are opaque, server-owned, ephemeral, and expire after 30 minutes. Clients must never persist them as operational records.

## `GET /preview`

Returns the read-only live-data readiness preview before upload.

```json
{
  "warehouse_id": "DC-01",
  "mode": "live",
  "ready": true,
  "blockers": [],
  "snapshot": {
    "snapshot_id": "opaque",
    "snapshot_at": "2026-01-01T12:00:00Z",
    "expires_at": "2026-01-01T12:30:00Z",
    "source_version": "sha256",
    "clock": {"at": "2026-01-01T12:00:00Z", "timezone": "UTC", "source": "live_simulation_clock"}
  },
  "map": {
    "width": 1200, "height": 720,
    "zones": [{"id":"ZONE-01","label":"Zone 1","x":60,"y":70,"width":220,"height":150}],
    "nodes": [{"id":"ZONE-01","x":170,"y":145,"zone_id":"ZONE-01"}],
    "edges": [{"from":"ZONE-01","to":"AISLE-01"}],
    "conveyor": {"id":"CONVEYOR-01","node_id":"CONVEYOR","label":"Conveyor receipt"}
  },
  "robots": [{
    "id":"source robot id","type":"AMR","capacity_kg":100,"battery_percent":85,
    "state":"idle","available":true,"capabilities":["pick","transfer"],
    "start_node":"...","eligible":true,"exclusion_reasons":[],"source_id":"..."
  }],
  "robot_candidates": [],
  "selection": {"selected_robot_ids":["all eligible frozen DC-01 robot IDs"],"required_count":8,"editable":false,"policy":"all_eligible_dc01"},
  "inventory_summary": {"eligible_skus":10,"eligible_bins":20},
  "assumptions": ["Illustrative geometry; not surveyed CAD."]
}
```

The server selects every eligible frozen DC-01 robot without a fleet-size cap. Readiness is blocked if that fleet has no robot with both pick and transfer capabilities. Records are never silently synthesized. `GET /preview?mode=synthetic_demo` returns the separately labelled synthetic demo.

## `GET /template`

Returns an XLSX attachment. Its example lines use eligible stock from the frozen live snapshot and include real example SKU/bin identifiers plus explicit UTC cut-offs. Optional query: `snapshot_id`.

## `GET /sample`

Returns the same example as JSON:

```json
{"snapshot_id":"opaque","headers":["Order ID","SKU","Qty","Order Cut-off"],"rows":[{"order_id":"EXAMPLE-...","sku":"real SKU","qty":1,"order_cutoff":"...Z","example_only":true}],"notes":[]}
```

## `POST /imports`

Body is raw XLSX (`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`), maximum 2 MiB. Required query: `snapshot_id`. Maximum one worksheet and 500 data rows. Accepted headers are exactly `Order ID`, `SKU`, `Qty`, `Order Cut-off`; `Order ID` and cut-off cells may be blank for later repair, but SKU and positive integral Qty may not.

```json
{
  "scenario_id":"opaque","snapshot_id":"opaque","revision":1,"valid":false,"ready_for_planning":false,
  "rows":[{
    "row_id":"ROW-2","source_row":2,"order_id":null,"sku":"SKU-1","quantity":2,
    "order_cutoff":null,"cutoff_timezone":"UTC","allocations":[],
    "unit_weight_kg":null,"total_weight_kg":null,"errors":[{"code":"MISSING_ORDER_ID","field":"order_id","message":"..."}],
    "warnings":[],"provenance":{"source":"xlsx","snapshot_id":"opaque"}
  }],
  "errors":[],"blockers":["..."],"map":{},"robots":[],"selected_robot_ids":[]
}
```

Malformed workbook/file-level errors use HTTP 422 with `{"detail":{"code":"...","message":"...","errors":[...]}}`; oversized bodies use 413.

## `GET /scenarios/{scenario_id}`

Returns the current normalized review document shown above. This is always rebuilt from the server-owned frozen snapshot.

## `PATCH /scenarios/{scenario_id}/rows`

Repairs editable grouping/cut-off fields. Robot selection is server-owned.

```json
{"revision":1,"rows":[{"row_id":"ROW-2","order_id":"ORDER-1","order_cutoff":"2026-01-01T13:00:00Z"}]}
```

Returns the complete normalized review with incremented revision. Unknown row IDs, stale revision, and conflicting cut-offs are HTTP 409/422. If legacy clients send `selected_robot_ids`, it must exactly equal the server-owned all-eligible set; any subset or differing set is rejected with 422. SKU and quantity are immutable; re-upload to change them.

## `POST /scenarios/{scenario_id}/suggest`

```json
{"revision":2}
```

Calls the configured LLM. There is no heuristic/fake fallback. Returns HTTP 503/502/504 for configuration/provider/shape failures.

```json
{
  "recommendation_id":"opaque","scenario_id":"opaque","revision":2,"source":"llm","summary":"...",
  "plan":{
    "batches":[{
      "batch_id":"B1","order_ids":["O1","O2"],"transfer_robot_id":"R1","pick_robot_ids":["R1"],
      "execution_order":1,"order_sequence":["O1","O2"],
      "stops":[
        {"sequence":1,"action":"pick","robot_id":"R1","node_id":"...","line_id":"ROW-2","inventory_source_id":"inventory_snapshot:123","bin_id":"DC-01-Z01-B001","quantity":2,"order_ids":[],"donor_robot_id":null},
        {"sequence":2,"action":"transfer","robot_id":"R1","node_id":"CONVEYOR","line_id":null,"inventory_source_id":null,"bin_id":null,"quantity":null,"order_ids":["O1","O2"],"donor_robot_id":null}
      ],
      "rationale":"..."
    }],
    "excluded_orders":[{"order_id":"O3","reason":"..."}]
  },
  "validation":{"valid":true,"errors":[]},"request_provenance":{"attempts":1,"repair_attempted":false}
}
```

Each batch has exactly one robot that performs every pick and the final transfer. That robot must be eligible, have both `pick` and `transfer` capabilities, and have capacity for the cumulative batch payload. Specialist pairs and split-robot handoffs are prohibited, and `donor_robot_id` must always be null. The only actions are all frozen allocation `pick` stops followed by one `transfer` stop. One batch represents one trip that collects assigned orders one by one in `order_sequence` and then transfers once; a singleton uses the same mandatory same-robot pick-then-transfer shape. Independent batches should use distinct feasible resources and run in parallel when possible, but neither four assignments nor any other fixed parallel count is required when infeasible. Receipt has no occupancy or extra service time, so independent transfers may overlap and simultaneous arrivals are allowed. The server rejects invented/omitted IDs or quantities, non-exact frozen line/source/bin/node allocation references, duplicate/overlapping claims, cumulative stock or payload excess, incompatible/blocked resources, unreachable paths, precedence errors, deadline misses, and any order not scheduled or validly excluded. Capacity-feasible exclusions are accepted only when the order provably cannot meet its cut-off even standalone using 7 seconds per frozen allocation pick (including illustrative travel, with no additional travel time) plus 45 seconds transfer. At most one LLM repair is attempted with deterministic validation errors; provenance reports one or two attempts.

## `POST /scenarios/{scenario_id}/compare`

```json
{"revision":2,"recommendation_id":"opaque"}
```

Runs the approved sequence and a fair concurrent singleton baseline from the identical frozen snapshot, complete eligible fleet, geometry, clock, and timing model. For each EDF singleton, the baseline requires one capable dual-capability robot for the full pick-and-transfer trip, then minimizes resource availability time and applies smallest-sufficient deterministic tie-breaks. Consequently, four orders use four distinct dual-capability robots and start concurrently when at least four such robots are initially feasible. There is no specialist-pair fallback.

```json
{
  "scenario_id":"opaque","recommendation_id":"opaque",
  "baseline":{"timeline":[],"orders":[],"metrics":{}},
  "proposed":{"timeline":[],"orders":[],"metrics":{}},
  "difference":{"transfer_service_seconds":0,"overall_completion_seconds":0,"comparable":true,"baseline_excluded_order_count":0,"proposed_excluded_order_count":0,"label":"faster|slower|equal|not_comparable"},
  "assumptions":{"transfer_service":"45 + 22.5 seconds per additional order","picking":"7 seconds per pick stop, including illustrative travel; no additional travel time is added","transfer_phase":"The same dual-capability robot carries the entire batch from its final pick to conveyor receipt","conveyor_receipt":"Point-in-time receipt with no occupancy or separate service stage; simultaneous arrivals are allowed","endpoint":"Transfer end at conveyor receipt"}
}
```

Timeline events contain `event_id`, `batch_id`, `action` (`pick|transfer`), `robot_id`, null `donor_robot_id`, `order_ids`, `line_id`, `quantity`, `node_id`, `path`, `start`, `end`, `carried_kg`, and `state`. Runs also contain `excluded_orders`. Metrics include transfer service seconds, overall completion seconds, deadline misses, transferred quantities, completed/excluded order counts, and utilization for every eligible selected robot.

## `POST /scenarios/{scenario_id}/validate`

For deterministic testing/review of an externally supplied structured plan:

```json
{"revision":2,"plan":{"batches":[],"excluded_orders":[]}}
```

Returns `{"valid":false,"errors":[{"code":"...","path":"...","message":"..."}]}`. This endpoint never stores an invalid plan.