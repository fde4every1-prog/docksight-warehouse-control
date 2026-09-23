# Where C4, ubiquitous language, evals, and risk/resilience live

**Purpose:** Presentation locator. Repo3 did **not** recreate the V2 `specs/` tree. Named FDE artifacts exist in three places: the **Repo3 ZIP**, this **V3 pack**, and the **separate V2 repo**.

**Roots**

| Tree | Path |
|---|---|
| Repo3 ZIP | `Warehouse-Local-Windows.zip` → `warehouse-local/` |
| V3 pack (this folder’s parent) | `Capstone/V2/V3/` |
| V2 FDE spine | `Capstone/V2/AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2/` |

Repo3 also embeds a **trimmed** brownfield copy at  
`warehouse-local/artifacts/api-server/brownfield/AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2/`.  
That copy is **not** the full V2 discovery/specs/eval pack.

---

## 1. C4 (architecture views)

Repo3 has **as-built product architecture**, not a file named `05_target_c4.md`.

| Level | Where it was created | What it is |
|---|---|---|
| Context / container (as-built) | **Created in V3:** `V3/ARTIFACTS/01_AS_BUILT_ARCHITECTURE.md` | Mermaid context diagram, containers, API components, data planes |
| ASCII control-tower flow | **In Repo3:** `artifacts/api-server/CONTROL_TOWER.md` §2 Architecture | Bazaar → API → SQLite → executor; Supervisor/Fleet HITL |
| Runtime composition | **In Repo3:** `local_server.py`, `artifacts/api-server/baseline_demo.py`, `replit.md` | Three SPAs + one FastAPI origin |
| API surface (not C4) | **In Repo3:** `lib/api-spec/openapi.yaml` | Selected generated contract |
| Current-state C4 (as-is brownfield) | **In V2, not Repo3 root:** `discovery/02_CURRENT_STATE_PROCESS_AND_ARCHITECTURE.md` §E | Inherited estate |
| Target C4 (Option A observe/refuse) | **In V2:** `specs/05_target_c4.md` | UC-1 target |
| As-built C4 (V2 code) | **In V2:** `specs/14_as_built_c4.md` | V2 FastAPI/dashboard, executor stub |

**Say in the room:** “C4 for DockSight V3 is `01_AS_BUILT_ARCHITECTURE.md`, backed by `CONTROL_TOWER.md` §2. Formal C4 target/as-built for the original proof remains in V2 `specs/05_target_c4.md` and `specs/14_as_built_c4.md`.”

---

## 2. Ubiquitous language (domain vocabulary)

There is **no** Repo3 file named `01_domain_model.md`. Language is split: V2 canonical warehouse terms vs Repo3 product terms.

| Vocabulary | Where it was created | Canonical names |
|---|---|---|
| **V2 ubiquitous language** | **V2:** `specs/01_domain_model.md` §1–3 | Robot, Eligibility, Conflict, Uncertainty, InventoryObservation, Decision ALLOW/DENY/ABSTAIN, I1–I12 |
| Context map | **V2:** `specs/01_context_map.md` | Bounded contexts and relationships |
| **V3 product language** | **Created in V3:** `V3/ARTIFACTS/02_DOMAIN_WORKFLOWS_AND_CONTROLS.md` | BazaarOrder, SubOrder, Allocation, Movement, Intervention, ForecastRun, Replay |
| Product PRD terms | **In Repo3:** `artifacts/api-server/CONTROL_TOWER.md` §1 | Free stock, reservation, Pick / Move / Pack_feed / Stage, persona |
| **Brownfield ER (knowledge share)** | **Created in V3:** `V3/ARTIFACTS/08_DOMAIN_ER_DIAGRAM.md` | Warehouse, Zone, SKU, Order, Task, Shipment, Robot and related observations |
| Intake terms | **In Repo3:** `artifacts/api-server/BAZAAR_API.md` | FBZ id, service, outbox, request identity |
| Intervention terms | **In Repo3:** `artifacts/api-server/PERSONA_API.md` | investigate / propose / approve / verify, fleet repair |
| API type names | **In Repo3:** `lib/api-zod/src/generated/types/` | `bazaarOrder`, `lifecycleTask`, `fulfillmentAssignmentResult` |

**Say in the room:** “Warehouse evidence language (Robot, Conflict, UNCERTAIN) is V2 `01_domain_model.md`. Product journey language (Bazaar, sub-order, reservation, Stage) is Repo3 `CONTROL_TOWER.md` plus V3 `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`. Do not mix them as one glossary without calling the fork.”

---

## 3. Evals and test cases

Repo3 **does not** rerun V2 EVAL-001–022 against the new executor. It has **product regressions** plus a **nested seed eval file**.

### Show for DockSight V3 (Repo3 tests)

| Artifact | Path in Repo3 ZIP |
|---|---|
| Packaged verification | `TEST_REPORT.md` |
| Product verification record | `artifacts/api-server/CONTROL_TOWER.md` §4 |
| V3 requirement → test map | **Created in V3:** `V3/ARTIFACTS/04_REQUIREMENTS_TRACEABILITY.md` |
| Fulfillment / accounting | `artifacts/api-server/test_fulfillment_v2.py`, `test_fulfillment.py`, `test_control_tower_boundaries.py` |
| Bazaar intake | `artifacts/api-server/test_bazaar_api.py` |
| Personas / HITL | `test_persona_api.py`, `test_persona_spec.py`, `test_persona_low_stock.py`, `test_persona_manual_close.py`, `test_persona_workspace_search.py` |
| Fleet repair | `test_fleet_repair.py`, `test_fleet_offline_repair.py` |
| Lifecycle / charging / fail-kill | `test_robot_lifecycle.py`, `test_robot_lifecycle_query_count.py` |
| Forecast | `test_demand_forecast.py` |
| Progress / export | `test_order_progress.py`, `test_order_progress_batching.py` |
| Replay | `test_replay.py`, `test_replay_merge.py` |
| Reset / weights / demo route | `test_operational_order_reset.py`, `test_sku_weights.py`, `test_demo_route_removed.py` |
| Browser lifecycle | `tests/lifecycle-ui/lifecycle-regression.spec.ts` |

### Show only if asked about the original FDE eval harness (V2)

| Artifact | Path in V2 repo |
|---|---|
| Golden pack | `evals/golden_cases_repo2.jsonl` (EVAL-001–022) |
| Scorecard | `evals/scorecard.md` |
| Strategy | `specs/03_evaluation_strategy.md` |
| Harness | `src/warehouse_control/evals/harness.py` |
| Traces | `evals/traces/` |
| Nested in Repo3 only | `artifacts/api-server/brownfield/.../evals/golden_cases.jsonl` (seed, not the full Repo2 pack) |

**Say in the room:** “V3 evals are the `test_*.py` suite and `TEST_REPORT.md`. V2 EVAL-001–022 stay in V2 `evals/`. We do not claim those 22 cases passed on the V3 simulated executor.”

---

## 4. Risk and resilience evidence

| Concern | Where it was created | Use in presentation |
|---|---|---|
| **Production / demo risk register** | **Created in V3:** `V3/ARTIFACTS/05_PRODUCTION_READINESS.md` | P0 blockers, release gates |
| **FDE harm register (synthetic)** | **V2:** `specs/03_risk_and_harms.md` | H1–H13; not a live-plant filing |
| **Threat model** | **V2:** `specs/07_threat_model.md` | TH-1–12; not copied into Repo3 |
| **Failure modes / injects** | **V2:** `specs/05_failure_modes.md`, `scenarios/inject_01.md`–`inject_06.md`, `scenarios/cascade_001.json` | AS/RS, charging, dock; V2 replay |
| **Consistency / restart resilience** | **In Repo3:** `CONTROL_TOWER.md` §2 Consistency boundaries | Atomic accept, no duplicate movement, restart-safe clocks |
| **Race / conservation tests** | **In Repo3:** `test_control_tower_boundaries.py` | Accept vs fleet acquire; cancel/pick races; idempotency |
| **Failure / replace / recover** | **In Repo3:** `robot_lifecycle.py`, `test_robot_lifecycle.py`, `replit.md` Fleet Simulator notes | Simulated kill/replace, not OT recovery |
| **Offline repair / reset locks** | **In Repo3:** `FLEET_OFFLINE_REPAIR.md`, `ORDER_RESET.md`, `maintenance_lock.py` | Fail-closed maintenance |
| **Replay isolation** | **In Repo3:** `REPLAY.md`, `replay_runner.py` | Copied DB; does not mutate live demo store |
| **Loopback / unauthenticated demo** | **In Repo3:** `LOCAL_SETUP_WINDOWS.md`, `local_server.py`; **V3:** `ADRs/ADR-006-demo-personas-loopback-boundary.md` | Shared-network NO-GO |
| **No AI / no OT** | **V3:** `ADRs/ADR-002-deterministic-simulation-no-ai-or-ot.md`; Repo3 `/api/health` `physical_control: disabled` | Hard boundary |
| **OM 17–21 honesty** | **Created in V3:** `V3/ARTIFACTS/03_FDE_OM21_EVIDENCE_MATRIX.md`; **V2:** `discovery/17_21_LIFECYCLE_DEFERRED.md` | Local ZIP ≠ production resilience |

**Say in the room:** “Risk register for this product is V3 `05_PRODUCTION_READINESS.md`. Harm/threat/inject evidence for the original proof is V2 `03_risk_and_harms.md`, `07_threat_model.md`, and inject scenarios. Repo3 adds restart, race, lock, fail/replace, and replay tests—still simulation, not live OT resilience.”

---

## One-page show list (these four)

| Ask | Open first | Backup |
|---|---|---|
| C4 | `V3/ARTIFACTS/01_AS_BUILT_ARCHITECTURE.md` | Repo3 `CONTROL_TOWER.md` §2; V2 `specs/05_target_c4.md` |
| Ubiquitous language | `V3/ARTIFACTS/02_DOMAIN_WORKFLOWS_AND_CONTROLS.md` | V2 `specs/01_domain_model.md`; Repo3 `CONTROL_TOWER.md` §1 |
| Evals / tests | `V3/ARTIFACTS/04_REQUIREMENTS_TRACEABILITY.md` + Repo3 `TEST_REPORT.md` | Repo3 `artifacts/api-server/test_*.py`; V2 `evals/scorecard.md` |
| Risk / resilience | `V3/ARTIFACTS/05_PRODUCTION_READINESS.md` | Repo3 `test_control_tower_boundaries.py`; V2 `specs/03_risk_and_harms.md` |
