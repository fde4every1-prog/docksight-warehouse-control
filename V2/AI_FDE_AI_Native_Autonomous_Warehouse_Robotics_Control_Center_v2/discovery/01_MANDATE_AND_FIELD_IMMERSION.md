# 01 — Mandate and field immersion

**FDE Operating Model phase:** 1 — Mandate and field immersion  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 01  
**Repo:** Repo 1 brownfield baseline `AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2`  
**Date:** 2026-09-17  
**Mode:** Discovery only. No `src/` changes. No architecture, agent, RAG, or implementation proposal.

**Evidence tag legend**

| Tag | Meaning |
|---|---|
| **EVIDENCED** | Stated in a repo file or counted from repo data |
| **INFERRED** | Reasonable reading of evidence; not explicitly named |
| **UNKNOWN** | Not in the repo; must not be invented |
| **ABSENT** | Searched for and not present in this tree |

---

## 1. Engagement charter

### What we inherited [EVIDENCED]

A fictional, deterministic, locally runnable brownfield simulation of a multinational warehouse and robotics estate. Source: `README.md`, `LICENSE.txt`, `docs/07_v2_audit_and_changelog.md`.

The estate is described as 18 distribution centers across five regions, with automation maturity ranging from legacy AGV sites to highly automated AMR/ASRS facilities. Orders are described as traversing OMS → WMS → WES → WCS/fleet → physical movement → pack/sort → TMS. Source: `docs/01_domain_context.md`, `data/reference/warehouses.csv` (18 rows; regions APAC, EU, LATAM, MEA, NA).

Snapshot scale from `data/manifest.json` (`repo_version` 2.0.0, `generated_at` 2026-09-10, seed 20260910):

| Object | Count |
|---|---|
| warehouses | 18 |
| robots | 712 |
| robot_aliases | 2,136 |
| control_assets | 918 |
| skus | 1,200 |
| inventory_rows | 9,360 |
| orders | 3,500 |
| tasks | 8,732 |
| shipments | 3,500 |
| telemetry_rows | 12,896 |
| vision_observations | 214 |
| safety_events | 1,170 |
| maintenance_records | 520 |
| events | 7,474 |

Systems named in current-state architecture (`docs/03_current_state_architecture.md`, `README.md`): ERP, OMS, WMS, WES, WCS / fleet managers, robots / PLCs / conveyors / ASRS, vision / safety / IoT, CMMS, labor management, TMS, plus a shadow layer of CSV/Excel-like exports, emails, and radio/manual overrides. [EVIDENCED as named systems in docs and data columns. Not EVIDENCED as live external integrations.]

Runnable software in this repo is a small Python package `warehouse_control` with CLI diagnostics, a FastAPI app (`/health`, `/diagnostics`, `/robots/{robot_id}`), CSV + SQLite read paths, a legacy allocator, and a legacy inventory quantity rule. [EVIDENCED: `src/warehouse_control/`]

Physical robot/OT control is disabled. `/health` returns `physical_control: disabled`. [EVIDENCED: `src/warehouse_control/api.py`, `docs/06_security_safety_assurance.md`, `VERIFICATION.md`]

### What “done” means (from `participant/CHALLENGE_BRIEF.md` only) [EVIDENCED]

This engagement is complete for the brief when we have:

1. reconstructed current architecture and systems of record
2. quantified contradictions and hidden dependencies
3. defined canonical domain concepts and invariants
4. improved at least three end-to-end workflows
5. demonstrated resilience under at least two injects
6. implemented evals before any autonomous action
7. shown before/after operational KPIs
8. defined authority boundaries and production-readiness gaps

Items 1–2 and part of 8 belong to discovery (Prompts 01–04). Items 3–7 are later Repo 2 work. They are in scope for the charter and **out of scope for this document’s actions**.

### Out of bounds [EVIDENCED]

- Connecting to real robots, warehouses, safety PLCs, or external services. (`README.md` Safety / scope)
- Treating `restricted_answer_key/` as available. `AGENTS.md` forbids it unless authorized. The directory is **ABSENT** from this V2 tree (`docs/07_v2_audit_and_changelog.md` states it was removed).
- Silently cleaning intentional data contradictions. (`docs/07_v2_audit_and_changelog.md`)
- Autonomous safety-system override, e-stop bypass, safety PLC change, or robot speed-limit change. (`docs/06_security_safety_assurance.md`)
- Inventing a named client sponsor, legal entity, or warehouse that is not in the files. (`AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md`, Prompt 01)

### Named company / named human sponsor [UNKNOWN]

The company is described only as “the fictional company” (`docs/01_domain_context.md`). No legal name, no named executive sponsor, no engagement SOW beyond `participant/CHALLENGE_BRIEF.md`.

---

## 2. Outcome statement

**[EVIDENCED from brief + repo purpose; not a solution choice]**

We have inherited a warehouse estate whose standard flows usually work, but whose exceptions consume disproportionate human effort and create service, safety, and resilience risk, because digital state is not physical state and a robot marked available is not necessarily suitable or optimal. The outcome of this FDE engagement is an evidence-based modernization proposal plus a working proof of capability that reconstructs systems of record, quantifies contradictions, defines canonical concepts, improves at least three workflows, survives at least two injects, places evals before autonomy, shows before/after KPIs, and states who may observe, recommend, approve, and execute — without enabling physical control in this training system.

---

## 3. Sponsor / owner roles

No named people exist in the dataset. Roles below are taken only from files.

| Role | Tag | Evidence | Notes |
|---|---|---|---|
| Floor / ops **supervisor** | **EVIDENCED** | `data/shadow/ops_emails.txt`: “supervisor approved low-speed replenishment for tonight” | Can grant a nightly workaround; CMMS still OPEN; fleet still AVAILABLE |
| **Operator** | **EVIDENCED** | `data/raw/safety_events.csv` `source=OPERATOR`; `data/raw/labor_capacity.csv` `certified_robot_operators` | Safety events also sourced from FLEET, VISION, SAFETY_PLC |
| **Pack staff** | **EVIDENCED** | `labor_capacity.csv` column `pack_staff` | Headcount only; no names |
| **Exception handlers** | **EVIDENCED** | `labor_capacity.csv` column `exception_handlers` | Headcount only |
| **Planned / actual warehouse workers** | **EVIDENCED** | `labor_capacity.csv` `planned_workers`, `actual_workers` | Shift-level labor, not a named owner |
| **Maintenance / CMMS owner** | **INFERRED** | `data/raw/maintenance.csv` work orders; alias source `CMMS`; architecture CMMS ↔ Fleet | No named planner |
| **Safety authority / Safety officer** | **INFERRED** | `docs/06_security_safety_assurance.md`; `safety_events.csv` including `E_STOP`, `ZONE_BREACH`, `SAFETY_PLC`; EVAL-004 | Role is required by constraint text, not named in data |
| **Carrier operations (Carrier-A..D)** | **EVIDENCED** | `data/raw/shipments.csv` `carrier`; email “Carrier-A advanced today's outbound cutoff” | External party; OMS SLA table described as stale until midnight |
| **Customer (region only)** | **EVIDENCED** | `orders.csv` `customer_region` | No customer names |
| **Robotics vendors** | **EVIDENCED** | `data/reference/vendors.csv`; `robots.csv` `vendor`; `warehouses.csv` `fleet_vendor` | FleetOne, RoboFlow, MoveIQ, LegacyAGV |
| **Vision / conveyor / sorter / ASRS / IoT / safety vendors** | **EVIDENCED** | `vendors.csv` VisionCo, ConveyX, SortWorks, RackBot, ColdSense, SafeMotion | Support SLA and remote_access recorded |
| **WMS vendor variants** | **EVIDENCED** | `warehouses.csv` `wms_vendor` = WMS_A / WMS_B / WMS_C / WMS_Legacy | Competing WMS products across DCs |
| **Executive sponsor / product owner** | **UNKNOWN** | Not in repo | Do not invent a name |
| **FDE participant (this engagement)** | **INFERRED** | `participant/CHALLENGE_BRIEF.md`, `AGENTS.md` | Training role; not a warehouse employee record |

---

## 4. Governance RACI draft

Scope of Execute: **digital recommendations and local software only**. Physical robot / PLC / safety-PLC execution is **out of scope** [EVIDENCED].

Canonical loop from the prompt library (discipline, not an implemented system): Observe → Reason → Propose → Decide → Approve → Execute → Observe outcome. The DecisionEngine / Copilot / ActionExecutor named in older libraries are **ABSENT** from this repo.

| Activity | FDE / analyst | Supervisor | Safety authority | Maintenance | Carrier | Legacy software (`warehouse_control`) | LLM / agent |
|---|---|---|---|---|---|---|---|
| **Observe** (read CSV, DB, diagnostics, emails) | R/A | C | C | C | I | R (CLI/API read) | **ABSENT** |
| **Recommend** (later; not this prompt) | R | C | C | C | I | I | **ABSENT / not authorized to write** |
| **Approve** material ops change | C | A/R [EVIDENCED workaround pattern] | A for safety-adjacent [INFERRED] | C | I | — | Must not approve |
| **Approve** safety override / e-stop / speed-limit / safety PLC | — | C | A [EVIDENCED constraint] | C | — | Must refuse | Must not approve |
| **Execute** physical robot / WMS write / motion | — | — | — | — | — | **Disabled** [EVIDENCED] | **Prohibited** [EVIDENCED] |
| **Execute** local analysis code / tests | A/R | I | I | I | I | R | — |

R = Responsible, A = Accountable, C = Consulted, I = Informed.

**Authority evidence already in files**

- Supervisor can approve a low-speed exception while CMMS remains OPEN. [EVIDENCED: shadow email]
- Fleet `AVAILABLE` is not a sufficient approval signal. [EVIDENCED: same email + `maintenance.csv` + EVAL-002]
- Safety-system overrides “require strong external authority and should not be autonomously delegated.” [EVIDENCED: `docs/06_security_safety_assurance.md`]
- EVAL-004 `must_not`: execute or endorse unsafe bypass to meet cutoff. [EVIDENCED]

---

## 5. Stakeholder and affected-groups map

```text
                    [UNKNOWN: executive sponsor]
                              |
         ---------------------------------------------
         |                    |                       |
   DC operations         Maintenance/CMMS         Safety / HRI
   supervisor [E]        [I from WO data]         [I from events/docs]
         |                    |                       |
   operators [E]         robotics vendors [E]     SAFETY_PLC [E]
   pack staff [E]        VisionCo / SafeMotion    OPERATOR reports [E]
   exception handlers[E] ConveyX / RackBot / ...
         |
   WES / Fleet / WMS digital owners [I — systems exist, people unnamed]
         |
   TMS / carriers A–D [E] ---- customer regions NA/EU/APAC/LATAM/MEA [E]
         |
   Physical warehouse workers and pedestrians [I from human_density_profile, ZONE_BREACH, NEAR_MISS]
```

**Affected groups if later automation is wrong** [INFERRED from event types and labor columns, not from a named impact assessment]

- People in zones with `human_density_profile` HIGH and `robot_access` RESTRICTED (`zones.csv`)
- Orders/shipments facing `carrier_cutoff` and DELAYED TMS status
- High-value inventory where camera 18 is untrusted [EVIDENCED: shadow email + `vision_observations.csv` includes `DC-01-CAM-18` with confidence 0.566]
- Robots with EXPIRED safety cert still connected [EVIDENCED: diagnostics 35; `VERIFICATION.md`]

**ISO/IEC 42001 “affected groups” note:** people on the floor and customers of delayed shipments are the affected groups implied by the data. No formal 42001 inventory exists in this repo [ABSENT].

---

## 6. Field-evidence register

Counts below for diagnostics are from `VERIFICATION.md` (release evidence) matching `src/warehouse_control/diagnostics.py` logic. They are **EVIDENCED snapshot figures**, not new measurements from this prompt run.

### 6.1 `data/`

| File | Grain / contents | Question it can answer |
|---|---|---|
| `data/manifest.json` | Snapshot inventory + SHA-256 + counts | What files belong to the deterministic world? What is the official population? |
| `data/warehouse_legacy.db` | SQLite copy used by `repository.query` | What does the legacy DB say for a `robot_id`? Does it match CSV? [join not done in Prompt 01] |
| `data/raw/robots.csv` | One row per robot (712). Type AMR/AGV/TUGGER/CASE_PICKER/FORK_AMR/PALLET_MOVER. Cert EXPIRED/EXPIRING/VALID. Calibration VALID/DUE/OVERDUE. Connectivity ONLINE/INTERMITTENT/OFFLINE | Who is the fleet registry robot? Is cert/calibration/connectivity consistent with “available”? |
| `data/raw/robot_aliases.csv` | robot_id × source WMS/FLEET/CMMS × alias (2,136). Diagnostics: 6 alias collisions | Do WMS, Fleet, and CMMS name the same robot? |
| `data/raw/orders.csv` | 3,500 orders. OMS vs WMS status, priority, carrier_cutoff, service_level | What did OMS vs WMS think, and when is the cutoff? |
| `data/raw/tasks.csv` | 8,732 tasks. `wes_status` vs `fleet_status`. Types PICK/MOVE/PACK_FEED/REPLENISH/STAGE | Do WES and fleet agree on the same task? Which robot is assigned? |
| `data/raw/inventory_snapshot.csv` | 9,360 rows. `wms_qty`, `erp_qty`, `vision_qty`, `reserved_qty` | Do digital books agree with vision? What is reserved? |
| `data/raw/maintenance.csv` | 520 WOs. `cmms_status` vs `fleet_availability`. `safety_release_recorded` | Is a robot in maintenance still marked AVAILABLE? |
| `data/raw/safety_events.csv` | 1,170 events. E_STOP, ZONE_BREACH, NEAR_MISS, MANUAL_OVERRIDE, SPEED_REDUCTION, SCANNER_FAULT | Where did safety events occur and who reported them? |
| `data/raw/shipments.csv` | 3,500. TMS status, carrier, planned vs actual departure | Did the truck leave vs plan? Which carrier? |
| `data/raw/zones.csv` | 216 zones. robot_access YES/RESTRICTED. `map_version`, `physical_change_pending` | Is the map stale vs physical change? Can robots enter? |
| `data/raw/charging_state.csv` | 712. preferred charger, charging_eligible, next_pm_days | Who may charge, on which charger? |
| `data/raw/control_assets.csv` | 918. ASRS, CHARGER, CONVEYOR, DOCK_DOOR, PACK_STATION, SORTER, VISION_GATE. state AVAILABLE/DEGRADED/DOWN | Which plant assets are down/degraded for inject tracing? |
| `data/raw/labor_capacity.csv` | Shift labor vs plan; certified operators; pack; exception handlers | Where is labor short or over plan? |
| `data/raw/events.jsonl` | 7,474 events. Sources OMS 1600, WMS 1600, WES 2500, FLEET 1774. Fields `event_time` and `recorded_time` | Is business sequence the same as recorded time? (clock-skew eval) |
| `data/telemetry/robot_telemetry.csv` | 12,896. `event_time` vs `ingest_time`, battery, speed, localization_confidence | Is telemetry delayed, duplicated, or low-confidence? |
| `data/telemetry/vision_observations.csv` | 214. Includes `DC-01-CAM-18` | What did cameras claim, at what confidence? |
| `data/reference/warehouses.csv` | 18 DCs. timezone, WMS vendor, fleet vendor, warehouse_type, go_live_year | Which site is legacy vs highly automated? Clock domain? |
| `data/reference/vendors.csv` | 10 vendors. support SLA, remote_access | Who supports which subsystem, and how do they connect? |
| `data/reference/skus.csv` | 1,200 synthetic SKUs. UoM, temp, lot/serial/hazmat flags | What item class is being counted? |
| `data/shadow/README.md` | Instruction | Treat shadow files as evidence, not truth |
| `data/shadow/ops_emails.txt` | 4 unofficial directives | What workarounds exist that systems of record missed? |
| `data/shadow/wave_priority_FINAL_v7.csv` | 216 manual priorities. reasons vip_customer, carrier_cutoff, inventory_risk, manager_override | What unofficial wave list is ops actually using? |

**Diagnostic snapshot [EVIDENCED: `VERIFICATION.md`]**

- alias_collisions: 6
- inventory_truth_conflicts: 7,382
- wes_fleet_task_conflicts: 7,351
- maintenance_availability_conflicts: 176
- expired_safety_cert_but_connected: 35
- duplicate_telemetry_packets: 80

### 6.2 `contracts/`

| File | Question it can answer |
|---|---|
| `contracts/fleet_api_v1.yaml` | How did legacy fleet assign work? (`robotId`, POST `/robots/{robotId}/task`, no idempotency key) |
| `contracts/fleet_api_v2.yaml` | Did v2 rename identity? (`vehicle_id`, POST `/missions`) |
| `contracts/order_event_schema.json` | Do order events use `orderId/status` (v1) or `order_id/state/occurred_at` (v2)? |

These are schema stubs, not running vendor APIs. [EVIDENCED: file content; ABSENT as live endpoints]

### 6.3 `scenarios/`

| File | Question it can answer |
|---|---|
| `scenarios/inject_01.md` | What if AS/RS is unavailable? |
| `scenarios/inject_02.md` | What if charging subsystem fails? |
| `scenarios/inject_03.md` | What if dock closes? |
| `scenarios/inject_04.md` | What if vision confidence collapses? |
| `scenarios/inject_05.md` | Duplicate title: vision confidence collapse — **EVIDENCED duplication / weak inject text** |
| `scenarios/inject_06.md` | Duplicate title: dock closure — same note |
| `scenarios/cascade_001.json` | How do cutoff + congestion + charger 3 + conveyor C7 + AMR-044 + inventory mismatch chain? What reasoning is expected? |

Injects are narrative drills. They do not themselves mutate CSV. [INFERRED from file contents being markdown/JSON descriptions]

### 6.4 `evals/` and `tests/`

| File | Question it can answer |
|---|---|
| `evals/README.md` | Which eval dimensions matter (grounding, identity, time, safety, authority, resilience, cost)? |
| `evals/golden_cases.jsonl` | What must the system **not** do (EVAL-001–006)? |
| `tests/test_baseline.py` | Does the snapshot have population and conflicts? Does legacy WMS math work? |
| `tests/test_known_legacy_defects.py` | Which allocator failures are **expected** (xfail): expired cert, payload, congestion? |

Release test result: 3 passed, 3 xfailed. [EVIDENCED: `VERIFICATION.md`]

### 6.5 `src/` (inspect only; not modified)

| File | Question it can answer |
|---|---|
| `src/warehouse_control/api.py` | What is exposed? Is physical control on? |
| `src/warehouse_control/cli.py` | How do we run diagnostics? |
| `src/warehouse_control/diagnostics.py` | Which contradictions are already counted? |
| `src/warehouse_control/repository.py` | CSV vs SQLite access paths |
| `src/warehouse_control/legacy/allocator.py` | What does “available robot” mean in code today? (battery + online; ignores cert, payload, congestion, CMMS) |
| `src/warehouse_control/legacy/inventory.py` | Does software trust WMS blindly? (yes) |
| `src/warehouse_control/core/models.py` | How thin is the domain model? (`RobotState` only) |
| `src/warehouse_control/__init__.py` | Package version string `0.1.0` vs project `2.0.0` — metadata drift [EVIDENCED] |

### 6.6 Supporting repo files (not in the prompt’s folder list, recorded for immersion)

| File | Question it can answer |
|---|---|
| `README.md` | What is this simulation and what are the two core tensions? |
| `AGENTS.md` | What are FDE ground rules and anti-patterns? |
| `participant/CHALLENGE_BRIEF.md` | What is “done”? |
| `participant/DISCOVERY_CHECKLIST.md` | What investigations are still unchecked? (all 11 boxes open) |
| `docs/01`–`07` | Domain, L1–L12, architecture, capabilities, KPI candidates, safety, V2 changelog |
| `.cursor/rules/warehouse-fde.mdc` | Cursor must preserve evidence and never enable physical control |
| `scripts/generate_data.py` | Is new data generated? No — check-only / snapshot already generated |
| `scripts/verify_repo.py` | Structural verification |
| `tools/inspect_repo.py` | File listing helper |
| `VERIFICATION.md`, `checksums.sha256` | Integrity evidence; not a digital signature or certification |
| `Dockerfile`, `Makefile`, `.env.example`, `requirements.txt`, `pyproject.toml` | How to run locally |
| `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` | Discovery-first prompt sequence for this engagement |
| `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15.md` and `_V2.md` | Older maritime-translated libraries — **do not use as systems inventory** |

### 6.7 Searched and ABSENT (do not invent)

| Item | Status |
|---|---|
| `restricted_answer_key/` | ABSENT (removed in V2) |
| `specs/` | ABSENT |
| `TRACEABILITY_MATRIX.md` | ABSENT |
| `DEFINITION_OF_READY.md` / `DEFINITION_OF_DONE.md` | ABSENT |
| Copilot, RAG, digital twin, DecisionEngine, ActionExecutor as running code | ABSENT |
| Named human sponsor, company legal name | UNKNOWN / ABSENT |
| Live fleet / WMS / PLC network endpoints | ABSENT (synthetic/local only) |
| Production credentials | ABSENT (`.env.example` has host/port/log only) |

---

## 7. Responsible AI context

**System class [EVIDENCED]:** Synthetic educational warehouse/robotics training repository. `LICENSE.txt`: “Synthetic training repository. Provided for educational/internal workshop use. No real operational data.”

**Physical / consequential control [EVIDENCED]:** Not connected to real robots, warehouses, safety PLCs, or external services. `VERIFICATION.md`: “External consequential-control integration: disabled / not configured.” API advertises `physical_control: disabled`.

**ISO/IEC 42001 [INFERRED as design discipline only]:** Prompt 01 requires 42001 as a **design discipline**, not a claim that this repo or any future Repo 2 increment is certified. No AIMS, no AI system record, no 42005 impact assessment file is in the tree [ABSENT]. This document does **not** claim certification.

**EU AI Act / high-risk operational AI [INFERRED, not classified in-repo]:** If a later system were connected to robot motion or safety PLCs, it would likely need a high-risk operational treatment. **That connection is not present here.** Do not treat this baseline as a deployed AI system.

**Responsible-AI operating constraints already written down [EVIDENCED]**

- Distinguish digital state, physical evidence, operational interpretation, and decision authority (`AGENTS.md`)
- Safety-critical actions require explicit human authority (`AGENTS.md`, `docs/06`)
- Do not bolt an LLM onto dashboards and call it modernization (`AGENTS.md`)
- Evals before autonomous action (`CHALLENGE_BRIEF.md`, `evals/golden_cases.jsonl`)
- Do not invent physical truth; do not assign expired-cert robots; do not bypass safety to hit cutoff (EVAL-001, 002, 004)

**Data subjects / privacy [EVIDENCED as synthetic]:** SKUs are “Synthetic Product NNNNN”. Countries are `Country-2` style labels. No real PII identified in this immersion.

**Integrity vs certification [EVIDENCED]:** SHA-256 hashes provide reproducibility. `VERIFICATION.md` states the release is not digitally signed and does not claim regulatory certification.

---

## 8. Discovery checklist status after Prompt 01

From `participant/DISCOVERY_CHECKLIST.md`. Prompt 01 **located** evidence; it did **not** complete the investigations (that is Prompt 02–03).

| Item | Status after Prompt 01 |
|---|---|
| Identify competing robot IDs | OPEN — evidence located (`robot_aliases.csv`, 6 collisions) |
| Reconcile WMS/ERP/vision inventory | OPEN — evidence located (7,382 conflicts) |
| WES vs fleet task conflicts | OPEN — evidence located (7,351) |
| Maintenance vs fleet availability | OPEN — evidence located (176) |
| Safety cert and calibration | OPEN — evidence located (35 expired-but-connected; calibration DUE/OVERDUE values exist) |
| Timestamp / event-order defects | OPEN — evidence located (`event_time` vs `recorded_time` / `ingest_time`; 80 duplicate telemetry) |
| Trace one carrier-cutoff risk E2E | OPEN — not traced; files identified (`orders.csv`, shipments, shadow email, cascade_001) |
| Local optimization harming throughput | OPEN — evidence located (`legacy/allocator.py`, three xfail tests) |
| Shadow-process evidence | OPEN — evidence located (`ops_emails.txt`, `wave_priority_FINAL_v7.csv`, zones `physical_change_pending`) |
| Map recovery dependencies | OPEN — injects/cascade located, not mapped |
| Propose bounded autonomy tiers | OPEN — constraints located in `docs/06`; tiers not proposed (Prompt 04/10) |

---

## 9. Explicit non-claims (Prompt 01 stop line)

This document does **not**:

- choose AI vs deterministic (Prompt 04)
- draw a target architecture or C4 to-be
- name three workflows to improve
- implement or modify `src/`
- create synthetic data
- declare modernization complete

**Next prompt:** Prompt 02 — Discover process and architecture (`discovery/02_CURRENT_STATE_PROCESS_AND_ARCHITECTURE.md` and `discovery/02_SYSTEM_OF_RECORD_MATRIX.md`), still with no `src/` changes.
