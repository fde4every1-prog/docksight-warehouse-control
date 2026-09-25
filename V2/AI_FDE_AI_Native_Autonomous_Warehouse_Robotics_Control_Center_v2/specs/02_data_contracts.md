# 02 — Data contracts (retain vs drop)

**Prompt 06.** Binding rules for UC-1 when reading Repo 1 data.  
Implements domain I1–I12 for **records**, not yet code.

**Forbidden:** set `wms_qty = vision_qty`; delete alias collision rows; copy shadow emails into WMS/OMS fields.

---

## 1. Canonical keys (CSV names)

| Entity | Canonical key | Do not rename files to |
|---|---|---|
| Robot | `robot_id` | `robotId`, `vehicle_id` |
| Order | `order_id` | `orderId` |
| Task | `task_id` | — |
| Shipment | `shipment_id` | — |
| InventoryObservation | (`warehouse_id`, `sku`, `location`) | — |
| Alias | (`robot_id`, `source`, `alias`) | — |
| Event | `event_id` | — |
| Time (business) | `event_time` | `recorded_time`, `ingest_time` as sequence |

Adapters may map fleet v1/v2 field names at an API boundary. Stored extracts stay as-is.

---

## 2. RETAIN (conflict is evidence)

A **retain** record must survive any UC-1 pipeline. Downstream may add Conflict/Uncertainty flags; it may not collapse values.

| Record / field set | Retain when | Flag |
|---|---|---|
| Alias rows with colliding `alias` | Always | `IDENTITY_COLLISION` (I9) |
| Unmatched name `AMR-044` | Always unmatched | Uncertainty; do not coerce to `RBT-0044` |
| `wms_qty`, `erp_qty`, `vision_qty` | Always all three | UNCERTAIN if not equal (I3) |
| `reserved_qty`, `inventory_status`, `last_cycle_count_days` | Always | — |
| `oms_status` and `wms_status` | Always both | `ORDER_STATUS` if unequal |
| `wes_status` and `fleet_status` | Always both | `TASK_STATUS` if unequal (I4) |
| `cmms_status` and `fleet_availability` | Always both | `AVAILABILITY` if OPEN/IN_PROGRESS and AVAILABLE (I5) |
| `safety_cert_status` EXPIRED + connectivity not OFFLINE | Always | I1 INELIGIBLE |
| `calibration_status` OVERDUE | Always | I2 |
| Task `warehouse_id` vs Robot `warehouse_id` | Always both | `SITE_MISMATCH` |
| `event_time` **and** `recorded_time` / `ingest_time` | Always both | `CLOCK_SKEW` if unequal (I8) |
| Shadow emails and FINAL_v7 | Always as ShadowDirective | Never Policy/Approval |
| Zone `physical_change_pending` vs email Z09 | Always | `MAP_STALE` |
| Empty `actual_departure` | Always empty | Do not impute depart time |
| SQLite vs CSV | If they ever differ, **keep CSV** as snapshot source | Log lineage |

**Inventory allocate contract:** if UNCERTAIN, return the triple + `uncertain=true`. **Do not** emit a single `available_qty` except as a clearly named `legacy_available_qty` baseline.

---

## 3. DROP or ignore (narrow)

Drop only **duplicate packets** or **non-authoritative copies**, never competing SoR values.

| Item | May drop / ignore | Must keep |
|---|---|---|
| Telemetry duplicate | Extra rows with identical (`robot_id`,`event_time`,`zone`,`battery_soc`,`speed_mps`) after the first | First observation; all non-duplicate rows |
| Byte-identical JSONL event_id | Would drop if duplicate event_id appeared (0 today) | All 7474 unique events |
| SQLite | May ignore as incomplete | Must not prefer DB over CSV for missing tables |
| Fleet API v1/v2 YAML | Ignore as live clients (none exist) | Keep files as drift evidence |
| `legacy_score` output | May ignore for UC-1 decisions | Keep function for before/after |
| Inject markdown | Not rows to load as fact | Keep as scenario fixtures |

**Not droppable:** the 6 colliding aliases, 7,382 inventory disagreements, 7,351 task splits, 176 maint conflicts, 35 expired-connected robots, 7,448 skewed events.

---

## 4. Trust class at read time

| Class | Examples | UC-1 treatment |
|---|---|---|
| Untrusted | ops_emails.txt, FINAL_v7 reasons, vision notes, future chat | Evidence / Conflict only |
| Observation | telemetry, vision_observations, safety_events, events.jsonl | Do not override registry identity or invent qty |
| Competing SoR | robots, orders statuses, tasks dual status, inventory triple, maintenance dual availability | Retain + Conflict |
| Reference | warehouses, vendors, skus | Join keys; timezone not applied blindly |

---

## 5. Write contract (this repo)

| Write | Allowed? |
|---|---|
| OT / robot / WMS / PLC | **Never** (`physical_control` disabled, I10) |
| Mutate `data/` to remove conflicts | **Never** |
| Derived Conflict/Uncertainty/Eligibility in memory or a new derived table | **Yes** (implementation later), as long as sources remain |

---

## 6. Fixture freeze (tests must use)

| ID | Contract check |
|---|---|
| `RBT-0001` aliases vs `RBT-0002` | RETAIN collision |
| `SKU-01146` @ `DC-01-Z03-B017` | RETAIN 205/205/202 |
| `TSK-000968-1` | RETAIN EXECUTING/EXECUTING vs order SHIPPED |
| `TSK-000004-1` | RETAIN EXECUTING vs FAILED |
| `WO-000380` | RETAIN IN_PROGRESS + AVAILABLE |
| `RBT-0194` dup telemetry | DROP extra packet only |
| `ORD-000004` | RETAIN STAGED vs EXCEPTION vs DELAYED |

---

## 7. Definition of Ready addendum

A Prompt 12+ data-touching task is Ready only if it cites **RETAIN or DROP** from this file for each field it reads.
