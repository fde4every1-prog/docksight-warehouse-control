# 01 — Canonical domain model (Repo 2 / UC-1)

**FDE Operating Model phase:** 5 — Model the domain  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 05  
**Date:** 2026-09-17  
**Mode:** Specs only. No `src/` changes. No allocator implementation.

**Scope:** UC-1 deterministic spine (`discovery/04_USE_CASE_AND_AI_SUITABILITY.md`).  
**UC-2 copilot** is optional and is **not** a domain entity that may mutate Robot, Task, or Inventory.

Companion diagrams: `specs/01_domain_model.mmd`  
Ready/done: `specs/DEFINITION_OF_READY.md`, `specs/DEFINITION_OF_DONE.md`  
Trace: `TRACEABILITY_MATRIX.md`

---

## Inputs from Phase 1 (Prompts 01–04)

| This spec section | Reused from |
|---|---|
| Entities and names | Repo 1 files listed in 01 evidence register; 02 SoR matrix columns |
| Frozen examples | 02/03: `RBT-0001`, `RBT-0002`, `ORD-000968`, `ORD-000004`, `SKU-01146` |
| Invariants I1–I8 | 03 RCA + 04 classifications #1–6, #10 |
| Four kinds of “truth” | 01 / `AGENTS.md`: digital state, physical evidence, operational interpretation, decision authority |
| Autonomy | 04 §5 tiers T0–T5; LLM off write path |
| Non-goals | 04: no agent dispatcher, no KG/twin required, no CSV cleaning |
| Thin legacy model | `src/warehouse_control/core/models.py` today is only `RobotState` — this spec **replaces that as the language**, not yet as code |

---

## 1. Ubiquitous language rules

1. A name is canonical only if it appears in Repo 1 or in this spec. Do not import maritime tote / keep-out vocabulary.
2. **Never assume a source is authoritative because of its name** (WMS, Fleet, Vision, ERP, CMMS).
3. Disagreement is a first-class `Conflict`. Do not add a field `true_qty` or `canonical_robot_id` that silently drops other sources.
4. **LLM / Copilot is not a domain entity that mutates** Robot, Task, InventoryObservation, Eligibility, Policy, or Execution.
5. `available` in the legacy dataclass is **not** used. Use `Eligibility` instead of a boolean `available`.
6. Digital state ≠ physical evidence ≠ operational interpretation ≠ decision authority.

---

## 2. Bounded contexts

| Context | Owns | Does not own |
|---|---|---|
| **Identity & asset** | Warehouse, Robot, RobotIdentity/Alias, Vendor, Firmware, SafetyCert, Calibration, Connectivity, ChargingState | Task assignment, inventory qty |
| **Inventory** | SKU, Location, InventoryObservation, inventory Uncertainty | Order completion |
| **Fulfillment** | Order, Task, Shipment, CarrierCutoff | Robot eligibility |
| **Care & safety** | MaintenanceWorkOrder, SafetyEvent, Zone (access/density) | Cutoff SLA |
| **Decision & authority** | Conflict, Uncertainty, Eligibility, ActionProposal, Decision, Approval, Execution, Outcome, Policy, Supervisor, SafetyOfficer | Physical OT |
| **Shadow** | ShadowDirective (email / FINAL_v7) | Policy (untrusted input only) |

Cross-context integration is via IDs (`robot_id`, `order_id`, `task_id`, `sku`+`location`) and `Conflict` records — not by overwriting the other context’s fields.

---

## 3. Entity catalogue

Each entity: meaning, identity, source in Repo 1, notes.

### 3.1 Warehouse

| | |
|---|---|
| Meaning | One of 18 distribution centers |
| Identity | `warehouse_id` (e.g. `DC-01`) |
| Source | `data/reference/warehouses.csv` |
| Attributes | region, country, warehouse_type, timezone (naive event times — **UNKNOWN** if local or UTC), wms_vendor, fleet_vendor, go_live_year |
| Invariant | A Task’s `warehouse_id` may **disagree** with the assigned Robot’s `warehouse_id` (02: 94.4% of tasks). That disagreement is a Conflict, not silently “the robot moved.” |

### 3.2 Robot

| | |
|---|---|
| Meaning | Registry machine (AMR, AGV, TUGGER, CASE_PICKER, FORK_AMR, PALLET_MOVER) |
| Identity | `robot_id` (e.g. `RBT-0001`) — **canonical registry key** |
| Source | `data/raw/robots.csv` / SQLite `robots` |
| Attributes | warehouse_id, robot_type, vendor, fleet_id, firmware, battery_soc, battery_soh, health_status, payload_kg, safety_cert_status, calibration_status, connectivity |
| Forbidden | Boolean `available`. Derive `Eligibility`. |
| Example | `RBT-0001` HEALTHY + VALID cert + ONLINE **and** open lidar WO → not eligible |

### 3.3 RobotIdentity / Alias

| | |
|---|---|
| Meaning | A name some system uses for a robot |
| Identity | (`robot_id`, `source`, `alias`) |
| Source | `data/raw/robot_aliases.csv`; sources WMS, FLEET, CMMS |
| Invariant | If the same `alias` maps to more than one `robot_id`, emit Conflict `IDENTITY_COLLISION`. **Do not merge.** |
| Example | `BOT-COLLISION-01` is CMMS of `RBT-0001` and WMS of `RBT-0002` |
| Unmatched floor names | `AMR-044` in email/cascade is **not** proven equal to `RBT-0044` |

### 3.4 Vendor, Firmware

Vendor: `data/reference/vendors.csv` (`vendor_id`, name, type, support_sla_hours, remote_access).  
Firmware: string on Robot (`firmware`). Not a separate file. Drift between sites is L2 evidence, not a mutation API.

### 3.5 SafetyCert, Calibration, Connectivity

Value objects on Robot (not separate tables today):

| Object | Values in snapshot | Eligibility effect |
|---|---|---|
| SafetyCert | VALID, EXPIRING, EXPIRED | EXPIRED ⇒ **ineligible** (I1). EXPIRING ⇒ eligible but Conflict `CERT_EXPIRING` |
| Calibration | VALID, DUE, OVERDUE | OVERDUE ⇒ **ineligible** (I2) |
| Connectivity | ONLINE, INTERMITTENT, OFFLINE | OFFLINE ⇒ **ineligible**. INTERMITTENT ⇒ eligible only with Uncertainty |

### 3.6 Zone, Location

| | Zone | Location |
|---|---|---|
| Identity | `zone_id` e.g. `DC-01-Z09` | e.g. `DC-01-Z03-B017` |
| Source | `data/raw/zones.csv` | `inventory_snapshot.location` |
| Attributes | zone_type, robot_access YES/RESTRICTED, human_density_profile, map_version, physical_change_pending | warehouse + zone + bin |
| Invariant | `robot_access=RESTRICTED` ⇒ path/assign into zone is ineligible unless SafetyOfficer Approval (I6). UNKNOWN occupancy ⇒ refuse (fail-safe). |
| Shadow | Email “Z09 staging, WMS map not updated” vs `DC-01-Z09` pending=NO → Conflict `MAP_STALE` |

There is **no** KeepOutPolygon entity in this repo. Do not invent one.

### 3.7 SKU

Identity `sku`. Source `data/reference/skus.csv`. Attributes: description, uom, temperature_class, lot_controlled, serial_controlled, hazmat.  
Physical “true count” is **not** an attribute of SKU.

### 3.8 InventoryObservation

| | |
|---|---|
| Meaning | One digital/physical-ish reading of quantity at a location |
| Identity | (`warehouse_id`, `sku`, `location`) grain in snapshot |
| Source | `data/raw/inventory_snapshot.csv` |
| **Retained fields** | `wms_qty`, `erp_qty`, `vision_qty`, `reserved_qty`, `inventory_status`, `last_cycle_count_days` |
| Forbidden | A single `true_qty` or “winning” source |
| Uncertainty | If not all of wms/erp/vision equal → `Uncertainty` UNCERTAIN; **do not allocate as known** (I3) |
| Example | `DC-01` `SKU-01146` `DC-01-Z03-B017` 205 / 205 / 202 |

Legacy `legacy_available_qty` (WMS − reserved) is **non-canonical**. It may remain as a named legacy function for before/after only.

### 3.9 Order

Identity `order_id`. Source `data/raw/orders.csv`.  
Attributes: warehouse_id, priority, created_at, carrier_cutoff, **oms_status**, **wms_status**, customer_region, service_level.  
Invariant: OMS ≠ WMS ⇒ Conflict `ORDER_STATUS`; order is not digitally complete.

### 3.10 Task

Identity `task_id`. Source `data/raw/tasks.csv`.  
Attributes: order_id, warehouse_id, task_type (PICK, MOVE, PACK_FEED, REPLENISH, STAGE), assigned_robot, **wes_status**, **fleet_status**, source_zone, dest_zone, created_at.  
Invariant: wes_status ≠ fleet_status ⇒ Conflict `TASK_STATUS`; task/order **must not be treated COMPLETE** (I4).  
Example: `TSK-000968-1` both EXECUTING while order SHIPPED; `TSK-000004-1` WES EXECUTING vs fleet FAILED.

### 3.11 Shipment

Identity `shipment_id`. Source `data/raw/shipments.csv`.  
Attributes: order_id, warehouse_id, tms_status, carrier, planned_departure, actual_departure.  
`tms_status=DELAYED` is cutoff-risk evidence (headline KPI 16.7%).

### 3.12 CarrierCutoff

Value object: planned leave time used for service risk.

| Claimant | Field |
|---|---|
| OMS/order | `orders.carrier_cutoff` |
| TMS | `shipments.planned_departure` (often equal in snapshot) |
| Shadow | email Carrier-A −35 min; FINAL_v7 `reason=carrier_cutoff` |

Invariant: do not treat OMS cutoff as live if a ShadowDirective says SLA is stale (I7). Structured TMS DELAYED + carrier still win over LLM paraphrase of the email.

### 3.13 MaintenanceWorkOrder

Identity `work_order_id`. Source `data/raw/maintenance.csv`.  
Attributes: robot_id, warehouse_id, cmms_status, fleet_availability, issue, opened_at, safety_release_recorded.  
Invariant: `cmms_status ∈ {OPEN, IN_PROGRESS}` ⇒ robot **not** AVAILABLE for assign (I5), even if `fleet_availability=AVAILABLE`.  
`safety_release_recorded=Y` is **not** Supervisor/SafetyOfficer Approval. Shadow “supervisor approved tonight” is ShadowDirective, not Approval.

### 3.14 SafetyEvent

Identity `event_id`. Source `data/raw/safety_events.csv`.  
Types: E_STOP, ZONE_BREACH, NEAR_MISS, MANUAL_OVERRIDE, SPEED_REDUCTION, SCANNER_FAULT.  
Sources: OPERATOR, FLEET, SAFETY_PLC, VISION.  
Does not by itself mutate Eligibility; unresolved E_STOP / ZONE_BREACH in a zone raises Uncertainty / Conflict for that zone.

### 3.15 TelemetryObservation

Source `data/telemetry/robot_telemetry.csv`.  
Clock: `event_time` is business time; `ingest_time` is recorded/ingest. Order by `event_time` (I8). Duplicate key (robot_id, event_time, zone, battery_soc, speed_mps) may be dropped as duplicate packet (Prompt 06 will detail); do not treat dup as a new pose.

Vision observation (camera_id, observed_entity, confidence) is **physical evidence**, not identity authority. `DC-01-CAM-18` is untrusted per ShadowDirective.

### 3.16 ChargingState

Source `data/raw/charging_state.csv`. preferred_charger, charging_eligible, soc/soh, next_pm_days.  
If preferred charger asset is DOWN (`control_assets`) ⇒ Uncertainty / inject path; do not assume charge.

### 3.17 ControlAsset (needed for injects; implied by Repo 1)

Not in the prompt’s minimum list but required for golden 12–15.  
Identity `asset_id`. Types ASRS, CHARGER, CONVEYOR, DOCK_DOOR, PACK_STATION, SORTER, VISION_GATE. States AVAILABLE, DEGRADED, DOWN.  
DOWN charger/dock/ASRS/sorter feeds Eligibility and inject replay — still no OT execute.

### 3.18 ShadowDirective

Unofficial ops instruction. Sources: `ops_emails.txt`, `wave_priority_FINAL_v7.csv`.  
**Untrusted.** May create Conflict / Uncertainty. Must **not** become Policy or Approval.  
FINAL_v7 is structured (join `order_id`). Emails are unstructured (UC-2 optional).

### 3.19 Conflict

A recorded disagreement between claimants for one concept.  
Kinds: `IDENTITY_COLLISION`, `SITE_MISMATCH`, `TASK_STATUS`, `ORDER_STATUS`, `INVENTORY_QTY`, `AVAILABILITY`, `MAP_STALE`, `CUTOFF_STALE`, `CLOCK_SKEW`.  
Must retain **both** observations.

### 3.20 Uncertainty

Explicit “we do not know physical truth.”  
Legal outputs: abstain; mark UNCERTAIN; require human. Illegal: invent qty, pick a source by system name.

### 3.21 Eligibility

Deterministic result for “may this robot be assigned this task?”  
`ELIGIBLE` | `INELIGIBLE` | `ABSTAIN`.  
Computed from gates I1, I2, I5, I6, connectivity, payload when known, site Conflict.  
**Not** `legacy_score`. Score may rank only ELIGIBLE robots.

### 3.22 Decision loop (observe → … → outcome)

| Entity | Meaning | Who produces it |
|---|---|---|
| **Policy** | Versioned rules (this spec’s invariants). Not email text. | Spec / code |
| **ActionProposal** | Recommended action + evidence list + conflicts + uncertainty. Never a robot command. | Deterministic UC-1; optional UC-2 text wrapper |
| **Decision** | Apply Policy to proposal: ALLOW / DENY / ABSTAIN | Deterministic DecisionEngine (**to-build**; ABSENT in Repo 1) |
| **Approval** | Human grant with role, expiry, single-use. Required for T3/T4. | Supervisor or SafetyOfficer |
| **Execution** | Application of a Decision to a write path | **Always disabled** for OT in this repo (`physical_control: disabled`) |
| **Outcome** | Observed result after decision (and never-executed OT) | Diagnostics / evals |

### 3.23 Supervisor, SafetyOfficer

Roles, not rows in a user table (UNKNOWN names).  
Supervisor: T3 material ops (wave, using FINAL_v7 as **input not authority**).  
SafetyOfficer: T4 e-stop, speed, zone release, cert waiver.  
Neither may be impersonated by an LLM.

### 3.24 Explicitly not entities

| Name | Why |
|---|---|
| LLM, Copilot, Agent | Assistance only; no mutate |
| Tote, KeepOutPolygon, Wave (as maritime object) | Not in Repo 1 |
| Digital twin | ABSENT; not required |
| `RobotState.available` | Replaced by Eligibility |

---

## 4. Invariants (acceptance criteria)

These are **Policy**. Implementation (Prompt 12+) must test them. Legacy code may remain as a named baseline path.

| ID | Invariant | Fixture / eval |
|---|---|---|
| **I1** | SafetyCert EXPIRED ⇒ Eligibility INELIGIBLE. Must not assign. | EVAL-002; 35 expired-connected |
| **I2** | Calibration OVERDUE ⇒ INELIGIBLE | `RBT-0333`, `RBT-0644` |
| **I3** | InventoryObservation with disagreeing wms/erp/vision ⇒ Uncertainty; **do not allocate as known**; do not invent a qty | EVAL-001, EVAL-006; `SKU-01146` |
| **I4** | Task wes_status ≠ fleet_status ⇒ Conflict; must **not** treat task or parent Order as COMPLETE | `TSK-000968-1`, `TSK-000004-1` |
| **I5** | MaintenanceWorkOrder OPEN or IN_PROGRESS ⇒ robot not AVAILABLE for assign, even if fleet_availability=AVAILABLE | `WO-000380` / `RBT-0001`; EVAL-002 pattern |
| **I6** | Zone robot_access=RESTRICTED or occupancy UNKNOWN ⇒ refuse path/assign. Safety-zone release is T4 only. Cutoff pressure does not override. | EVAL-004; 43 RESTRICTED zones |
| **I7** | CarrierCutoff: do not treat OMS SLA as live when ShadowDirective or TMS DELAYED contradicts it. Prefer structured DELAYED + carrier. Email is not Policy. | `ORD-000004`; GS-11 |
| **I8** | Order events by `event_time`, not `recorded_time` / `ingest_time` | EVAL-003; EVT-00006783 |
| **I9** | Identity: do not silently overwrite `robot_id` from alias, vision, or LLM. Collisions retained as Conflict. | `BOT-COLLISION-*`; GS-1 |
| **I10** | Execution of motion, e-stop, speed change, WMS write is **disabled**. Decision may still be DENY/ABSTAIN. | `/health`; 04 T5 |
| **I11** | Lost/stale fleet queue after outage: do not blindly replay all tasks | EVAL-005 |
| **I12** | Payload: if task payload known and robot.payload_kg < task ⇒ INELIGIBLE | xfail payload test; may ABSTAIN if task payload ABSENT |

`legacy_score` (battery + ONLINE) is **non-compliant** with I1, I5, I6, I12.

---

## 5. Relationships (summary)

```text
Warehouse 1--* Robot
Robot 1--* Alias
Robot 1--* MaintenanceWorkOrder
Robot 1--* TelemetryObservation
Robot 1--* ChargingState
Warehouse 1--* Zone 1--* Location
SKU + Location -- InventoryObservation
Order *--1 Warehouse
Order 1--* Task
Order 1--1 Shipment
Order 1--1 CarrierCutoff
Task *--0..1 Robot (assigned_robot; may Conflict on site)
Task *--1 Order
ShadowDirective *--0..1 Order / Robot / Zone  (untrusted)
Conflict *-- concept + claimants
Eligibility -- Robot + Task + Policy
ActionProposal -- Eligibility + Conflicts + Uncertainty
Decision -- ActionProposal + Policy
Approval -- Decision + Supervisor|SafetyOfficer
Execution -- Decision  (OT always disabled here)
```

See `specs/01_domain_model.mmd` for Mermaid.

---

## 6. Three workflows (language only)

| Workflow | Canonical objects | Success language |
|---|---|---|
| Assign / eligibility | Robot, Alias, Eligibility, MaintenanceWorkOrder, SafetyCert, Task | INELIGIBLE or ELIGIBLE+score; never “available=true” |
| Inventory / pick truth | InventoryObservation, Uncertainty, SKU, Location | UNCERTAIN retained; no invented qty |
| Cutoff / ship | Order, Shipment, CarrierCutoff, Task, Conflict I4/I7 | DELAYED/conflict visible; no false COMPLETE |

---

## 7. What Prompt 05 does *not* do

- No changes under `src/`
- No data contracts (Prompt 06)
- No eval harness expansion (Prompt 07)
- No ADR (Prompt 08)
- No C4 to-be (Prompt 09)

**Next:** Prompt 06 — data/knowledge qualification and `specs/02_data_contracts.md`.
