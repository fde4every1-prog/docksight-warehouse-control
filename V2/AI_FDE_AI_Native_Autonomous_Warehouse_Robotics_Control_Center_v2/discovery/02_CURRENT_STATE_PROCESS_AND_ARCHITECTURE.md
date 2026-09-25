# 02 — Current-state process and architecture

**FDE Operating Model phase:** 2 — Discover process and architecture  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 02  
**Repo:** Repo 1 brownfield baseline  
**Date:** 2026-09-17  
**Mode:** Discovery only. No `src/` changes. No data fixes. No target architecture.

**Depends on:** `discovery/01_MANDATE_AND_FIELD_IMMERSION.md`  
**Companion:** `discovery/02_SYSTEM_OF_RECORD_MATRIX.md`

**Evidence tag legend:** EVIDENCED / INFERRED / UNKNOWN / ABSENT (same as Prompt 01).

Diagnostics in this document were re-run on 2026-09-17 from `warehouse_control.diagnostics.run()` [EVIDENCED]:

| Metric | Count |
|---|---|
| robots | 712 |
| alias_collisions | 6 |
| inventory_truth_conflicts | 7,382 |
| wes_fleet_task_conflicts | 7,351 |
| maintenance_availability_conflicts | 176 |
| expired_safety_cert_but_connected | 35 |
| duplicate_telemetry_packets | 80 |

Additional Prompt 02 counts [EVIDENCED from CSV joins]:

| Metric | Count | Population |
|---|---|---|
| orders where `oms_status` == `wms_status` | 2,217 | 3,500 |
| orders where OMS ≠ WMS | 1,283 | 3,500 |
| tasks where `wes_status` == `fleet_status` | 1,381 | 8,732 |
| SHIPPED/SHIPPED + TMS DEPARTED + all tasks WES=fleet=COMPLETE | **0** | 3,500 |
| SHIPPED/SHIPPED + TMS DEPARTED + WES=fleet (any status) | 19 | 3,500 |
| events with `event_time` ≠ `recorded_time` | 7,448 | 7,474 |
| calibration OVERDUE robots | 45 | 712 |
| unresolved safety events (`resolved=N`) | 209 | 1,170 |
| zones `robot_access=RESTRICTED` | 43 | 216 |
| zones `physical_change_pending=YES` | 27 | 216 |

**Finding that frames this whole phase:** there is no fully consistent happy-path order in the snapshot. The “best” closed order still has a robot in another DC, an open maintenance WO, overdue calibration, and a task stuck in EXECUTING after the truck has left.

---

## A. SIPOC — intended happy path

Described order flow in `docs/01_domain_context.md` and `docs/03_current_state_architecture.md`: OMS → WMS → WES → WCS/fleet → physical movement → pack/sort → TMS.

| | Suppliers | Inputs | Process | Outputs | Customers |
|---|---|---|---|---|---|
| **Order capture** | Customer region (field only); OMS | `orders.csv`: priority, service_level, created_at | OMS RELEASED / ALLOCATED | `order_id`, `carrier_cutoff`, `oms_status` | WMS; later TMS/carrier |
| **Allocate inventory** | ERP qty; WMS qty; vision qty | `inventory_snapshot.csv` | WMS allocation. Legacy code uses **WMS only**: `legacy_available_qty` = wms_qty − reserved_qty | reserved qty; `wms_status` | WES |
| **Create work** | WMS order; zones | `tasks.csv` | WES creates PICK / MOVE / REPLENISH / PACK_FEED / STAGE | `task_id`, `wes_status`, assigned_robot | Fleet / WCS |
| **Assign robot** | Fleet registry; CMMS; safety cert; telemetry | `robots.csv`, aliases, maintenance, charging | **Intended:** suitable robot in the warehouse. **Actual code:** `choose_robot` keeps anyone not `health_status=MAINTENANCE` and not OFFLINE, then scores battery + ONLINE bonus. Ignores cert, payload, congestion, CMMS | robot_id on task | Physical robot |
| **Move / pick / pack** | Robot; conveyors; sorters; pack stations; labor | telemetry, control_assets, labor_capacity, safety_events | Physical movement. **Not executed in this repo** (`physical_control: disabled`) | zone changes; pack completion | TMS |
| **Ship** | Carrier A–D | `shipments.csv` | Book → dock → load → depart | `tms_status`, planned/actual departure | Customer region |

**Shadow SIPOC (parallel, unofficial)** [EVIDENCED: `data/shadow/`]

| Suppliers | Inputs | Process | Outputs | Customers |
|---|---|---|---|---|
| Supervisor / unnamed ops | `ops_emails.txt`, `wave_priority_FINAL_v7.csv` | Manual priority, map workarounds, low-speed overrides | P1/P2/P3 list; Z09 staging; “AVAILABLE” despite open CMMS | Floor; not OMS/WMS |

---

## B. Journey 1 — closest happy path: `ORD-000968`

**Why this ID:** among 3,500 orders, this is a member of the 19 where OMS and WMS both say SHIPPED, TMS is DEPARTED with an actual departure, and the only task has WES status = fleet status. It is the least-broken closed loop. It is **not** clean.

### Named IDs [EVIDENCED]

| Object | ID |
|---|---|
| Order | `ORD-000968` |
| Warehouse (order) | `DC-02` (EU, mixed_robotics, timezone `UTC+5:30`, WMS_C, fleet vendor MoveIQ) |
| Shipment | `SHP-000968` |
| Task | `TSK-000968-1` PACK_FEED |
| Assigned robot | `RBT-0333` |
| Robot home warehouse | `DC-09` (not DC-02) |
| Maintenance | `WO-000251` |
| Events | `EVT-00006783` WES TASK_DISPATCHED; `EVT-00006784` FLEET TASK_STATUS |

### Timeline

| Time | System | What it claims |
|---|---|---|
| 2026-08-31 10:17 | OMS/WMS order row | Created STANDARD / STANDARD service; cutoff 14:17 same day |
| 11:56:38 recorded / 11:57:00 event | WES | Dispatched `TSK-000968-1` to `RBT-0333` |
| 11:57 | WES+Fleet task row | PACK_FEED DC-02-Z03 → DC-02-Z05, both **EXECUTING** |
| 12:11 event / 12:14:44 recorded | Fleet event | TASK_STATUS EXECUTING (ingest ~3.7 min late) |
| 14:17 | TMS planned | Departure = cutoff |
| 14:19 | TMS actual | DEPARTED Carrier-B, 2 minutes after plan |
| Snapshot “now” | OMS + WMS | **SHIPPED** |
| Snapshot “now” | WES + Fleet | Task still **EXECUTING** |
| Snapshot “now” | Robot registry | `RBT-0333` lives at **DC-09**, `health_status=MAINTENANCE`, calibration OVERDUE, battery 94%, ONLINE |
| Snapshot “now” | CMMS | `WO-000251` IN_PROGRESS drive_fault; **fleet_availability=AVAILABLE**; safety_release_recorded=Y |
| Snapshot “now” | Charging | eligible Y, preferred `DC-09-CHARGER-08` |

### What “worked”

- OMS and WMS agree SHIPPED. [EVIDENCED]
- Carrier-B left, only +2 minutes vs plan. [EVIDENCED]
- WES and fleet agree with each other (both EXECUTING). [EVIDENCED]
- Not on the unofficial wave spreadsheet. [EVIDENCED: no shadow row]

### What did not actually work (hidden even on the happy path)

1. **Digital complete ≠ execution complete.** Truck departed; pack-feed task still EXECUTING. [EVIDENCED]
2. **Robot is not at the order’s warehouse.** Task warehouse DC-02; robot warehouse DC-09; fleet_id `DC-09-F1`. [EVIDENCED] Whether this is physically possible or a generator artifact is **UNKNOWN**.
3. **Available ≠ suitable.** Registry says MAINTENANCE; CMMS IN_PROGRESS; fleet column still AVAILABLE; calibration OVERDUE. Legacy allocator would still consider it because `health_status==MAINTENANCE` is the only health filter — wait: `choose_robot` **excludes** `health_status=MAINTENANCE`. So this assignment **violates even the weak legacy filter** unless assignment bypassed `choose_robot`. [EVIDENCED code vs EVIDENCED row]
4. **Clock:** dispatch `recorded_time` is 22 seconds **before** `event_time`. [EVIDENCED] EVAL-003 warns not to trust recorded_time as business sequence.
5. **Vendor mismatch:** DC-02 fleet vendor is MoveIQ; robot vendor is RoboFlow. [EVIDENCED]

**Process implication:** “Shipped” in OMS/WMS/TMS is not a reliable end-to-end completion signal.

---

## C1. Journey 2 — EXCEPTION / cutoff-risk: `ORD-000004`

### Named IDs [EVIDENCED]

| Object | ID |
|---|---|
| Order | `ORD-000004` |
| Warehouse (order) | `DC-16` (NA, highly_automated, UTC+1, WMS_A, FleetOne, go-live 2010) |
| Priority / SLA | CRITICAL / SAME_DAY / customer_region APAC |
| Created | 2026-09-02T20:16:00 |
| Cutoff | 2026-09-03T20:16:00 (24h later despite SAME_DAY — **INFERRED** stale or mismatched SLA table; **UNKNOWN** if intentional) |
| OMS | STAGED |
| WMS | EXCEPTION |
| Shipment | `SHP-000004` Carrier-A, TMS **DELAYED**, planned 2026-09-03T20:16:00, actual_departure empty |
| Task 1 | `TSK-000004-1` MOVE `RBT-0644` WES EXECUTING / fleet **FAILED** DC-16-Z08 → Z08 |
| Task 2 | `TSK-000004-2` REPLENISH `RBT-0506` WES QUEUED / fleet **EXECUTING** DC-16-Z03 → Z06 |
| Events | `EVT-00000719` OMS ORDER_RELEASED; `EVT-00000720` WMS ORDER_ALLOCATED payload already `wms_status=EXCEPTION`; `EVT-00004607` WES dispatched TSK-000004-1 |

### Assigned robots vs order site [EVIDENCED]

| Robot | Registry warehouse | Type | Battery | Health | Cal | Task site |
|---|---|---|---|---|---|---|
| `RBT-0644` | **DC-17** | CASE_PICKER | 10% | DEGRADED | OVERDUE | DC-16 |
| `RBT-0506` | **DC-13** | CASE_PICKER | 53% | HEALTHY | VALID | DC-16 |

`RBT-0644` also has `WO-000010` lidar_calibration IN_PROGRESS, fleet_availability UNAVAILABLE — yet WES still shows EXECUTING.

### DC-16 plant already degraded [EVIDENCED `control_assets.csv`]

DOWN at DC-16: `DC-16-CONVEYOR-05`, `DC-16-CHARGER-08`, `DC-16-PACK_STATION-11`, `DC-16-DOCK_DOOR-04`, `DC-16-VISION_GATE-05`. Labor shift 3: planned 94, actual **47**.

### Carrier-A cutoff context [EVIDENCED]

Shadow email: “Carrier-A advanced today's outbound cutoff by 35 minutes. OMS SLA table will not refresh until midnight.”  
`cascade_001.json` uses the same Carrier-A −35 minutes story.  
This order is Carrier-A + DELAYED + WMS EXCEPTION. It is **not** on `wave_priority_FINAL_v7.csv`.

**Cutoff-risk reading [INFERRED]:** OMS still says STAGED (optimistic). WMS already EXCEPTION. TMS DELAYED with no actual departure. Fleet reports FAILED on the MOVE. A control center that trusted OMS + WES EXECUTING would believe the order is still recoverable; one that trusted WMS + fleet FAILED + DELAYED would escalate. Both views are in the files.

### Related shadow+exception order (not the primary journey)

`ORD-002442` at DC-06: CRITICAL NEXT_DAY, OMS PACKING vs WMS EXCEPTION, Carrier-A DELAYED, **on the shadow sheet as P2 `manager_override`**. Assigned `RBT-0020` (expired cert, INTERMITTENT, CMMS OPEN, fleet AVAILABLE, safety_release **N**). Cited here because it ties unofficial priority to an unsafe robot; full trace is in the working notes, not a fourth required journey.

---

## C2. Journey 3 — robot identity / maintenance / vision disagree: `RBT-0001`

**Why this ID:** only robot in the **intersection** of colliding aliases and CMMS-open-but-fleet-AVAILABLE (6 colliding aliases; 176 maint conflicts; intersection size 1).

### Registry [EVIDENCED `robots.csv` = SQLite `robots` row]

`RBT-0001`, DC-01, AMR, RoboFlow, fleet `DC-01-F2`, firmware 4.8.9, battery 72/SOH 82, HEALTHY, payload 1500 kg, safety_cert **VALID**, calibration VALID, **ONLINE**.

### Competing names [EVIDENCED `robot_aliases.csv`]

| Source | Alias for RBT-0001 | Also used by |
|---|---|---|
| WMS | `BOT-COLLISION-00` | — (same alias also on this robot’s Fleet row) |
| Fleet | `BOT-COLLISION-00` | — |
| CMMS | `BOT-COLLISION-01` | **WMS alias of `RBT-0002`** |

`RBT-0002` is a different machine (TUGGER, DEGRADED). CMMS of RBT-0001 shares the WMS name of RBT-0002. Diagnostics count this family as 6 alias collisions (`BOT-COLLISION-00` … `05`).

### Availability [EVIDENCED]

| System | Claim |
|---|---|
| Robot registry | HEALTHY + ONLINE + VALID cert |
| CMMS `WO-000380` | IN_PROGRESS **lidar_calibration** since 2026-08-08T06:00, warehouse DC-01, **fleet_availability=AVAILABLE**, safety_release_recorded=Y |
| Charging | eligible Y, preferred `DC-01-CHARGER-02` |
| Legacy allocator | would **select** this robot (not MAINTENANCE, not OFFLINE, high battery) |
| Shadow email pattern | “CMMS is still open, but supervisor approved… Fleet shows AVAILABLE” — same pattern, different robot name (AMR-044) |

Safety cert is VALID, so this is **not** the expired-cert case (that is 35 other robots, e.g. `RBT-0020`). Eligibility failure here is **open lidar calibration WO vs HEALTHY/AVAILABLE**.

### Where the robot is claimed to be working [EVIDENCED `tasks.csv`]

Registry warehouse is DC-01, but `RBT-0001` is `assigned_robot` on tasks in **DC-06, DC-09, DC-17, DC-16, DC-02** (examples: `TSK-002899-4` DC-09 PICK QUEUED/QUEUED; `TSK-003149-4` DC-17 PACK_FEED BLOCKED/COMPLETE; `TSK-003163-2` DC-16 PACK_FEED QUEUED/EXECUTING; `TSK-003310-1` DC-02 PICK EXECUTING/EXECUTING).

### Physical-ish observation [EVIDENCED]

`vision_observations.csv`: camera **`DC-01-CAM-18`** observed `RBT-0001` in `DC-01-Z08` at 2026-08-30T06:19:00, confidence **0.566**, class ROBOT.

Shadow email: “Do not trust camera 18. Camera confidence has been poor since lighting retrofit. Physical count wins for high-value SKU family.”

DC-01-Z09 (the unofficial staging zone in the Dock 7 email) exists as STORAGE, robot_access YES, map v9, `physical_change_pending=NO` — the WMS map-not-updated claim is therefore **not visible on the Z09 flag**. Nearby `DC-01-Z01` **does** have `physical_change_pending=YES` (STAGING, map v7, human density HIGH). Sorter evidence: `DC-01-SORTER-03` is **DOWN**. [EVIDENCED] Linking “sorter 2” in the email to SORTER-03 is **INFERRED**, not proven.

### AMR-044 identity gap [UNKNOWN / ABSENT as exact id]

Cascade and email say **AMR-044**. Registry has `RBT-0044` with WMS alias `BOT0044`. No alias equals `AMR-044`. Do not collapse them without a spec.

---

## D. System landscape and competing systems of record

Documented landscape (`docs/03_current_state_architecture.md`) [EVIDENCED as a drawing, not as live systems]:

```text
ERP → OMS → WMS → WES → Fleet Managers / WCS → Robots / PLCs / Conveyors / ASRS
                         ↘ Vision / Safety / IoT
CMMS ↔ Fleet                  ↓
Labor Mgmt                 Physical warehouse
TMS ← staging/ship confirmation
Shadow: CSV/Excel-like exports + emails + radio/manual overrides
```

How those names appear **in this repo** (files, not running vendor products):

| Named system | Repo evidence | Runnable? |
|---|---|---|
| ERP | `inventory_snapshot.erp_qty` | No |
| OMS | `orders.oms_status`; events source OMS | No |
| WMS | `orders.wms_status`; `inventory.wms_qty`; alias source WMS; events source WMS; warehouses.wms_vendor | No |
| WES | `tasks.wes_status`; events source WES | No |
| Fleet / WCS | `tasks.fleet_status`; `robots.*`; alias source FLEET; fleet_api v1/v2 stubs; events source FLEET | No live fleet. Read-only API `/robots/{id}` |
| CMMS | `maintenance.csv`; alias source CMMS | No |
| Vision | `vision_qty`; `vision_observations.csv`; safety source VISION | No |
| Safety PLC | `safety_events.source=SAFETY_PLC` | No |
| TMS | `shipments.csv` | No |
| Labor | `labor_capacity.csv` | No |
| PLC / conveyor / ASRS / charger / dock | `control_assets.csv` | No |
| Shadow ops | `ops_emails.txt`, `wave_priority_FINAL_v7.csv` | Files only |
| **This repo’s app** | FastAPI + CLI + diagnostics + legacy allocator/inventory | Yes, local synthetic |
| Copilot / RAG / digital twin / DecisionEngine / ActionExecutor | — | **ABSENT** |

**Who claims truth (summary; detail in companion matrix)**

| Concept | Claimants | Snapshot verdict |
|---|---|---|
| Robot identity | robots.csv `robot_id`; WMS/FLEET/CMMS aliases; camera `observed_entity`; email “AMR-044” | **Conflict** (6 alias collisions; AMR-044 unmatched) |
| Robot location | `robots.warehouse_id`; `tasks.warehouse_id`; telemetry `zone`; vision `observed_zone` | **Conflict** (cross-DC assignment) |
| Availability | health_status; connectivity; CMMS fleet_availability; charging_eligible; supervisor email | **Conflict** (176 maint; shadow override) |
| Safety eligibility | safety_cert_status; calibration_status; safety_events; EVAL-002/004 | **Conflict** (35 expired-but-connected) |
| Task status | wes_status vs fleet_status; events | **Conflict** (7,351 / 8,732) |
| Inventory qty | wms_qty, erp_qty, vision_qty, reserved; legacy trusts WMS | **Conflict** (7,382 / 9,360) |
| Order status | oms_status vs wms_status | **Conflict** (1,283 / 3,500) |
| Cutoff | orders.carrier_cutoff; shipments.planned_departure; shadow email; cascade | **Conflict** (OMS table described as stale) |
| Zone map | zones.map_version, physical_change_pending; email “WMS map has NOT been updated” | **Conflict** / incomplete |

`docs/03`: “No component has complete warehouse truth.” The three journeys support that statement with named rows.

---

## E. Current-state C4

Only containers that exist in the tree are drawn as live. Missing pieces are labeled ABSENT.

### Context

```text
[Carriers A–D]          [Robotics/vision/conveyor vendors]
        |                            |
        v                            v
[Fictional warehouse estate — 18 DCs, floor people, robots, PLCs]
        ^
        |  synthetic files only; no OT link
[FDE participant / analyst]
        |
        v
[Repo 1 warehouse_control — observe/diagnose only]
        |
        x  ABSENT: Copilot, digital twin, DecisionEngine,
           ActionExecutor, live WMS, live fleet API, safety PLC write
```

### Container (what actually runs)

```text
                    +---------------------------+
                    |  FastAPI warehouse_control |
                    |  GET /health               |
                    |  GET /diagnostics          |
                    |  GET /robots/{robot_id}    |
                    |  physical_control=disabled |
                    +-------------+-------------+
                                  |
           +----------------------+----------------------+
           |                                             |
           v                                             v
+----------------------+                      +----------------------+
| CSV / JSONL / TXT    |                      | SQLite               |
| data/raw, telemetry, |                      | warehouse_legacy.db  |
| shadow, reference    |                      | 8 tables: robots,    |
+----------------------+                      | inventory, orders,   |
           ^                                  | tasks, shipments,    |
           |                                  | maintenance,         |
+----------------------+                      | safety_events,       |
| CLI diagnostics      |--------------------->| control_assets       |
| pytest + evals jsonl |                      +----------------------+
+----------------------+
           |
           |  NOT in DB: aliases, telemetry, vision,
           |  events, zones, charging, labor, shadow, SKUs
           v
     ABSENT write path to robots / WMS / PLC
```

**Contract containers (stubs, not implemented clients):** `contracts/fleet_api_v1.yaml` (`robotId`, no idempotency), `fleet_api_v2.yaml` (`vehicle_id`, `/missions`), `order_event_schema.json` v1 vs v2 field names.

**Software components inside the app [EVIDENCED]**

| Component | Role now |
|---|---|
| `api.py` | Three GET endpoints |
| `cli.py` | `diagnostics` command |
| `diagnostics.py` | Count selected conflicts |
| `repository.py` | CSV DictReader + sqlite query |
| `legacy/allocator.py` | Battery heuristic |
| `legacy/inventory.py` | Trust WMS |
| `core/models.py` | `RobotState` dataclass only |

---

## F. Data flows and trust boundaries

```text
[Untrusted / unofficial]
  ops_emails.txt
  wave_priority_FINAL_v7.csv
  vendor telemetry payloads (not present as live; vision CSV is synthetic)
  future chat/SOP paste (ABSENT now)     }  EVAL later: do not take as Policy

[Operational observations — not authority]
  robot_telemetry.csv   event_time vs ingest_time
  vision_observations.csv  confidence
  safety_events.csv     OPERATOR / VISION / FLEET / SAFETY_PLC
  events.jsonl          event_time vs recorded_time

[Digital systems of record — competing, synthetic extracts]
  robots, aliases, orders, tasks, inventory, maintenance,
  shipments, zones, charging, control_assets, labor, reference/*

[Trust boundary: this machine / this repo]
  All of the above are local files. No network OT.
  API is read-only. .env.example has no secrets.

[Prohibited]
  Physical execute, e-stop, speed change, safety PLC, WMS write
```

**Lineage note [EVIDENCED]:** SQLite counts match CSV for the eight loaded tables (712 robots, 9,360 inventory, etc.). Aliases and telemetry are CSV-only, so `/robots/{id}` **cannot** disclose collisions or CAM-18. Manifest SHA-256 is the integrity story; not a signed production feed.

Everything inside the boundary is **synthetic/read-only**. [EVIDENCED: README, LICENSE, VERIFICATION, api.py]

---

## G. Waste register (Lean)

Cite files, not slogans.

| Waste | Evidence | Effect |
|---|---|---|
| **Defects** | 7,382 inventory disagreements; 7,351 WES/fleet task splits; 1,283 OMS/WMS order splits; 176 false availability vs CMMS; 35 expired-cert still connected; 80 duplicate telemetry; 209 unresolved safety events | Exception handlers exist as a labor column because exceptions are the operating mode |
| **Extra processing** | Three aliases per robot; dual status columns (OMS/WMS, WES/fleet, CMMS/fleet); fleet API v1 `robotId` vs v2 `vehicle_id`; order schema v1 vs v2 | Reconciliation is human work; software does not reconcile |
| **Waiting** | 586 DELAYED shipments; WMS EXCEPTION 976 orders; DC-16 shift 3 actual 47 vs planned 94; charger/dock/conveyor DOWN at DC-16 | Cutoff miss risk (ORD-000004) |
| **Extra motion / local optimization** | `legacy_score` = battery + ONLINE; xfail tests for payload, congestion, expired cert; cascade expects 38 AMRs redirected into congestion | Local “best battery” vs global throughput (`docs/04`, L11) |
| **Unused / mismatched talent** | Certified robot operators vs robots assigned across DCs; exception_handlers 2 on DC-02 shift 2 vs 90 actual workers | People absorb system disagreement |
| **Inventory / overproduction of signals** | Duplicate telemetry packets (example `RBT-0194` 2026-08-12T07:24:00); 7,448/7,474 events with clock disagreement | Noise mistaken for new state |
| **Shadow / workaround (motion of work outside the system)** | Email: Dock 7 pallets to Z09, **WMS map NOT updated**; email: supervisor low-speed while CMMS open; email: do not trust camera 18; email: Carrier-A −35 min, OMS SLA stale until midnight; `wave_priority_FINAL_v7.csv` 216 rows including `ORD-002442` P2 manager_override | Official SoR is not what ops follows |
| **Overprocessing “complete”** | ORD-000968 SHIPPED/DEPARTED while PACK_FEED still EXECUTING | False service-level success |

---

## H. L1–L12 brownfield assessment

At least one evidenced example per layer, or UNKNOWN.

| Layer | Status | Evidenced example |
|---|---|---|
| **L1 Software/Code** | EVIDENCED | `legacy_score` ignores cert/payload/congestion; `legacy_available_qty` trusts WMS; `__init__.py` version 0.1.0 vs project 2.0.0; 3 xfail tests |
| **L2 Robotics/Control** | EVIDENCED | fleet_api v1 vs v2; four fleet vendors; control_assets DOWN (DC-01-SORTER-03, DC-16-CHARGER-08, inject AS/RS / charging / dock) |
| **L3 Data/Telemetry** | EVIDENCED | 80 duplicate packets; 7,448 event_time≠recorded_time; telemetry ingest lag on EVT-00006784 |
| **L4 Asset/Robot** | EVIDENCED | Alias collisions; RBT-0001 vs RBT-0002 name swap; 45 OVERDUE calibration; payload 100–1500 kg unused by allocator |
| **L5 Physical warehouse** | EVIDENCED | 27 zones physical_change_pending; 43 RESTRICTED; Dock 7 / Z09 email vs DC-01-Z09 pending=NO |
| **L6 Inventory/Order** | EVIDENCED | 7,382 qty conflicts (e.g. DC-01 SKU-01146 loc DC-01-Z03-B017 wms 205 / erp 205 / vision 202); 1,283 order status splits |
| **L7 Safety/HRI** | EVIDENCED | 191 E_STOP, 194 ZONE_BREACH, 197 NEAR_MISS; 35 expired cert connected; EVAL-002/004; CAM-18 low confidence |
| **L8 Operations** | EVIDENCED | Shadow emails; FINAL_v7; labor plan vs actual; supervisor override pattern |
| **L9 Enterprise ecosystem** | EVIDENCED | OMS vs WMS vs TMS vs Carrier-A; WMS_A/B/C/Legacy across DCs; ERP qty vs WMS qty |
| **L10 Resilience** | EVIDENCED as drills + assets | inject_01–06; cascade_001; DOWN chargers/docks/conveyors/vision gates. **Not replayed** as a simulator in code [ABSENT] |
| **L11 Decision intelligence** | EVIDENCED | Local battery heuristic; cascade “avoid locally optimal reroute”; no cutoff-aware allocator |
| **L12 Autonomy/safety assurance** | EVIDENCED constraints, ABSENT machinery | physical_control disabled; evals exist as 6 jsonl rows; no DecisionEngine, no autonomy tiers implemented |

Forensic lenses used above: inconsistency (status splits), hidden dependency (cross-DC robot on a closed shipment), uncertainty (vision 0.566), friction (shadow map), complexity (v1/v2 contracts), volatility (Carrier-A cutoff), unknown unknown (AMR-044 ≠ any proven robot_id).

---

## I. Recovery dependency map

What breaks if the named subsystem is wrong. Grounded in injects + journeys + assets.

```text
OMS cutoff wrong or stale
  -> orders.carrier_cutoff and TMS planned_departure look fine
  -> Carrier-A already moved (email, cascade, ORD-000004 DELAYED)
  -> WES may not reprioritize on time
  -> recovery needs a cutoff source other than OMS SLA table

Vision wrong / confidence collapse (inject_04/05, CAM-18)
  -> inventory vision_qty and camera class become unusable
  -> EVAL-001: must not invent physical qty; physical count / cycle_count remain
  -> high-value SKU family per email

Fleet manager wrong or stale after outage (EVAL-005)
  -> tasks.fleet_status and assigned_robot cannot be replayed blindly
  -> 7,351 WES/fleet splits already show divergence before an outage

Charger failure (inject_02; DC-16-CHARGER-08 DOWN; DC-02-CHARGER-07 DOWN)
  -> charging_state.preferred_charger may point at a dead asset
  -> low-battery robots (RBT-0644 soc 10%) cannot recover
  -> cascade: charger 3 fail -> queue grows -> cutoff collapse

AS/RS unavailable (inject_01; ASRS assets exist per DC)
  -> STORAGE/PICK replenishment tasks starve
  -> PACK_FEED (TSK-000968-1) has nothing to feed
  -> no code path models this today [ABSENT]

Dock closure (inject_03/06; DC-16-DOCK_DOOR-04 DOWN)
  -> TMS AT_DOCK / DELAYED cannot clear
  -> SAME_DAY CRITICAL (ORD-000004) has no actual_departure

Sorter / conveyor jam (email sorter 2; DC-01-SORTER-03 DOWN; cascade C7)
  -> unofficial Z09 staging; WMS map not updated
  -> digital locations lie

Identity map wrong (aliases, AMR-044)
  -> maintenance WO and safety cert attach to the wrong machine
  -> recovery actions hit RBT-0002 instead of RBT-0001

Safety PLC / cert
  -> expired-connected robots still in pool (35)
  -> recovery that “uses any ONLINE robot” reintroduces L7 risk
```

**Hidden dependency across journeys:** task.assigned_robot is **not** constrained to order.warehouse_id or robots.warehouse_id. A DC-16 cutoff recovery that “pulls more AMRs” can select DC-17/DC-13/DC-01 identities. That is the cascade’s “38 AMRs redirected” failure mode sitting already in the master data.

---

## Explicit non-claims

This document does not choose AI vs deterministic (Prompt 04), does not define the canonical domain (Prompt 05), and does not change `src/` or CSV. Companion matrix: `discovery/02_SYSTEM_OF_RECORD_MATRIX.md`.

**Next:** Prompt 03 — problem frame, RCA, and computed KPI baselines.
