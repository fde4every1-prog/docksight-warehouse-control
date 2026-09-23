# 02 — System of record matrix

**FDE Operating Model phase:** 2  
**Companion:** `discovery/02_CURRENT_STATE_PROCESS_AND_ARCHITECTURE.md`  
**Date:** 2026-09-17  
**Rule:** a system is not authoritative because of its name. Cells are EVIDENCED from named rows unless tagged otherwise.

Diagnostics (re-run): alias_collisions 6; inventory_truth_conflicts 7,382; wes_fleet_task_conflicts 7,351; maintenance_availability_conflicts 176; expired_safety_cert_but_connected 35; duplicate_telemetry_packets 80. OMS≠WMS orders 1,283 / 3,500.

Legend for **Verdict**

| Verdict | Meaning |
|---|---|
| AGREES | This snapshot row set agrees for the example |
| CONFLICTS | Two or more claimants disagree on the example |
| SOLE | Only this source has the field; others silent |
| STALE / UNOFFICIAL | Shadow or delayed vs another clock |
| ABSENT | No claimant in repo |

---

## How to read a row

**Concept** = business thing we must not mix up.  
**Claimant** = column/file that asserts a value.  
**Example** = a real ID from Repo 1.  
**Does not decide authority.** Authority is Prompt 04/10.

---

## 1. Robot canonical identity

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| Fleet/registry CSV + SQLite | `robots.robot_id=RBT-0001` | DC-01 AMR RoboFlow | SOLE numeric registry id |
| WMS alias | `BOT-COLLISION-00` | `robot_aliases` source=WMS | CONFLICTS with other robots’ names (collision family 00–05) |
| Fleet alias | `BOT-COLLISION-00` | source=FLEET for RBT-0001 | AGREES with this robot’s WMS alias; still a colliding string globally |
| CMMS alias | `BOT-COLLISION-01` | source=CMMS for RBT-0001 | **CONFLICTS**: that string is WMS alias of **RBT-0002** |
| Vision | `observed_entity=RBT-0001` | `DC-01-CAM-18` conf 0.566 | AGREES id string; **UNTRUSTED** per email |
| Shadow / cascade | name `AMR-044` | `ops_emails.txt`, `cascade_001.json` | **ABSENT** as exact alias; `RBT-0044` / `BOT0044` is **INFERRED** only — do not merge |
| Fleet API v1 vs v2 | `robotId` vs `vehicle_id` | `contracts/fleet_api_v1.yaml`, `v2.yaml` | CONFLICTS schema; no live calls |

**Competing SoR:** registry `robot_id` vs WMS/FLEET/CMMS aliases vs informal floor names.  
**Must not:** silently overwrite canonical id from alias or camera (EVAL-006; Prompt 03 identity RCA).

---

## 2. Robot site / location

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| Registry | `robots.warehouse_id` | RBT-0001 → **DC-01**; RBT-0333 → **DC-09**; RBT-0644 → **DC-17** | — |
| Task assignment | `tasks.warehouse_id` + `assigned_robot` | TSK-000968-1 is **DC-02** but robot RBT-0333 is DC-09; TSK-000004-1 is **DC-16** but RBT-0644 is DC-17 | **CONFLICTS** |
| Telemetry | `robot_telemetry.zone` | RBT-0001 has 18 telemetry rows (DC-01 zones in samples) | Observation, not assignment |
| Vision | `observed_zone=DC-01-Z08` | CAM-18 on RBT-0001 | Observation, low confidence |
| Warehouse master | `warehouses.timezone`, `fleet_vendor` | DC-02 timezone UTC+5:30 vs DC-01 UTC+1 | CONFLICTS if events are compared naively |

---

## 3. Robot availability (“can we dispatch?”)

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| Registry health | `health_status` | RBT-0001 HEALTHY; RBT-0333 **MAINTENANCE** | CONFLICTS with other availability fields |
| Registry connectivity | `connectivity` | RBT-0001 ONLINE; RBT-0020 INTERMITTENT | — |
| CMMS | `cmms_status` + `fleet_availability` | WO-000380 RBT-0001 IN_PROGRESS + **AVAILABLE**; WO-000251 RBT-0333 IN_PROGRESS + **AVAILABLE**; WO-000503 RBT-0020 OPEN + AVAILABLE, safety_release **N** | **CONFLICTS** (176 such WOs) |
| Charging | `charging_eligible` | RBT-0001 Y | SOLE for charge policy |
| Shadow supervisor | email “Fleet shows AVAILABLE” despite open CMMS | AMR-044 pattern | UNOFFICIAL override |
| Legacy allocator | exclude only MAINTENANCE and OFFLINE | would still pick RBT-0001; would **exclude** RBT-0333 if used — but RBT-0333 is assigned anyway | CONFLICTS with actual `tasks.assigned_robot` |

**Available ≠ suitable ≠ assigned.** [EVIDENCED]

---

## 4. Safety / calibration eligibility

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| Safety cert | `safety_cert_status` | RBT-0001 VALID; RBT-0020 **EXPIRED** but INTERMITTENT (counts in 35 expired-and-not-OFFLINE) | CONFLICTS with any “online ⇒ usable” rule |
| Calibration | `calibration_status` | RBT-0333 OVERDUE; RBT-0644 OVERDUE; 45 OVERDUE total | CONFLICTS with HEALTHY/AVAILABLE |
| Safety events | E_STOP / ZONE_BREACH / NEAR_MISS | 191 / 194 / 197 events; sources OPERATOR, FLEET, SAFETY_PLC, VISION | Observation; 209 unresolved |
| Eval seed | EVAL-002 | must_not assign expired-cert robot | Spec, not implemented in allocator |
| Eval seed | EVAL-004 | must_not endorse safety-zone bypass for cutoff | Spec |

---

## 5. Task execution state

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| WES | `tasks.wes_status` | TSK-000004-1 **EXECUTING**; TSK-000968-1 EXECUTING; TSK-003149-4 **BLOCKED** | — |
| Fleet | `tasks.fleet_status` | TSK-000004-1 **FAILED**; TSK-000968-1 EXECUTING; TSK-003149-4 **COMPLETE** | **CONFLICTS** on 7,351 tasks |
| WES event | TASK_DISPATCHED | EVT-00006783, EVT-00004607 | — |
| Fleet event | TASK_STATUS | EVT-00006784 payload EXECUTING | May lag (recorded_time 12:14:44 vs event_time 12:11:00) |
| Order status (downstream) | OMS/WMS SHIPPED | ORD-000968 SHIPPED while task EXECUTING | **CONFLICTS** with task state |

WES vs fleet disagree values observed: COMPLETE vs EXECUTING, BLOCKED vs COMPLETE, EXECUTING vs FAILED, QUEUED vs EXECUTING, QUEUED vs ASSIGNED, QUEUED vs COMPLETE, BLOCKED vs FAILED.

---

## 6. Inventory quantity and location

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| WMS | `wms_qty` | DC-01 SKU-01146 loc DC-01-Z03-B017 **205**; DC-16 SKU-00169 loc DC-16-Z07-B002 **36**; DC-02 SKU-00639 loc DC-02-Z11-B024 **66** | — |
| ERP | `erp_qty` | 205; 36; **67** | AGREES on first two; **CONFLICTS** on DC-02 (66 vs 67) |
| Vision | `vision_qty` | **202**; **35**; **65** | **CONFLICTS** all three examples |
| Reservation | `reserved_qty` | 16; 9; 5 | SOLE |
| Status | `inventory_status` | AVAILABLE / AVAILABLE / **QUARANTINE** (DC-02 sample) | Digital hold vs counts |
| Cycle count age | `last_cycle_count_days` | 2; 22; **66** | Staleness |
| Legacy code | `legacy_available_qty` | uses **only** wms_qty − reserved | **Ignores** ERP and vision |
| Shadow email | “Physical count wins for high-value SKU family”; “Do not trust camera 18” | no SKU id in email | UNOFFICIAL policy vs vision_qty |
| Eval | EVAL-001, EVAL-006 | must_not invent physical truth; must_not pick a source by name | Spec |

Conflicts: **7,382 / 9,360** inventory rows.

---

## 7. Order status

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| OMS | `oms_status` | ORD-000968 **SHIPPED**; ORD-000004 **STAGED**; ORD-002442 **PACKING** | — |
| WMS | `wms_status` | ORD-000968 SHIPPED; ORD-000004 **EXCEPTION**; ORD-002442 **EXCEPTION** | AGREES first; **CONFLICTS** 1,283 orders including 000004 and 002442 |
| OMS event | ORDER_RELEASED | EVT-00000719 ORD-000004 | — |
| WMS event | ORDER_ALLOCATED payload `wms_status=EXCEPTION` | EVT-00000720 | WMS already EXCEPTION at allocate |
| Shadow wave | `manual_priority` | ORD-002442 P2 `manager_override` | UNOFFICIAL; **ABSENT** for ORD-000004 and ORD-000968 |

---

## 8. Carrier cutoff and shipment progress

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| OMS order | `carrier_cutoff` | ORD-000004 2026-09-03T20:16:00; ORD-000968 2026-08-31T14:17:00 | — |
| TMS | `planned_departure` | matches those timestamps on SHP-000004 / SHP-000968 | AGREES with order cutoff field |
| TMS | `tms_status` / `actual_departure` | SHP-000968 DEPARTED 14:19; SHP-000004 **DELAYED**, actual empty; SHP-002442 DELAYED but actual 07:02 (after 05:52 plan) | CONFLICTS vs OMS “still staged/packing” |
| Carrier | `carrier` | Carrier-B on 968; **Carrier-A** on 000004 and 002442 | — |
| Shadow email | Carrier-A −35 minutes; OMS SLA table stale until midnight | no order_id in email | **STALE** vs `carrier_cutoff` column |
| Cascade drill | same Carrier-A story + 214 orders at risk | `cascade_001.json` | Drill; not applied as a data mutation |
| Service level vs cutoff | SAME_DAY vs 24h cutoff on ORD-000004 | CRITICAL SAME_DAY created 20:16, cutoff next day 20:16 | **CONFLICTS** / **INFERRED** SLA bug |

---

## 9. Zone map vs physical layout

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| Zone master | `map_version`, `physical_change_pending`, `robot_access` | DC-01-Z09 STORAGE v9 pending **NO** access YES; DC-01-Z01 STAGING v7 pending **YES** HIGH density | — |
| Shadow email | Dock 7 workaround → temporary staging in Z09; **WMS map has NOT been updated** | Z09 pending flag does **not** show the workaround | **CONFLICTS** with email |
| Control assets | sorter/dock state | DC-01-SORTER-03 **DOWN**; DC-16-DOCK_DOOR-04 DOWN | Physical plant vs zone row |
| Restricted access | `robot_access=RESTRICTED` | 43 / 216 zones | SOLE; allocator does not read it |

---

## 10. Time / event order

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| Business time | `event_time` | EVT-00006783 2026-08-31T11:57:00; EVT-00000001 2026-08-30T13:55:00 | — |
| Recorded / ingest | `recorded_time`, `ingest_time` | EVT-00006783 recorded **11:56:38** (before event); EVT-00006784 recorded 12:14:44 vs event 12:11:00; EVT-00000001 recorded **13:54:22** before 13:55:00 | **CONFLICTS** on 7,448 / 7,474 events |
| Warehouse timezone | `warehouses.timezone` | DC-02 UTC+5:30 vs DC-16 UTC+1 vs naive timestamps without offset | **UNKNOWN** whether timestamps are local or UTC |
| Eval | EVAL-003 | must_not assume business sequence from recorded_time | Spec |
| Duplicate telemetry | same robot_id+event_time+zone+battery+speed | RBT-0194 2026-08-12T07:24:00 (80 dups) | CONFLICTS with “each packet is a new pose” |

---

## 11. Plant / charging assets

| Claimant | Field | Example | Verdict |
|---|---|---|---|
| Control assets | `state` | DC-16-CHARGER-08 DOWN; DC-02-CHARGER-07 DOWN; DC-01-SORTER-03 DOWN | — |
| Charging plan | `preferred_charger` | RBT-0001 → DC-01-CHARGER-02 (not the DOWN charger) | May still conflict under inject_02 |
| Inject / cascade | charger 3 fails; AS/RS unavailable; dock closure | markdown/JSON only | Drill **ABSENT** from live state machine |

---

## 12. What the running app actually uses

| Question | Source the app reads | Sources it ignores |
|---|---|---|
| Diagnostics counts | robots, aliases, inventory, tasks, maintenance, telemetry CSVs | orders, shipments, shadow, vision, events, zones, assets, safety, charging |
| `/robots/{id}` | SQLite `robots` only | aliases, CMMS, telemetry, vision, tasks |
| Legacy allocate | in-memory robot dicts (battery, connectivity, health) | cert, payload, congestion, CMMS, zone access |
| Legacy inventory | `wms_qty`, `reserved_qty` | erp_qty, vision_qty, cycle count, quarantine |
| Physical execute | none (`physical_control: disabled`) | everything |

So even when a “system of record” exists in a file, **the running control-center code is not looking at it.** That is a current-state architecture fact, not a future design.

---

## Compact concept × system grid

C = CONFLICTS in snapshot; A = AGREES on the happy-path *order header only*; S = SOLE field; — = no claim; U = unofficial/stale.

| Concept | ERP | OMS | WMS | WES | Fleet | CMMS | Vision | TMS | Safety PLC | Shadow |
|---|---|---|---|---|---|---|---|---|---|---|
| Robot id | — | — | C aliases | — | C aliases | C aliases | C/low conf | — | — | U AMR-044 |
| Robot warehouse | — | — | — | C via tasks | C registry | C WO warehouse | zone only | — | — | — |
| Availability | — | — | — | assigns anyway | C | C | — | — | — | U override |
| Safety cert | — | — | — | ignored | C (still connected) | safety_release Y/N | — | — | events | — |
| Task status | — | — | — | C | C | — | — | — | — | — |
| Inventory qty | C | — | C | — | — | — | C | — | — | U physical count |
| Order status | — | C | C | — | — | — | — | C vs DELAYED | — | U wave P1–P3 |
| Cutoff | — | C/stale | — | — | — | — | — | A planned / C actual | — | U −35 min |
| Zone map | — | — | C pending flags | — | — | — | — | — | RESTRICTED unused | U Z09 workaround |

---

## IDs frozen for later prompts

Do not replace these without a new evidence note.

| Journey | IDs |
|---|---|
| Closest happy path | `ORD-000968` · `SHP-000968` · `TSK-000968-1` · `RBT-0333` · `WO-000251` · DC-02 / DC-09 |
| EXCEPTION / cutoff | `ORD-000004` · `SHP-000004` · `TSK-000004-1` · `TSK-000004-2` · `RBT-0644` · `RBT-0506` · DC-16 / Carrier-A |
| Identity / maint / vision | `RBT-0001` · aliases `BOT-COLLISION-00/01` · `WO-000380` · `DC-01-CAM-18` · vs `RBT-0002` |
| Shadow extra | `ORD-002442` · P2 manager_override · `RBT-0020` expired cert |
