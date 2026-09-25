# 06 — Data and knowledge readiness

**FDE Operating Model phase:** 6 — Qualify data and knowledge  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 06  
**Date:** 2026-09-17  
**Mode:** Profile only. **No CSV/SQLite cleaning.** No `src/` changes.

Companions: `discovery/06_DATA_QUALITY_PROFILE.md`, `discovery/06_LINEAGE_AND_PROVENANCE.md`, `specs/02_data_contracts.md`.

**Readiness verdict:** Data is **usable for UC-1** as a synthetic evidence pack. It is **not** a clean system of record. Keys and joins are intact; **values conflict on purpose**. Knowledge in shadow emails is **untrusted**. Do not wait for a new dataset.

---

## Inputs from Prompts 01–05

| This file | Reused from |
|---|---|
| File list and hashes | 01 evidence register; `data/manifest.json` |
| Role of each system | 02 SoR matrix |
| Quality counts | 03 KPI formulas (same methods) |
| Retain disagreement | 04 GO; I3 I4 I9; `AGENTS.md` |
| Entity ↔ file map | `specs/01_domain_model.md` |
| Forbidden | Silently set wms=vision; drop alias collisions; rewrite emails into WMS |

---

## 1. Snapshot identity

| Field | Value | Tag |
|---|---|---|
| `repo_version` | 2.0.0 | EVIDENCED manifest |
| `seed` | 20260910 | EVIDENCED |
| `generated_at` | 2026-09-10 | EVIDENCED; used as PARTIAL as-of in 03 |
| File count | 22 paths in manifest | EVIDENCED |
| Integrity | SHA-256 in manifest + `checksums.sha256`; not a digital signature | EVIDENCED VERIFICATION.md |

`scripts/generate_data.py --check-only` verifies presence; it does **not** regenerate the world.

---

## 2. Catalogue (every manifest file)

Class: **SoR** = digital system extract; **OBS** = sensor/event observation; **REF** = relatively stable reference; **SHADOW** = unofficial; **PACK** = packaged copy (SQLite).

| Path | Grain / PK | Join keys | Freshness fields | Class | UC-1 use |
|---|---|---|---|---|---|
| `data/reference/warehouses.csv` | `warehouse_id` (18) | — | go_live_year | REF | Site, timezone (naive) |
| `data/reference/vendors.csv` | `vendor_id` (10) | `name` ↔ robots.vendor | — | REF | Vendor, SLA, remote_access |
| `data/reference/skus.csv` | `sku` (1200) | inventory.sku | — | REF | Item class |
| `data/raw/robots.csv` | `robot_id` (712) | warehouse_id, vendor | — | SoR (fleet registry) | Canonical Robot |
| `data/raw/robot_aliases.csv` | (`robot_id`,`source`,`alias`) 2136; 3 per robot | robot_id | — | SoR (WMS/FLEET/CMMS names) | I9 collisions |
| `data/raw/orders.csv` | `order_id` (3500) | warehouse_id | created_at, carrier_cutoff | SoR OMS+WMS statuses | Order, Cutoff |
| `data/raw/tasks.csv` | `task_id` (8732) | order_id, assigned_robot, zones | created_at | SoR WES+Fleet | Task I4 |
| `data/raw/shipments.csv` | `shipment_id` (3500); 1:1 order | order_id, carrier | planned_departure, actual_departure (empty 1933) | SoR TMS | DELAYED KPI |
| `data/raw/inventory_snapshot.csv` | (`warehouse_id`,`sku`,`location`) 9360 | sku, warehouse | last_cycle_count_days | SoR WMS+ERP + OBS vision qty | I3 |
| `data/raw/maintenance.csv` | `work_order_id` (520) | robot_id | opened_at | SoR CMMS + fleet_availability | I5 |
| `data/raw/safety_events.csv` | `event_id` (1170) | warehouse_id, zone | event_time | OBS | Safety rate; not Eligibility alone |
| `data/raw/zones.csv` | `zone_id` (216) | warehouse_id | map_version, physical_change_pending | SoR map | I6 RESTRICTED |
| `data/raw/charging_state.csv` | `robot_id` (712, 1:1 robots) | preferred_charger → assets | next_pm_days | SoR | Inject 14; 42 prefer DOWN charger |
| `data/raw/control_assets.csv` | `asset_id` (918) | warehouse_id | — | SoR plant | GS-13–15 |
| `data/raw/labor_capacity.csv` | (`warehouse_id`,`shift`) 54 | warehouse_id | — | SoR labor | Waste; not Eligibility |
| `data/raw/events.jsonl` | `event_id` (7474 unique) | entity_id → order or task | event_time, recorded_time | OBS/SoR mix | I8 |
| `data/telemetry/robot_telemetry.csv` | no business PK; 12896 rows | robot_id, zone | event_time, ingest_time | OBS | I8; 80 dups **droppable** |
| `data/telemetry/vision_observations.csv` | no PK; 214 rows | observed_entity, camera_id | event_time | OBS | Untrusted CAM-18; not identity |
| `data/shadow/README.md` | n/a | — | — | SHADOW | Treat as evidence not truth |
| `data/shadow/ops_emails.txt` | 4 subjects | informal names AMR-044, Z09, camera 18, Carrier-A | “tonight”, “today”, “until midnight” | SHADOW | Untrusted; not Policy |
| `data/shadow/wave_priority_FINAL_v7.csv` | `order_id` (216) | order_id all exist in orders | — | SHADOW structured | Join OK; not OMS priority |
| `data/warehouse_legacy.db` | 8 tables | subset of CSV | — | PACK | `/robots/{id}` only sees this |

**Referential integrity on IDs [EVIDENCED this run]:** 0 orphan tasks→robots/orders, 0 alias/maint/charging/tele/vision orphans, 0 inventory SKU/warehouse orphans, 0 event entity orphans, 0 missing zones on tasks, 0 shadow order_ids missing.  

**Implication:** this brownfield is **semantic** (competing values), not broken keys. UC-1 must not “fix” values to make joins prettier.

---

## 3. What the running app actually reads

| Surface | Reads | Ignores |
|---|---|---|
| `diagnostics.py` | robots, aliases, inventory, tasks, maintenance, telemetry CSVs | orders, shipments, shadow, vision, events, zones, assets, safety, charging, labor, reference |
| `/robots/{id}` | SQLite `robots` only | aliases, CMMS, telemetry |
| `legacy_available_qty` | wms_qty, reserved_qty | erp_qty, vision_qty |
| `legacy_score` | battery, connectivity, health | cert, CMMS, payload, zone |

**Knowledge gap:** even “good” files are unused. Readiness is not only file presence.

---

## 4. Knowledge (non-tabular)

| Knowledge | Permissible use | Not permissible |
|---|---|---|
| EVAL-001–006 `must_not` | Policy seeds | Soften to make demo pass |
| `docs/06` safety constraints | Authority | Autonomous T4 |
| Shadow emails | Conflict/Uncertainty hints | Supervisor waiver, map update, live cutoff Policy |
| FINAL_v7 | Extra priority signal | Overwrite OMS/WMS status |
| Fleet API v1/v2 stubs | Identity field drift | Live dispatch |
| Restricted answer key | ABSENT | — |

Representativeness: synthetic 18 DCs; **not** a real network. Permissible for training proof only (01 §7).

---

## 5. Data-gap register (do not fill by invention)

| Gap | Impact | Treatment |
|---|---|---|
| No task payload_kg | I12 may ABSTAIN | Do not invent payload |
| Timestamps timezone-naive vs warehouses.timezone | Cross-DC order UNKNOWN | Order within one clock field; do not convert |
| AMR-044 ≠ any alias | GS-3 email pattern | Keep unmatched; do not bind to RBT-0044 |
| SQLite missing aliases/telemetry/events/shadow | API blind | UC-1 must read CSV (or load more tables) — implementation later |
| 1933 shipments no actual_departure | On-time PARTIAL | Same as 03 |
| No Approval table | I5 cannot auto-grant | Email ≠ Approval |
| inject_* are markdown | Not applied to rows | Replay as fixtures, do not mutate snapshot |

---

## 6. Readiness for UC-1 / Prompt 12

| Need | Ready? |
|---|---|
| Identity collisions | Yes — aliases CSV, 6 colliding strings |
| Eligibility I1 I2 I5 | Yes — robots + maintenance |
| Inventory I3 | Yes — three qty columns retained |
| Task I4 | Yes — wes_status, fleet_status |
| Cutoff I7 structured | Yes — shipments DELAYED, FINAL_v7, Carrier-A |
| Cutoff from email NLP | Not required (04: optional UC-2) |
| Duplicate telemetry drop | Yes — 80 extras; contract allows drop |
| Clean physical truth | **No — and must not be created** |

**Go to Prompt 07** (evals) with this pack. Do not generate synthetic data.
