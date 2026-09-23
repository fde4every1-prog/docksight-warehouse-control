# P01-v1-SDD_GAP_ANALYSIS

**Prompt:** 01 — Warehouse Brownfield Forensics  
**Artifact:** Gap analysis vs WRCC SDD intent and 15 golden scenarios  
**Rule:** Tag PASS / PARTIAL / FAIL / NOT PROVEN. Do not invent contract text that is not in this repo.

The prompt library references WRCC-FR-011 and WRCC-AC-002…015. **Those requirement files are not in this repository.** Ratings below compare (a) what this brownfield repo actually contains with (b) the *intent* stated in the external prompt library. That is a gap, not a failed hidden spec.

---

## 0. Contract and SDD scaffolding

| ID | Finding | Tag | Evidence |
|----|---------|-----|----------|
| SDD-01 | WRCC SDD contract in repo | **FAIL** | No `specs/`, no WRCC-*.md |
| SDD-02 | TRACEABILITY_MATRIX.md | **FAIL** | Absent |
| SDD-03 | DEFINITION_OF_READY / DONE | **FAIL** | Absent |
| SDD-04 | Observe→Reason→Propose→Decide→Approve→Execute→Observe loop | **FAIL** | No DecisionEngine, Approval, ActionExecutor |
| SDD-05 | “LLM never on the write path” | **PARTIAL** | No LLM write path exists; also no enforced DecisionEngine. API is GET-only with `physical_control: disabled` |
| SDD-06 | Challenge-brief reconstruction of systems of record | **PARTIAL** | Docs + data allow a map; no canonical WarehouseState |
| SDD-07 | Packaged baseline reproducibility | **PASS** | `VERIFICATION.md`, `scripts/verify_repo.py`, checksums, diagnostics JSON |
| SDD-08 | Physical robot control disabled | **PASS** | `/health`, README, AGENTS.md, cursor rule |

---

## 1. Prompt-01 required gap themes

| Theme | Tag | What exists | What is missing |
|-------|-----|-------------|-----------------|
| Robot identity | **PARTIAL** | `robot_id`, `fleet_id`, aliases, 6 collisions, EVAL-006 | No resolver; no preserve-disagreement API; no tote identity; fleet v1 `robotId` vs v2 `vehicle_id` |
| Live WarehouseState | **FAIL** | Snapshot CSVs + SQLite | No freshness, occupancy, connectivity, UNKNOWN execution, or graph |
| Human-only zones | **PARTIAL** | 43 RESTRICTED zones, HIGH human density, ZONE_BREACH events, EVAL-004 | No keep-out polygon, no path gate, allocator ignores `blocked_zone` |
| Supervisor authority | **PARTIAL** | Email “supervisor approved”; docs/06 human authority; labor file | No Supervisor role, no expiring approval, no audit of Act |
| Lost write-acks | **FAIL** | Fleet v1 “No idempotency key”; EVAL-005 (stale replay, not ack) | No command id, UNKNOWN execution, reconcile-on-ack |
| Clock drift | **PARTIAL** | `event_time` vs `recorded_time` (7,448 / 7,474 events); telemetry `event_time` ≠ `ingest_time` (12,765 / 12,896); EVAL-003 | No drift detector; no multi-clock model (robot / WMS / control center) |
| Wi-Fi / edge outage | **PARTIAL** | `connectivity` ONLINE / INTERMITTENT / OFFLINE; EVAL-005 | No edge journal, no cloud-down mode, no local policy cache |
| Offline continuity | **FAIL** | Narrative in README L10 | No degraded-mode implementation |
| Reconnect reconciliation | **FAIL** | EVAL-005 `must_not` blindly replay | No journals, no merge, no provenance report |

---

## 2. Fifteen WRCC golden scenarios

Robot ids in this dataset are `RBT-nnnn`, not `R-12`. “Aisle 7” is not a named entity. Ratings use **analogous evidence**, not invented scenario packs.

| # | Scenario | Tag | Repo evidence | Gap |
|---|----------|-----|---------------|-----|
| 1 | Aisle 7 blocked (pallet + committed AMR + picker) | **PARTIAL** | Cascade: “forklift blocks alternate route”; zones `physical_change_pending`; allocator XFAIL on `blocked_zone`; Dock 7 email | No aisle occupancy, no committed-path set, no fail-safe UNKNOWN occupancy |
| 2 | Robot R-12 battery critical with tote on deck | **PARTIAL** | Battery SOC/SOH, charging_eligible=N (43), cascade AMR-044 low battery | No robot R-12; no tote-on-deck; no critical-SOC gate in allocator (high battery is preferred) |
| 3 | Wave will miss carrier cutoff | **PARTIAL** | `orders.carrier_cutoff`; shadow wave CSV; cascade −35 min; stale OMS email | No Wave aggregate; no cutoff risk engine; OMS vs WMS status fights |
| 4 | Lost write-ack (UNKNOWN dispatch) | **FAIL** | Fleet API v1 has no idempotency key | No command identity, UNKNOWN state, or ack reconciliation |
| 5 | Path through human-only zone | **PARTIAL** | 43 RESTRICTED; 194 ZONE_BREACH; EVAL-004 must_not bypass | No path planner; no DecisionEngine gate; UNKNOWN zone does not refuse |
| 6 | Telemetry pose vs WMS/fleet identity | **PARTIAL** | Alias collisions (e.g. `BOT-COLLISION-01` → RBT-0001 CMMS vs RBT-0002 WMS); telemetry `zone` only | No pose; no identity-conflict object; silent overwrite not even modeled |
| 7 | Stale map / WMS snapshot treated as live | **PARTIAL** | `map_version`, 27 physical_change_pending; Dock 7 email; cycle-count days; inventory snapshot | No freshness TTL; legacy inventory treats WMS as live truth |
| 8 | Duplicate / replayed dispatch | **FAIL** | Duplicate **telemetry** packets counted (80); not command replay | No dedupe key; v1 API documents the hole |
| 9 | Prompt injection (chat / SOP / WMS note) | **NOT PROVEN** | Untrusted text exists (`ops_emails.txt`, WMS-like notes in shadow) | No copilot to attack; no injection tests |
| 10 | Unauthorized remote execute | **PARTIAL** | No execute API (GET only); physical_control disabled | Cannot prove role enforcement; no Supervisor vs remote attacker tests |
| 11 | Clock drift robot / WMS / control center | **PARTIAL** | Dual timestamps on events and telemetry; EVAL-003 | No named clocks; no drift alarm; recorded_time can precede event_time (EVT-00000001) |
| 12 | Charger occupancy conflict (two robots, one bay) | **PARTIAL** | 137 shared preferred_charger keys; max 11 robots; 144 CHARGER assets; inject 02 | No occupancy mutex; preferred_charger is a label, not a reservation |
| 13 | Damaged tote / inventory discrepancy | **PARTIAL** | 7,382 qty fights; vision confidence; camera 18 email; EVAL-001/006 | No tote; no damaged-tote exception workflow; WMS-only available qty |
| 14 | Floor Wi-Fi / edge outage (cloud AI unavailable) | **PARTIAL** | Connectivity field; L10 narrative | No edge-first mode; no “AI out while aisle blocked” test; copilot already absent |
| 15 | Reconnect reconciliation | **FAIL** | EVAL-005 text only | No journals, no merge, no “do not overwrite Supervisor decision” |

**Scoreboard:** PASS 0 · PARTIAL 10 · FAIL 4 · NOT PROVEN 1 (scenarios 1–15)  
Contract scaffolding: PASS 2 · PARTIAL 2 · FAIL 4 (section 0, excluding challenge-brief row)

---

## 3. Hard-gate IDs from the prompt library (intent only)

| ID | Intent | Tag | Notes |
|----|--------|-----|-------|
| WRCC-FR-011 | AI must not issue AMR/WMS writes | **PARTIAL** | True by absence of write APIs, not by an authority engine |
| WRCC-AC-002 | Wave pull-forward / labor needs Supervisor | **FAIL** | No approval object |
| WRCC-AC-003 | Human-only zone hard gate | **FAIL** | Data flag only; allocator can still pick congested/restricted-unaware |
| WRCC-AC-004 | Preserve identity disagreement | **FAIL** | Collisions counted; not preserved as first-class conflict |
| WRCC-AC-005 | Stale map/WMS not treated live | **FAIL** | Legacy inventory trusts WMS |
| WRCC-AC-006 | Missing telemetry → abstain | **FAIL** | Allocator uses battery even with no pose/quality gate |
| WRCC-AC-007 | Idempotent commands; lost ack → UNKNOWN | **FAIL** | v1 contract |
| WRCC-AC-008 | Unauthorized remote execute blocked | **PARTIAL** | No execute surface |
| WRCC-AC-009 | Prompt injection cannot change Policy | **NOT PROVEN** | No Policy, no copilot |
| WRCC-AC-010 | Degraded mode during Wi-Fi/cloud loss | **FAIL** | Unimplemented |
| WRCC-AC-011 | Conflicting pose/charger evidence preserved | **FAIL** | Conflicts exist in CSV; runtime collapses or ignores them |
| WRCC-AC-013 | Detect clock drift | **FAIL** | Fields exist; no detector |
| WRCC-AC-014 | Local safety without cloud AI | **NOT PROVEN** | No edge runtime; AMR LIDAR not in dataset |
| WRCC-AC-015 | Reconnect without silent overwrite | **FAIL** | Unimplemented |

Golden eval questions (`EVAL-001`…`006`) **align in spirit** with several ACs but are **not a runner** (`evals/README.md` is one line). Tag for eval harness: **FAIL** as executable TEVV, **PARTIAL** as intent seeds.

---

## 4. Implications (forensics only)

1. This capstone repo is a **rich evidence estate** and a **thin control plane**. Do not claim WRCC SDD compliance.  
2. Highest-risk inherited behaviors already proven in tests: expired-cert assignment, no payload check, no congestion/keep-out check, WMS-only inventory.  
3. Highest-risk **missing** controls vs the 15 scenarios: idempotency/UNKNOWN ack, reconnect journals, live WarehouseState, human-zone hard gate, injection/authority tests.  
4. Prompt 02+ must write specs **before** code. Overlay version stays **0.1.0** until a spec exists; baseline **2.0.0** stays frozen.
