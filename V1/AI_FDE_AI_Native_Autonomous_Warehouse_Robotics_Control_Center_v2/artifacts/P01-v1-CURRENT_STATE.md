# P01-v1-CURRENT_STATE

**Prompt:** 01 — Warehouse Brownfield Forensics  
**Artifact:** Current-state reconstruction  
**Baseline frozen:** 2.0.0 (`pyproject.toml`, FastAPI `app.version`, `data/manifest.json`)  
**Scope:** Files in this repository only. No client sponsor, no external zip, no assumed production plant.

---

## 1. What this estate is

This is a **synthetic, locally runnable brownfield simulation** of a multinational warehouse network (18 DCs). ERP, OMS, WMS, WES, WCS/fleet, TMS, CMMS, vision, safety, labor and carrier feeds evolved independently.

Core tensions stated in `README.md` and confirmed in data:

1. **Digital warehouse state ≠ physical warehouse state**
2. **Robot available ≠ robot suitable ≠ robot optimal**

The packaged API declares `physical_control: disabled`. `AGENTS.md` and `.cursor/rules/warehouse-fde.mdc` forbid connecting to real robot controllers.

---

## 2. SDD / contract surfaces inspected

| Surface | Status | Evidence |
|---------|--------|----------|
| `AGENTS.md` | Present | Brownfield rules, 10-step workflow, anti-patterns |
| `README.md` | Present | L1–L12 model, quick start, safety scope |
| `.cursor/rules/warehouse-fde.mdc` | Present | Preserve evidence; eval before behavior change |
| `docs/` (01–07) | Present | Domain, layers, architecture sketch, KPIs, safety, v2 changelog |
| `participant/CHALLENGE_BRIEF.md` | Present | Eight minimum outcomes |
| `specs/` | **Absent** | No directory |
| WRCC SDD contract / WRCC-AC-* files | **Absent** | IDs exist only in the external prompt library, not in this repo |
| `TRACEABILITY_MATRIX.md` | **Absent** | — |
| `DEFINITION_OF_READY.md` / `DEFINITION_OF_DONE.md` | **Absent** | — |
| Copilot / RAG / DecisionEngine / ActionExecutor | **Absent** | No modules, no services |

Inherited version skew (left as evidence, not “fixed”): `src/warehouse_control/__init__.py` is `__version__ = "0.1.0"` while API and pyproject are **2.0.0**.

---

## 3. System-of-systems map (as implemented / as data)

```text
ERP qty ──┐
OMS orders / cutoff ──► WMS qty, bins, wms_status ──► WES task.wes_status
Vision qty / cameras ─┘                              │
Shadow email / Excel ────────────────────────────────┤
                                                     ▼
CMMS work orders ◄──► Fleet availability / fleet_status / robots.csv
                          │
                          ▼
                    Telemetry (zone, battery, clocks)
                          │
WCS / PLC assets (conveyor, ASRS, charger, sorter, dock)
                          │
TMS shipments / planned_departure
                          │
                    Physical warehouse (not a live twin)
```

`docs/03_current_state_architecture.md`: **no component has complete warehouse truth.** That statement matches the files.

There is **no live WarehouseState object**, no context graph, and no simulation loop. “State” is CSV/JSONL snapshots plus a SQLite copy (`data/warehouse_legacy.db`) read by `repository.query`.

---

## 4. Capability map (what Prompt 01 asked to locate)

### 4.1 Warehouse management (WMS)

**PARTIAL.** Not a WMS service. Present as:

- `data/raw/inventory_snapshot.csv` — `wms_qty`, `erp_qty`, `vision_qty`, `reserved_qty`, `location`, `last_cycle_count_days`
- `data/raw/orders.csv` — `wms_status` vs `oms_status`
- `data/raw/zones.csv` — `map_version`, `physical_change_pending`
- Shadow: Dock 7 workaround email (“WMS map has NOT been updated”)

Legacy rule `legacy_available_qty` **trusts WMS only**.

### 4.2 Warehouse execution (WES)

**PARTIAL.** `data/raw/tasks.csv` has `wes_status` and `fleet_status` on the same row. Diagnostics count **7,351** rows where they differ. No WES engine, no wave executor.

### 4.3 Robot fleet / AMR telemetry

**PARTIAL.**

- `data/raw/robots.csv` — 712 robots: type, vendor, `fleet_id`, firmware, battery, payload, `safety_cert_status`, `calibration_status`, `connectivity`
- `data/raw/robot_aliases.csv` — 2,136 aliases across WMS / FLEET / CMMS; diagnostics **6** alias collisions
- `data/telemetry/robot_telemetry.csv` — 12,896 rows: `event_time`, `ingest_time`, `zone`, `battery_soc`, `speed_mps`, `localization_confidence`, `telemetry_quality`
- No pose (x/y/heading), no LIDAR, no path, no tote-on-deck flag
- Duplicate telemetry packets: **80** (diagnostics)

Contracts: `contracts/fleet_api_v1.yaml` (POST task, **no idempotency key**, `robotId`); `contracts/fleet_api_v2.yaml` (POST mission, `vehicle_id`). Neither is implemented behind the FastAPI app.

### 4.4 Zones and keep-outs

**PARTIAL.**

- 216 zones; types include PICK, STORAGE, CHARGE, PACK, HAZMAT, COLD, CROSSDOCK, STAGING
- `robot_access`: YES **173**, RESTRICTED **43** (e.g. `DC-01-Z05`)
- `human_density_profile`: HIGH **71** / MEDIUM **64** / LOW **81**
- `physical_change_pending`: YES **27**
- **No keep-out polygon, no aisle-7 geometry, no occupancy grid**

Allocator XFAIL: ignores `blocked_zone`.

### 4.5 Waves and orders

**PARTIAL.**

- 3,500 orders: `priority`, `carrier_cutoff`, split OMS/WMS status, `service_level`
- No `Wave` table or object
- Shadow `data/shadow/wave_priority_FINAL_v7.csv` — manual P1/P2 reasons (`vip_customer`, `carrier_cutoff`)
- `scenarios/cascade_001.json` — Carrier-A cutoff −35 minutes, 214 priority orders at risk

Example already traced in discovery: `ORD-000003` OMS=`PACKING` vs WMS=`EXCEPTION`.

### 4.6 Inventory and totes

**PARTIAL / FAIL for totes.**

- 9,360 inventory rows; diagnostics **7,382** WMS/ERP/vision disagreements
- Example: `SKU-01146` at `DC-01-Z03-B017` — WMS 205, ERP 205, vision 202
- Vision: 214 observations (`camera_id`, `confidence`, `classification`)
- Email: “Do not trust camera 18”
- **No tote, barcode, or damaged-tote entity**

### 4.7 Charge bays

**PARTIAL.**

- `data/raw/charging_state.csv` — 712 rows: `preferred_charger`, `charging_eligible` (Y 669 / N 43)
- **137** warehouse+charger keys shared by more than one robot; max **11** robots prefer the same charger
- Control assets: **144** `CHARGER` (plus 36 ASRS, 54 SORTER, 180 CONVEYOR, 180 DOCK_DOOR, 216 PACK_STATION, 108 VISION_GATE)
- Inject 02 = charging subsystem failure; cascade includes “charger 3 fails”
- **No bay occupancy lock, no charger reservation object**

### 4.8 Human labor

**PARTIAL.** `data/raw/labor_capacity.csv` — planned vs actual workers, certified robot operators, pack staff, exception handlers. No Supervisor / SafetyOfficer identity model, no approval records.

Shadow: “supervisor approved low-speed replenishment” for AMR-044 while CMMS open and fleet AVAILABLE.

### 4.9 Safety policies

**PARTIAL.**

- Robot `safety_cert_status` / `calibration_status`; **35** expired cert but not OFFLINE
- 1,170 safety events: SPEED_REDUCTION 209, MANUAL_OVERRIDE 200, NEAR_MISS 197, ZONE_BREACH 194, E_STOP 191, SCANNER_FAULT 179; unresolved `resolved=N` **209**
- `docs/06_security_safety_assurance.md` — e-stop, safety PLC, speed-limit changes require external human authority
- **No Policy engine, no keep-out hard gate, no SafetyOfficer role in code**
- Legacy allocator **ignores expired certification** (XFAIL test)

### 4.10 Copilot / RAG

**FAIL.** No copilot, no retrieval router, no SOP store, no chat endpoint. `evals/golden_cases.jsonl` are questions only. Target docs mention RAG as optional, not present.

### 4.11 Simulation / digital twin

**FAIL as a twin.** Dataset is a deterministic snapshot (`data/manifest.json` seed 20260910), not a live digital twin, occupancy simulator, or reconnect journal. `AGENTS.md` says do not make a twin mandatory unless warranted.

### 4.12 AI services

**FAIL as an AI control plane.** Runnable surfaces:

- CLI `python -m warehouse_control.cli diagnostics`
- FastAPI GET `/health`, `/diagnostics`, `/robots/{id}`
- Legacy `choose_robot` / `legacy_available_qty`

No LLM loop, no ActionProposal → Decision → Approval → Execute. Participant overlay (`src/warehouse_control/overlay/`, version **0.1.0**) is a transformation register only; it does not execute warehouse actions.

---

## 5. Code and test baseline

| Item | Finding |
|------|---------|
| Legacy allocator | Battery + ONLINE bonus; skips MAINTENANCE and OFFLINE only |
| Legacy inventory | `wms_qty - reserved_qty` |
| Domain model | `RobotState` dataclass only (`core/models.py`) |
| Diagnostics | Six conflict counters (see VERIFICATION.md) |
| Packaged tests (`VERIFICATION.md`) | 3 passed, 3 xfailed (legacy defects) |
| Workspace tests after overlay freeze tests | 7 passed, 3 xfailed — overlay does not change legacy behavior |
| Physical control | Disabled |

---

## 6. Shadow processes (first-class evidence)

`data/shadow/ops_emails.txt`:

1. Dock 7 → temporary Z09; WMS map not updated  
2. AMR-044 low-speed; CMMS open; fleet AVAILABLE  
3. Camera 18 untrusted; physical count wins for high-value SKU  
4. Carrier-A cutoff −35 min; OMS SLA table stale until midnight  

`wave_priority_FINAL_v7.csv` is a parallel priority list outside OMS/WMS.

---

## 7. Injects present vs WRCC golden pack

Repo injects are one-line disruption prompts, not executable simulators: AS/RS down, charging failure, dock closure (duplicated inject 03/06), vision collapse (duplicated 04/05), plus `cascade_001.json`.

They **do not** enumerate the 15 WRCC golden scenarios (aisle 7, R-12 tote, lost write-ack, prompt injection, etc.). Mapping is in `P01-v1-SDD_GAP_ANALYSIS.md`.

---

## 8. What is true at the end of Prompt 01

- The inherited estate **runs** and is **intentionally inconsistent**.  
- Competing records exist for robot ID, quantity, task status, availability, order status, and cutoff time.  
- There is **no WRCC SDD contract in-tree**, no DecisionEngine, and no write path to robots.  
- Modernization must be an **overlay on frozen 2.0.0**, not a silent rewrite of `legacy/` or of contradictory CSVs.
