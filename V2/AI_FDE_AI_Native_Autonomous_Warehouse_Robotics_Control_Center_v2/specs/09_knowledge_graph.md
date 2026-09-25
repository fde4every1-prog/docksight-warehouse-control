# 09 — Overall knowledge-graph mapping (schema, not instances)

**FDE OM:** 9 — Information architecture  
**Date:** 2026-09-18  
**Machine file:** `specs/09_knowledge_graph.json` (`scope: schema`, `instances: false`)  
**Diagrams:** `specs/09_knowledge_graph.mmd`  
**Companions:** domain model, context map, SoR matrix, data contracts, hard gates

This file maps **Repo 2 as types and predicates**. It does not list individual SKUs, robots, orders, or tasks. Those rows stay in `data/` and in the data-contract freeze list. The graph answers the same question for every row: who claimed what, did they agree, what may software do.

Not a Neo4j store, not RAG, not on the DecisionEngine write path. `physical_control` stays disabled.

---

## Overall map (four layers)

```text
L1  Systems of record
    ERP  OMS  WMS  WES  Fleet  CMMS  Vision  TMS  Safety PLC  Shadow
                         | CLAIMS (never “truth because of the name”)
                         v
L2  Bounded contexts and entities
    Identity & asset | Inventory | Fulfillment | Care & safety | Decision | Shadow
                         | ABOUT / HAS / ASSIGNED_TO / LOCATED_AT
                         v
L3  Concepts and interpretation
    11 concepts → Conflict kinds and Uncertainty (retain both sides)
                         | GATES
                         v
L4  Authority
    G1–G8  implement  I1–I12  →  Eligibility  →  ALLOW / DENY / ABSTAIN
                         | MUST_NOT execute
                         v
    Execution stub (applied=false)
```

C4 is containers. The DDD context map is team relationships. This graph is **claim structure**.

**Shared kernel (join keys only):** `warehouse_id`, `robot_id`, `order_id`, `task_id`, `sku`+`location`. There is no shared kernel for quantity, availability, or completeness.

---

## L1 → L3  Who claims which concept

A cell is a `CLAIMS` edge. Competing cells on one row are `DISAGREES_WITH`. Empty means that SoR is silent.

| Concept | ERP | OMS | WMS | WES | Fleet | CMMS | Vision | TMS | PLC | Shadow |
|---|---|---|---|---|---|---|---|---|---|---|
| Robot identity | — | — | alias | — | `robot_id` + alias | alias | observed entity | — | — | floor names |
| Robot site | — | — | — | task warehouse | registry warehouse | WO warehouse | zone only | — | — | — |
| Availability | — | — | — | assigns anyway | AVAILABLE (ACL) | cmms_status | — | — | — | unofficial override |
| Safety / calibration | — | — | — | ignored | cert + connected | release flag ≠ Approval | — | — | events | — |
| Task status | — | — | — | wes_status | fleet_status | — | — | — | — | — |
| Inventory qty | erp_qty | — | wms_qty | — | — | — | vision_qty | — | — | paraphrase |
| Order status | — | oms_status | wms_status | — | — | — | — | DELAYED | — | wave text |
| Cutoff / ship clock | — | carrier_cutoff | — | — | — | — | — | planned/actual | — | stale SLA text |
| Zone map | — | — | pending flags | — | — | — | — | — | restricted unused | workaround text |
| Event clock | — | — | — | — | event_time vs ingest | — | — | — | — | — |
| Plant / charger / dock | — | — | — | — | asset state | asset state | — | — | — | — |

**ACL:** Fleet `AVAILABLE` becomes evidence for Decision, never a boolean `available` on Robot.  
**SEPARATE_WAYS:** WES status and Fleet status stay two fields until a human reconciles.  
**MUST_NOT:** Shadow never becomes Policy or Approval.

---

## L2  Contexts own entity types

| Context | Owns | Does not own |
|---|---|---|
| Identity & asset | Warehouse, Robot, Alias, Vendor, Firmware, SafetyCert, Calibration, Connectivity, ChargingState | Task assignment, quantity |
| Inventory | SKU, Location, InventoryObservation | Order completion |
| Fulfillment | Order, Task, Shipment, CarrierCutoff | Robot eligibility |
| Care & safety | MaintenanceWorkOrder, SafetyEvent, Zone, ControlAsset | Cutoff SLA |
| Decision & authority | Conflict, Uncertainty, Eligibility, Policy, ActionProposal, Decision, Approval, Execution, Outcome | Physical OT |
| Shadow | ShadowDirective | Policy |

### Entity relationship skeleton

```text
Warehouse 1--* Robot, Zone, Order
Robot 1--* Alias, WorkOrder, Telemetry
Robot HAS SafetyCert, Calibration, Connectivity, ChargingState, Vendor, Firmware
Zone 1--* Location
SKU + Location -- InventoryObservation   (three qty fields, never one true_qty)
Order 1--* Task
Order 1--1 Shipment, CarrierCutoff
Task *--0..1 Robot     ASSIGNED_TO (site may conflict)
Eligibility ABOUT Robot + Task + Policy
ActionProposal HAS Eligibility + Conflict + Uncertainty
Decision HAS ActionProposal + Policy
Approval HAS Supervisor | SafetyOfficer
Execution HAS Decision     always applied=false here
```

---

## L3  Concept → conflict / uncertainty

| Concept | Produces | Retain rule |
|---|---|---|
| Robot identity | `IDENTITY_COLLISION` | Keep every alias row; do not merge ids |
| Robot site | `SITE_MISMATCH` | Keep both warehouse_ids |
| Availability | `AVAILABILITY` | Keep cmms_status and fleet_availability |
| Safety | `CERT_EXPIRING` (warn) / G1 fail if EXPIRED | Keep cert + connectivity |
| Task status | `TASK_STATUS` | Keep wes_status and fleet_status |
| Order status | `ORDER_STATUS` | Keep oms_status and wms_status |
| Inventory qty | `INVENTORY_QTY` + Uncertainty | Keep wms_qty, erp_qty, vision_qty |
| Zone map | `MAP_STALE` | Keep pending flag and shadow as untrusted |
| Cutoff | `CUTOFF_STALE` | Prefer structured DELAYED + carrier over OMS-only |
| Event clock | `CLOCK_SKEW` | Order by event_time, keep recorded_time |
| Asset state | Uncertainty / inject | DOWN is evidence, not an OT write |

Illegal nodes: `true_qty`, `canonical_robot_id` that drops aliases, `true_status`, `available=true`.

---

## L4  Gates, invariants, decisions

| Gate | Implements | Typical act |
|---|---|---|
| G1 Safety cert missing/EXPIRED | I1 | DENY assign |
| G2 Open / in-progress CMMS without SafetyOfficer record | I5 | DENY assign |
| G3 Known payload exceeds robot | I12 | DENY assign (unknown payload → G8) |
| G4 Restricted zone or occupancy UNKNOWN | I6 | DENY path/assign |
| G5 Qty fields not all equal | I3 | ABSTAIN allocate-as-known |
| G6 WES ≠ fleet (or order vs still-open task) | I4, I11 | not completable; no blind replay |
| G7 E-stop / speed / zone release / cert waiver | I6, I10 | always DENY in this repo |
| G8 Required evidence UNKNOWN | I9 and catch-all | ABSTAIN |

Calibration OVERDUE is I2 (same INELIGIBLE family as G1/G2).  
Filter-then-score runs **only** on ELIGIBLE robots. `legacy_score` / `legacy_available_qty` / `choose_robot` are **MUST_NOT** edges (named FAIL baseline).

Decision loop in the graph:

`Evidence → Interpretation (Conflict/Uncertainty) → ActionProposal → Decision (ALLOW/DENY/ABSTAIN) → Approval required? → Execution disabled → Outcome`

ALLOW still has `applied=false`.

---

## Code packages (same graph, implementation column)

| Package | Implements |
|---|---|
| `identity/` | Alias resolution; collisions retained |
| `eligibility/` | G1–G4 family + Eligibility |
| `inventory/` | Triple qty → Uncertainty |
| `tasks/` | WES vs fleet reconcile |
| `fulfillment/` | Cutoff / on-time interpretation |
| `decision/` | ALLOW / DENY / ABSTAIN |
| `allocator/` | Filter-then-score |
| `execution/` | Stub; not importable as a live write |
| `legacy/` | FAIL baseline only |

---

## Predicates

| Edge | Meaning | Illegal use |
|---|---|---|
| `CLAIMS` | SoR asserted a concept | Treat as truth |
| `DISAGREES_WITH` | Two SoRs compete | Drop one side |
| `ABOUT` | Concept concerns an entity type | Overwrite the entity |
| `PRODUCES` | Disagreement became Conflict/Uncertainty | Silent merge |
| `GATES` | Hard rule constrains an act | Score bypass |
| `ACL` | Raw field is evidence only | Copy `available` onto Robot |
| `SEPARATE_WAYS` | Two languages stay two | Force COMPLETE |
| `MUST_NOT` | Forbidden product inference | Email as Approval; OT execute |
| `IMPLEMENTS` | Gate is an invariant in code | Narrative override |
| `IMPLEMENTS_IN` | Python package for that type | New SoR |

---

## Files

| File | Role |
|---|---|
| This markdown | Overall mapping |
| `specs/09_knowledge_graph.json` | Schema nodes and edges |
| `specs/09_knowledge_graph.mmd` | Preview diagram |
| `tests/test_knowledge_graph.py` | Schema completeness; no instance ids; OT still off |

Row-level fixtures remain in `specs/02_data_contracts.md` §6. They are tests of RETAIN/DROP, not nodes in this graph.
