# 03 — Problem frame, root cause, and baseline KPIs

**FDE Operating Model phase:** 3 — Frame problem, root cause and value  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 03  
**Date:** 2026-09-17  
**Mode:** Discovery only. Read-only queries. No `src/` changes. No CSV cleaning. No technology choice.

**As-of clock used for cutoff proxies:** `data/manifest.json` `generated_at` = **2026-09-10**. Timestamps in files have **no timezone**. Treat cutoff “past as-of” as **PARTIAL**.

---

## Inputs from Prompts 01 and 02 (what this artifact reused)

Prompt 03 is not a blank-sheet KPI exercise. Every section below is fed by a prior discovery artifact plus a fresh compute. Without 01/02, the SCQA would be generic and the KPI denominators would be undefined.

| Prompt 03 section | Prompt 01 input used | Prompt 02 input used | Fresh compute / repo file |
|---|---|---|---|
| Evidence tags, out-of-scope, synthetic/no physical control | Charter, RACI, Responsible AI (§1, §4, §7) | — | `docs/06`, `api.py` |
| SCQA Situation (“standard flows usually work”) | Challenge-brief wording in 01 charter | Finding: **0** fully consistent closed orders; SIPOC happy path vs actual | 19 SHIPPED+DEPARTED+WES=fleet (any status) |
| SCQA Complication (counts + emails) | Field-evidence register; diagnostic snapshot | Journeys `ORD-000968`, `ORD-000004`, `RBT-0001`; waste register; SoR matrix | Re-run rates below |
| SCQA Question / Answer | Two tensions from 01 (`digital ≠ physical`, `available ≠ suitable`) | “No component has complete warehouse truth”; competing SoR grid | — |
| RCA — identity fragmentation | Checklist item “competing robot IDs”; alias file listed | Journey 3 `RBT-0001` / `BOT-COLLISION-00/01` vs `RBT-0002`; AMR-044 unmatched | 6 colliding strings, 4 robots |
| RCA — competing SoR | Named systems ERP/OMS/WMS/WES/Fleet/CMMS/Vision/TMS | Full matrix + C4 (API ignores aliases/CMMS/vision) | OMS≠WMS 1,283; WES≠fleet 7,351 |
| RCA — stale/shadow | Shadow emails in evidence register | Waste register; `ORD-002442` P2 manager_override; Z09 vs pending flags | 216 unofficial wave rows |
| RCA — `legacy_score()` | L11 in 01 L1–L12 list | Allocator vs assigned `RBT-0333` (MAINTENANCE but assigned) | xfail tests; 8,247/8,732 cross-warehouse assignments |
| RCA — missing eligibility gates | EVAL-002/004 in 01; safety RACI | RBT-0001 open lidar WO + HEALTHY; RBT-0020 expired; RBT-0644 10% battery | Union false-available **203/712** |
| RCA — temporal/ingest | EVAL-003; telemetry files listed | 7,448/7,474 event_time≠recorded_time; dispatch recorded before event on `EVT-00006783` | 80 duplicate packets |
| KPI false availability | Diagnostics 35 + 176 in 01 | Availability SoR table | Union + allocator-pool rates |
| KPI inventory / task / OMS-WMS / dups | Diagnostics in 01 | Prompt 02 additional counts | Confirmed + WMS≠ERP 4,601; WMS≠vision 5,415 |
| KPI cutoff-risk | Carrier-A email in 01 | Journey `ORD-000004` + cascade note | DELAYED 586; as-of proxy 2,941 (**PARTIAL**) |
| CTQs / counter-metrics | Safety must-nots; KPI candidate list `docs/05` | EVAL alignment in matrix | — |
| Value hypothesis / 3 workflows | Challenge-brief 8 outcomes | SIPOC stages: assign, allocate, ship/cutoff | — |
| Checklist CLOSED/OPEN | 01 left all 11 OPEN (located only) | 02 closed identify/find/trace/map | This prompt ranks them |

Frozen IDs carried forward from 02 (do not replace): `ORD-000968`, `ORD-000004`, `RBT-0001`, extra `ORD-002442`.

---

## 1. SCQA

### Situation [EVIDENCED]

The estate can close some orders on paper. OMS and WMS agree on **2,217 / 3,500** orders. **559** shipments are TMS `DEPARTED`. **1,381 / 8,732** tasks have matching WES and fleet status. The intended chain OMS → WMS → WES → fleet → pack → TMS is documented and the local app runs (`/health` ok, physical control disabled).

The brief’s phrase “standard flows usually work” is **only partly true in this snapshot**. There are **zero** orders that are OMS+WMS `SHIPPED`, TMS `DEPARTED` with an actual time, **and** all tasks `COMPLETE` on both WES and fleet. The closest success, `ORD-000968`, is already departed while pack-feed `TSK-000968-1` is still `EXECUTING` on a DC-09 robot assigned to a DC-02 order.

### Complication [EVIDENCED]

Exceptions are not the tail. They are the mass:

- **7,382 / 9,360 (78.9%)** inventory rows: WMS, ERP, and vision qty are not identical
- **7,351 / 8,732 (84.2%)** tasks: WES status ≠ fleet status; fleet `FAILED` = 1,788
- **1,283 / 3,500 (36.7%)** orders: OMS status ≠ WMS status; WMS `EXCEPTION` = **976 (27.9%)**
- **176** work orders open/in progress while fleet still `AVAILABLE`; **35** robots with `EXPIRED` cert still not `OFFLINE`
- **203 / 712 (28.5%)** robots are in the union “expired-and-connected **or** open-CMMS-but-AVAILABLE”
- **586 / 3,500 (16.7%)** shipments `DELAYED`; Carrier-A accounts for **151** of those
- Shadow ops: four emails (unupdated WMS map, supervisor override vs open CMMS, untrusted camera 18, Carrier-A −35 min with stale OMS SLA) plus **216** rows in `wave_priority_FINAL_v7.csv`
- Safety: **1,170** events including 191 E_STOP, 194 ZONE_BREACH, 200 MANUAL_OVERRIDE; **209** unresolved
- Plant: **50** assets `DOWN`, **131** `DEGRADED` of 918
- Clocks: **7,448 / 7,474** events have `event_time` ≠ `recorded_time`

Humans already absorb this (`exception_handlers`, supervisor emails, FINAL_v7). That is the service, safety, and resilience risk in the brief.

### Question

What must be true — in identity, eligibility, inventory uncertainty, task/order state, and time — before any orchestration (human or software) can be trusted to recommend or act without inventing physical truth or bypassing safety?

### Answer (one sentence, no technology)

**A robot, quantity, task, or cutoff may be used for a decision only when competing sources are reconciled or explicitly marked uncertain, eligibility gates have passed, and clocks are ordered by event time — otherwise the legal output is abstain.**

---

## 2. Root-cause analysis

Do not collapse these into “need an LLM.” They are separate mechanisms. An LLM does not fix a missing join.

### 2.1 Identity fragmentation [EVIDENCED]

- **6** alias strings collide (`BOT-COLLISION-00` … `05`); **4** robots participate (`RBT-0001`–`RBT-0004`).
- `RBT-0001` CMMS alias `BOT-COLLISION-01` is the **WMS** alias of `RBT-0002` (a different type: AMR vs TUGGER).
- Floor/cascade name `AMR-044` has **no** matching alias; `RBT-0044`/`BOT0044` is unproven.
- Fleet contracts rename identity (`robotId` vs `vehicle_id`).
- **8,247 / 8,732 (94.4%)** tasks have `assigned_robot` whose `robots.warehouse_id` ≠ `tasks.warehouse_id`. That is EVIDENCED in rows. Whether it is intended brownfield (identity leak) or generator noise is **UNKNOWN**; either way the control center cannot treat `assigned_robot` as “a robot that is at this DC.”

**Effect:** maintenance, certs, and vision attach to the wrong body. Recovery hits the wrong machine.

### 2.2 Competing systems of record [EVIDENCED]

Prompt 02 matrix: no concept has a single winner.

| Concept | Split |
|---|---|
| Inventory qty | WMS≠ERP 4,601; WMS≠vision 5,415; any-of-three 7,382 |
| Order status | OMS≠WMS 1,283; WMS EXCEPTION 976 vs OMS EXCEPTION 490 |
| Task status | WES≠fleet 7,351 |
| Availability | registry HEALTHY vs CMMS OPEN vs fleet AVAILABLE vs email override |
| Cutoff | `orders.carrier_cutoff` = TMS `planned_departure`, but email says OMS SLA is stale vs Carrier-A |

Running code makes this worse: `/robots/{id}` reads **only** SQLite `robots`. Diagnostics never look at orders, shipments, shadow, or vision. Legacy inventory **drops** ERP and vision.

**Effect:** two operators (or two services) can both be “right” about their own system and still ship the wrong work.

### 2.3 Stale / shadow process [EVIDENCED]

Official SoR is not the operating system:

| Shadow artifact | What it does | Official field that does not show it |
|---|---|---|
| Dock 7 → Z09, WMS map not updated | Physical staging change | `DC-01-Z09` `physical_change_pending=NO` |
| Supervisor low-speed, CMMS open, fleet AVAILABLE | Authority workaround | No approval table; pattern matches `WO-000380` / `RBT-0001` |
| Do not trust camera 18 | Vision policy | CAM-18 still contributes `vision_qty` / observations (conf 0.566 on `RBT-0001`) |
| Carrier-A −35 min, OMS SLA until midnight | Live cutoff | `carrier_cutoff` column unchanged |
| `wave_priority_FINAL_v7.csv` 216 orders | Manual P1–P3 (66 manager_override, 59 carrier_cutoff, 54 inventory_risk, 37 vip) | Not joined to OMS priority; `ORD-002442` is P2 override and WMS EXCEPTION |

**Effect:** global planning that trusts OMS/WMS/wave files will fight the floor list.

### 2.4 Local optimization in `legacy_score()` [EVIDENCED]

```text
score = battery_soc + 10 if ONLINE
candidates = health_status != MAINTENANCE AND connectivity != OFFLINE
```

Documented ignores: expired cert, payload, congestion, maintenance (`allocator.py` comments + three **xfail** tests).

Allocator **pool** = **606 / 712** robots. Of those, **172** still pass the weak filter despite expired cert or open-CMMS-AVAILABLE (**33** expired, **147** open CMMS; overlap exists).

`RBT-0333` is `health_status=MAINTENANCE` so `choose_robot` would **exclude** it — yet it is assigned on `TSK-000968-1`. Assignments in the CSV **do not even obey** the weak legacy function. Cross-DC assignment (94.4%) is the global-throughput harm: local “pick a high battery id” with no site, payload, or congestion constraint.

Cascade `expected_reasoning` already says “avoid locally optimal reroute.” That is this RCA, not a new AI idea.

### 2.5 Missing eligibility gates [EVIDENCED]

| Gate missing in code | Snapshot evidence |
|---|---|
| Safety cert not EXPIRED | 38 EXPIRED; 35 not OFFLINE; 33 in allocator pool |
| Calibration not OVERDUE | 45 OVERDUE; 38 in allocator pool |
| CMMS not OPEN/IN_PROGRESS unless recorded authority | 249 open/in progress WOs; 176 with fleet AVAILABLE |
| Payload ≥ task | no task payload field; allocator ignores `payload_kg` (xfail) |
| Zone not blocked / RESTRICTED | 43 RESTRICTED zones unused by allocator (xfail congestion) |
| Battery / charger alive | `RBT-0644` soc 10% still EXECUTING; 50 assets DOWN including chargers |
| Inventory not uncertain | code treats WMS as truth |

EVAL-002 and EVAL-004 already encode the must-nots. They fail on the legacy path by design.

### 2.6 Temporal / ingest defects [EVIDENCED]

- **7,448 / 7,474 (99.7%)** events: `event_time` ≠ `recorded_time`
- **2,132** of those have `recorded_time` **before** `event_time` (example `EVT-00006783` dispatch)
- Telemetry: **80 / 12,896 (0.62%)** extra duplicate packets (example `RBT-0194` 2026-08-12T07:24:00)
- 18 warehouse timezones; timestamps are timezone-naive → ordering across DCs is **UNKNOWN**
- `ORD-000004` SAME_DAY with cutoff **24 hours** after create: SLA field vs cutoff field **CONFLICTS**

EVAL-003: do not use recorded_time as business sequence.

---

## 3. Baseline KPI tree

Definitions are stated so Repo 2 “before/after” uses the **same** formula.  
Status: **COMPUTED** / **PARTIAL** / **NOT COMPUTABLE**.

### 3.1 Required Prompt 03 metrics

| KPI | Formula used | Value | Status | Caveat |
|---|---|---|---|---|
| **False availability rate (robot union)** | Unique robots with (`EXPIRED` cert ∧ connectivity ≠ `OFFLINE`) **OR** (WO `OPEN`/`IN_PROGRESS` ∧ `fleet_availability=AVAILABLE`) / 712 | **203 / 712 = 28.5%** | COMPUTED | Union of two different “treated available” signals |
| False availability (expired-connected only) | 35 / 712 | **4.9%** | COMPUTED | Diagnostics definition |
| False availability (WO-level) | 176 / 520 open-style WOs | **33.8%** | COMPUTED | Not a robot rate |
| False availability in allocator pool | 172 / 606 weak-filter candidates with expired **or** open-CMMS-AVAILABLE | **28.4%** | COMPUTED | What `choose_robot` would still see |
| **Inventory disagreement rate** | rows with not-all-equal (`wms_qty`,`erp_qty`,`vision_qty`) / 9,360 | **7,382 / 9,360 = 78.9%** | COMPUTED | Disagreement ≠ proven physical error |
| **WES/fleet task conflict rate** | wes_status ≠ fleet_status / 8,732 | **7,351 / 8,732 = 84.2%** | COMPUTED | |
| **Duplicate telemetry rate** | extra duplicate keys / 12,896 | **80 / 12,896 = 0.62%** | COMPUTED | Same definition as `diagnostics.py` |
| **OMS vs WMS disagreement** | oms_status ≠ wms_status / 3,500 | **1,283 / 3,500 = 36.7%** | COMPUTED | |
| **Cutoff-risk proxy A (TMS)** | tms_status = DELAYED / 3,500 | **586 / 3,500 = 16.7%** | COMPUTED | Best operational proxy |
| Cutoff-risk proxy B (Carrier-A) | Carrier-A ∧ DELAYED | **151** shipments | COMPUTED | Matches shadow/cascade carrier |
| Cutoff-risk proxy C (as-of) | `carrier_cutoff` < 2026-09-10 ∧ not DEPARTED | **2,941 / 3,500 = 84.0%** | **PARTIAL** | Historical pile vs live “today”; overstates risk |
| SAME_DAY ∧ DELAYED | count | **183** | COMPUTED | |
| CRITICAL/EXPEDITE, cutoff < as-of, not DEPARTED | count | **862** | PARTIAL | Same as-of issue |

### 3.2 `docs/05_kpis_baseline.md` candidates

| Candidate | Value | Status | Why |
|---|---|---|---|
| On-time carrier departure (measurable) | **64 on-time / 184 late** among 248 DEPARTED with both timestamps (**25.8% on-time**). 311 DEPARTED lack `actual_departure`. 559 DEPARTED total | **PARTIAL** | Missing actuals; not a % of all orders |
| Order cycle time (create → actual depart) | n=248; min 3.7 h; **median 8.3 h**; mean 11.4 h; max 25.2 h | **PARTIAL** | Only measurable departed subset |
| Pick/pack exception rate | WMS `EXCEPTION` **976 / 3,500 = 27.9%**; OMS EXCEPTION 490 / 3,500 = 14.0% | **PARTIAL** | Status ≠ proven pick/pack fail; two SoRs |
| Inventory accuracy | Inverse of disagreement would be 21.1% “sources agree” | **PARTIAL** | Agreement ≠ physical accuracy (EVAL-001) |
| Safety event rate | 1,170 events; **134 per 1,000 tasks**; unresolved 209 | **PARTIAL** | No exposure hours; snapshot not a year |
| Manual overrides per 1,000 tasks | **200 MANUAL_OVERRIDE / 8,732 × 1000 = 22.9** | COMPUTED | Safety table only; misses email overrides |
| Human interventions per 1,000 robot tasks | Same 22.9 if using MANUAL_OVERRIDE only | **PARTIAL** | Labor `exception_handlers` exist but are headcount, not events |
| Maintenance-induced downtime | 67 robots `health=MAINTENANCE`; 249 open/in-progress WOs | **PARTIAL** | No WO close timestamps for duration |
| Plant unavailability | 50/918 DOWN = **5.4%**; +131 DEGRADED | COMPUTED | Asset state, not minutes |
| Labor shortfall | **26 / 54** shifts actual < planned | COMPUTED | Not a warehouse KPI in docs/05 but evidenced waste |
| Robot productive utilization | telemetry speed>0.1 on 12,811/12,896 | **NOT COMPUTABLE** | Almost all rows moving; not idle/busy calendar |
| Robot deadlock rate | WES `BLOCKED` = 1,754 tasks (20.1%) | **NOT COMPUTABLE** as deadlock | BLOCKED ≠ deadlock |
| Charging queue time | 43/712 charging_eligible=N; chargers DOWN exist | **NOT COMPUTABLE** | No queue timestamps |
| Travel distance per completed task | — | **NOT COMPUTABLE** | No path length |
| Congestion minutes | — | **NOT COMPUTABLE** | No congestion clock; 43 RESTRICTED zones unused |
| Recovery time after control-system outage | — | **NOT COMPUTABLE** | Injects are narrative; EVAL-005 not simulated |
| Cost per fulfilled order | — | **NOT COMPUTABLE** | No cost fields |

There are **no undocumented management KPIs** in the repo to “trust.” All numbers above are computed or marked uncomputable. [EVIDENCED]

---

## 4. CTQs and counter-metrics

**CTQs** (critical to quality) for any later Repo 2 proof — mapped to brief outcomes:

| CTQ | Baseline link | Must not damage (counter-metric) |
|---|---|---|
| Zero expired-cert assigns on the **new** path | 33 such robots still in allocator pool; EVAL-002 | Must not hide them by marking robots OFFLINE in CSV |
| Uncertain inventory is visible, not silently WMS | 78.9% disagree; EVAL-001/006 | Must not “fix” by copying vision into WMS |
| Task/order conflicts surfaced before completion | 84.2% task split; `ORD-000968` SHIPPED while EXECUTING | Must not force WES=fleet by overwriting a source |
| Cutoff risk uses a fresher clock than stale OMS SLA | `ORD-000004`; Carrier-A email; 16.7% DELAYED | Must not meet cutoff via safety-zone bypass (EVAL-004) |
| Identity collisions preserved until resolved | `RBT-0001`/`RBT-0002`; AMR-044 unmatched | Must not collapse aliases to the first row |
| Event order uses `event_time` | 99.7% recorded skew; EVAL-003 | Must not sort the warehouse by ingest time |
| Physical control stays disabled | `/health` | Must not add a write path “for the demo” |
| Inject resilience without replay | EVAL-005; Prompt 02 dependency map | Must not blindly replay fleet queues |

**Counter-metrics to watch if “on-time” improves:** safety MANUAL_OVERRIDE rate, ZONE_BREACH, E_STOP, expired-cert assigns, inventory treated-as-known when sources disagree.

---

## 5. Value hypothesis and success / failure (Repo 2 proof only)

**Hypothesis [INFERRED from evidence, not a vendor pitch]:**  
Most exception labor is caused by **false certainty** (wrong id, false available, WMS qty, WES EXECUTING, OMS STAGED) rather than missing robots. If Repo 2 makes eligibility, uncertainty, and conflict **first-class and deterministic**, then (a) unsafe and cross-unfit assigns drop on the new path, (b) cutoff handling can abstain or escalate instead of locally rerouting, and (c) KPI movement is measurable against the table in §3. AI is **not required** for that hypothesis (Prompt 04 decides).

**Three workflows the brief will later need (not implemented here)** — chosen from SIPOC + journeys:

1. **Robot assign / eligibility** — today: `legacy_score` + CSV assigns that ignore site/CMMS/cert (`RBT-0001`, `RBT-0333`, `RBT-0644`).
2. **Inventory allocate / pick truth** — today: WMS-only `legacy_available_qty` vs 78.9% multi-source conflict (`SKU-01146` 205/205/202).
3. **Cutoff / ship confirmation** — today: OMS STAGED vs WMS EXCEPTION vs TMS DELAYED (`ORD-000004`); SHIPPED vs task EXECUTING (`ORD-000968`).

**Repo 2 success criteria**

- New functions have tests that turn the three xfail *behaviors* into passes **without** deleting brownfield CSV contradictions
- EVAL-001–006 must_nots hold on the new path
- False-available robots are ineligible on the new path (rate of *unsafe assigns* → 0 in fixtures; population 203 remains as evidence)
- At least two injects (charging or dock/cascade + one other) replay as fixtures: abstain or replan, no G-violation
- Before/after reported with **same formulas** as §3
- `physical_control` remains disabled

**Repo 2 failure / kill**

- LLM or agent on a write path
- Cleaning `data/` to make KPIs look good
- Claiming cutoff-proxy C (84%) as the business on-time KPI
- Safety override to hit Carrier-A
- “Modernization complete” with TRACEABILITY unlinked (later prompt)

---

## 6. Discovery checklist rank

`participant/DISCOVERY_CHECKLIST.md` after Prompts 01–03.

| Item | Rank | Why |
|---|---|---|
| Identify competing robot IDs | **CLOSED (identified)** | 6 collisions; `RBT-0001` vs `RBT-0002`; AMR-044 unmatched. *Reconcile* is later, not now |
| Reconcile WMS/ERP/vision inventory | **OPEN** | Quantified 78.9%; must **not** reconcile by wiping sources (Prompt 06/12) |
| Find task status conflicts WES vs fleet | **CLOSED** | 84.2%; journeys 1–2 |
| Find maintenance vs fleet availability | **CLOSED** | 176 WOs; `WO-000380`, `WO-000251` |
| Inspect safety cert and calibration | **CLOSED (inspected)** | 38 EXPIRED, 35 connected, 45 OVERDUE; gates not implemented |
| Analyze timestamp / event-order defects | **CLOSED (analyzed)** | 7,448 skew; 80 dups; EVAL-003 |
| Trace one carrier-cutoff risk E2E | **CLOSED** | `ORD-000004` + SHP/TSK/robots/assets/Carrier-A email |
| Identify local optimization that harms global throughput | **CLOSED** | `legacy_score`; xfail; 94.4% cross-DC assign (operational meaning UNKNOWN) |
| Find shadow-process evidence | **CLOSED** | 4 emails; 216 FINAL_v7 rows |
| Map recovery dependencies | **CLOSED** | Prompt 02 §I |
| Propose bounded autonomy tiers | **OPEN** | Constraints known (`docs/06`); tiers are Prompt 04 / 10 |

Prompt 01 located files. Prompt 02 traced IDs. Prompt 03 **quantified and framed**. Tiers and AI-vs-deterministic remain.

---

## Explicit non-claims

- No architecture to-be, no ADR, no LLM/agent decision (Prompt 04).
- No domain spec (Prompt 05).
- Cross-DC assignment rate is a snapshot fact, not a proven physical operating model.
- As-of cutoff 84% is **not** the headline business KPI; DELAYED 16.7% is.

**Next:** Prompt 04 — use-case qualification and AI vs deterministic **stop gate**.
