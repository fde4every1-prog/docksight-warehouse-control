# Monthly KPI audit and methodology

## Isolation and reproducibility

The read-only `/api/monthly-kpis` router imports no operational database module.
Original CSV bytes are read, not rewritten. Scenario rows are new in-memory
records and cannot schedule tasks, repair robots or change inventory.

Inspect a deterministic, internally labelled audit manifest offline:

```sh
cd artifacts/api-server
python3 monthly_kpi_sources.py
python3 monthly_kpi_sources.py --include-records > /tmp/monthly-kpi-bundle.json
python3 -m unittest test_monthly_kpis -v
```

The default command prints hashes, exact headers/enums, date ranges, row counts,
archive cardinality, assumptions and generator thresholds. `--include-records`
adds three explicit sections: original source records, assumed baseline records,
and generated scenario records. The CLI writes stdout only; direct any export to
isolated storage, never to source CSVs or operational databases. The scenario
version and SHA-256-based selections make repeated exports deterministic for
unchanged sources. The API never exposes the archive's internal synthetic naming.

## Population selection

The original raw extract contains 3,500 unique orders and 3,500 unique shipments.
Their order IDs match one-to-one. There are 1,567 actual departure timestamps and
1,933 missing departures, not an absence of all departure history. Orders span
August 1 through September 5; departures extend through September 6.

These raw records were chosen because the 8,732 raw task records refer to the
same original order population. The separate uploaded 7,000-order benchmark has
different identities and generated timing assumptions. Blending it with raw
orders or operational replay outcomes would obscure populations and milestones.
The archive remains reference evidence, not carrier or robot execution truth.

Archive audited: `attached_assets/Synthetic_Data_1789961144297.zip`.
Internal members are `synthetic_orders_7000.csv` and
`synthetic_shipments_7000.csv`. Each has 7,000 rows and 7,000 unique order IDs,
with exactly 7,000 matched IDs and zero unmatched IDs. No actual departures are
missing. UTC date ranges:

| Field | Start | End |
|---|---|---|
| Order created_at | 2026-08-01 06:02 | 2026-09-05 17:54 |
| Shipment planned_departure | 2026-08-01 13:02 | 2026-09-06 03:01 |
| Shipment actual_departure | 2026-08-01 13:20 | 2026-09-06 02:40 |

## Exact source fields and classification

- Orders: `order_id,warehouse_id,priority,created_at,carrier_cutoff,oms_status,wms_status,customer_region,service_level`.
- Shipments: `shipment_id,order_id,warehouse_id,tms_status,carrier,planned_departure,actual_departure`.
- Inventory: `warehouse_id,sku,location,wms_qty,erp_qty,vision_qty,reserved_qty,inventory_status,last_cycle_count_days,weight_kg`.
- Robots: `robot_id,warehouse_id,robot_type,vendor,fleet_id,firmware,battery_soc,battery_soh,health_status,payload_kg,safety_cert_status,calibration_status,connectivity`.
- Tasks: `task_id,order_id,warehouse_id,task_type,assigned_robot,wes_status,fleet_status,source_zone,dest_zone,created_at`.

Robot safety enums are `VALID,EXPIRING,EXPIRED`; connectivity is
`ONLINE,INTERMITTENT,OFFLINE`. Connected means ONLINE or INTERMITTENT, because
intermittent connectivity is not disconnected. EXPIRING is not EXPIRED.
All unique nonempty robot IDs remain in the denominator, including conflicting
duplicate identities; unknown states are disclosed, not asserted safe.

Task types are `PICK,MOVE,PACK_FEED,STAGE,REPLENISH`. Every one of the 8,732
source tasks has an assigned robot, providing direct evidence that these types
represent robot work in this extract. Classification uses these types, not a
requirement for assignment, so future unassigned blocked robot work is retained.
An additional type qualifies only with an assigned robot. WES enums are
`QUEUED,ASSIGNED,EXECUTING,COMPLETE,BLOCKED`; fleet enums are
`QUEUED,ASSIGNED,EXECUTING,COMPLETE,FAILED`. The predicate checks BLOCKED or FAILED
in either field and ORs all observations of a task ID, counting each task once.
This measures an intervention proxy, not actual recorded human actions.

## Definitions, unknowns and cohorts

- Cycle time: mean nonnegative actual carrier departure minus matched order
  creation, in hours, by order creation month. No staging-time substitution.
  Exact duplicate identities collapse; conflicting order/shipment identities and
  one-to-many shipment joins are excluded. Audit fields report shipment
  duplicates/conflicts, unmatched orders, invalid durations and future actuals;
  `matched_pair_count` explicitly reports accepted pairs.
- On time: actual departure <= planned departure, divided by all shipments with
  valid actual departure timestamps. Missing planned timestamps remain in the
  denominator as unknown, not classified late. Missing actuals are excluded.
  Cohort uses planned departure month, falling back to actual month if unknown.
- Inventory: exact WMS/ERP/VISION agreement over comparable unique
  warehouse+SKU+location rows. Missing, malformed, nonfinite or negative
  quantities are unknown. Agreement does not prove physical accuracy.
- False availability: expired-connected unique robots / all unique snapshot
  robot IDs. Conflicting duplicate IDs remain denominator-only as unknown.
- Interventions: qualifying unique tasks / all unique robot tasks × 1,000,
  by task creation month. Missing task identities cannot count as unique tasks.

Inventory and robot files have no snapshot timestamps. Their assignment to
August is an explicit illustrative baseline assumption, not measured August
history. Source September-to-date inventory/fleet values are unavailable.

## September scenario versus source-to-date

The dashboard reference cutoff is September 22, 2026 at 23:59:59 UTC.
Offset-free source timestamps are interpreted as UTC. Pure aggregation accepts
an `as_of` argument: future source creation/planned cohorts are excluded, and
future actual departures never count as observed durations or on-time outcomes.
Source coverage is calculated from timestamped records within the warehouse
scope and cutoff; it does not extend the actual extract to the reference date.
The full-month scenario deliberately omits this observation cutoff. Its later
September dates are illustrative, not already observed.

The versioned generator reuses August's valid duration samples at 0.42 times
their original duration, distributes new arrivals across September and assigns
approximately 97% on-time deadlines. It aligns about 98.5% of inventory rows to
WMS, renews about 90% of expired certifications, and assigns roughly 3.5% blocked
task outcomes. Hash selection introduces warehouse-level variation. All card
values are recomputed from these row-level records, not hardcoded targets.
The sample count is not a volume forecast, and improvements are not causal claims.

Changes are September minus August. Rate changes use percentage points.
Relative changes are null when the August baseline is zero or unavailable;
zero denominators yield null values rather than misleading zero performance.