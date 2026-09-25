# 01 — DDD Context Map (OM 5)

**FDE OM:** 5 — Model the domain (essential artifact: DDD Context Map)  
**Date:** 2026-09-18  
**Companion:** `specs/01_domain_model.md` §2 (bounded contexts) · `discovery/02_SYSTEM_OF_RECORD_MATRIX.md` (as-is claimants)

This is the **map of relationships**, not a new warehouse. Languages stay different on purpose.

---

## Bounded contexts (from domain model)

Identity & asset · Inventory · Fulfillment · Care & safety · Decision & authority · Shadow

Upstream brownfield systems (Fleet, WMS, ERP, OMS, TMS, CMMS, Vision) are **other teams’ contexts**. We do not own them. We consume extracts.

---

## Map (relationship types)

| Upstream / peer | Downstream | DDD relationship | What crosses the wall | Must not cross |
|---|---|---|---|---|
| Fleet / registry | Identity & asset | **Customer–Supplier** (we are customer of extracts) | `robot_id`, cert, connectivity, payload | “AVAILABLE ⇒ assign” |
| Fleet AVAILABLE | Decision | **Anti-corruption (ACL)** | Raw availability becomes **evidence**, not Eligibility | Boolean `available` on Robot |
| WMS + ERP + Vision | Inventory | **Partnership of conflict** (no winner by name) | Triple qty + `uncertain` | Single `available_qty` |
| OMS | Fulfillment | **Customer–Supplier** | `oms_status`, `carrier_cutoff` | OMS SLA as live on-time |
| TMS | Fulfillment | **Customer–Supplier** (preferred clock when DELAYED) | `tms_status`, planned/actual depart | Invented departure |
| WES vs Fleet task | Fulfillment | **Separate Ways on status** until reconciled | Both statuses + Conflict | Forced COMPLETE |
| CMMS | Care & safety | **Customer–Supplier** | `cmms_status`, `wo_id` | Email waiver |
| Care & safety | Decision | **Conformist to G2/G7** | OPEN WO ⇒ INELIGIBLE | Supervisor text as Approval |
| Shadow (email, FINAL_v7) | Decision | **Anti-corruption** | Conflict / CUTOFF_STALE only | Policy, Eligibility, Execution |
| Vision / CAM-18 | Identity & Inventory | **Open-host service we distrust** | Observation | `robot_id` or qty authority |
| Legacy `choose_robot` | Decision | **Separate Ways** | Named FAIL baseline | Product recommendation |
| Physical OT / PLC | Decision | **Separate Ways** (disabled) | Nothing | POST `/missions`, motion |
| UC-2 Copilot (ABSENT) | Decision | **Published Language later**: ActionProposal text only | Citations of UC-1 JSON | Import of ActionExecutor |

**Shared kernel:** canonical IDs only (`robot_id`, `order_id`, `task_id`, `warehouse_id`, `sku`+`location`). Not a shared “truth qty.”

**Published language of the control tower:** `Eligibility`, `Conflict`, `Uncertainty`, `ALLOW` / `DENY` / `ABSTAIN`, `applied=false`.

---

## Sequence (domain events we already have as files)

Not a new event bus. Existing extracts:

`order created` → `task assigned` → `telemetry` → `safety_event` → `shipment DELAYED` → shadow email.

Business order uses **`event_time`**, not `recorded_time` (I8, `EVT-00006783`).

---

## Ownership

| Context | Owner in this repo | Code |
|---|---|---|
| Identity & asset | UC-1 | `identity/` |
| Inventory | UC-1 | `inventory/` |
| Fulfillment | UC-1 | `tasks/`, `fulfillment/cutoff.py` |
| Care & safety | UC-1 reads CMMS/zones | `eligibility/` G1 G2 G4 |
| Decision & authority | UC-1 | `decision/`, `allocator/filter_score.py` |
| Shadow | Untrusted files | never imported as Policy |
| OT | Out of engagement | `execution/` stub |

---

## What this file is not

A mandate to build Kafka, a **runtime** graph database, or an agent mesh. Integration remains CSV/SQLite + FastAPI GET. An explanatory KG lives in `specs/09_knowledge_graph.md` and is not queried at decide time.
