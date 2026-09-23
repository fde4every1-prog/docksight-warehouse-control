# Repo 3 domain, workflows and controls

## 1. Bounded contexts

| Context | Core concepts | Owner |
|---|---|---|
| Bazaar Intake | BazaarOrder, Service, DeliveryAttempt, Outbox | Bazaar |
| Fulfillment | ParentOrder, SubOrder, Allocation, Task, Progress | Supervisor/Core |
| Inventory Accounting | FreeQuantity, Reservation, PickedQuantity, Movement | Core |
| Resource Readiness | Robot, ControlAsset, MaintenanceEvidence, Claim | Fleet/Core |
| Lifecycle Simulation | Battery, Charging, FailureBlock, Replacement, Recovery | Fleet Simulator |
| Intervention | Issue, Proposal, Approval, Verification, AuditEvent | Persona-specific |
| Forecasting | ForecastRun, DailyInput, ForecastItem, Coverage | Core |
| Brownfield Review | SourceRecord, Diagnostic, LegacyAllocation | Reviewer |
| Replay | Snapshot, SimulationRun, Benchmark, ReplayReport | Admin/Reviewer |

## 2. Important invariants

| ID | Invariant |
|---|---|
| V3-I1 | Imported brownfield sources are immutable evidence. |
| V3-I2 | Repeating the same request identity/body cannot create another order. |
| V3-I3 | A changed body under an existing request identity is rejected. |
| V3-I4 | Bazaar acceptance is all-or-nothing within the selected warehouse. |
| V3-I5 | Free stock is the conservative source minimum and is debited once. |
| V3-I6 | Pick releases reservation; it does not debit free stock again. |
| V3-I7 | Completed movement effects are idempotent across retries/restarts. |
| V3-I8 | Missing/blocking readiness evidence prevents assignment. |
| V3-I9 | Resource claims are exclusive. |
| V3-I10 | Recovery preserves completed work and does not duplicate stock effects. |
| V3-I11 | Corrections cannot directly overwrite protected reservations/picked totals. |
| V3-I12 | All resource execution is simulated; no physical action is available. |
| V3-I13 | Statistical demand forecast is never labeled as trained AI. |
| V3-I14 | Persona selection is not asserted as secure identity. |

## 3. End-to-end journeys

### Journey A — customer order to staged completion

1. Customer creates a multi-line order in Bazaar.
2. Bazaar persists order and outbox delivery state atomically.
3. Core validates warehouse, SKUs, quantities and stable identity.
4. Core verifies every Bazaar line against selected-warehouse allocatable stock.
5. Core debits free source balances, credits reservations and creates work.
6. Supervisor explicitly starts planned work where the applicable flow requires it.
7. Scheduler acquires eligible robot/control-asset/labor capacity.
8. Tasks progress through Pick, Move, Pack_feed and Stage.
9. Pick converts reservation to picked/in-process state exactly once.
10. Bazaar and Core expose delivery and fulfillment progress separately.

### Journey B — stock shortage

1. Acceptance detects that one selected-warehouse line is short.
2. The entire new Bazaar request is rejected with warehouse, SKU, requested and
   available quantities.
3. No order, task, reservation or movement is created in Core.
4. Bazaar keeps failed delivery state for inspection/retry.
5. Later correction/replenishment can enable a controlled retry.

### Journey C — resource failure

1. Fleet identifies a running simulated assignment and its assignment token.
2. Fleet records failure or kills the current assignment.
3. Failure state and failed-resource block are persisted.
4. Kill attempts an eligible same-stage replacement; otherwise work waits.
5. Explicit recovery removes only the simulator failure block.
6. Independent readiness, claim, payload and safety blockers still apply.
7. Completed stages and inventory effects remain unchanged.

### Journey D — discrepancy intervention

1. Detection creates or reopens an issue from current effective evidence.
2. Role owner investigates/proposes under the relevant workflow.
3. Revision/fingerprint protects against stale action.
4. Approved corrections update app-owned modeled sources only.
5. Verification records evidence and reevaluates held work.
6. Reservations, picked work and imported source evidence remain protected.

### Journey E — forecast explanation

1. Scheduled generation aggregates attributable demand by IST calendar day.
2. Zero-demand days are included in the observed window.
3. Mean daily demand produces ceiling-rounded 7/30-day totals.
4. Run inputs and coverage labels are saved.
5. Detail views use the exact selected run; missing legacy evidence stays missing.
6. Low-stock alert compares current free availability with the saved 7-day value.

## 4. Authority matrix

| Action | Bazaar | Supervisor | Fleet | Admin | System |
|---|---:|---:|---:|---:|---:|
| Create customer request | ✓ | — | — | — | — |
| Accept/reserve valid order | — | — | — | — | deterministic policy |
| Start/retry/cancel eligible order | — | ✓ | — | limited | — |
| Assign simulated task | — | — | — | — | scheduler/API |
| Correct inventory evidence | — | ✓ | — | inspect | — |
| Repair fleet readiness | — | — | ✓ | inspect | — |
| Fail/kill/recover simulator assignment | — | — | ✓ | — | — |
| Configure/register supported resources | — | — | — | ✓ | — |
| Inspect all audit/policy | — | scoped | scoped | ✓ | — |
| Write external WMS/FMS/PLC/robot | — | — | — | — | **prohibited** |

This is a product authority model, not a secure access-control model.

## 5. Hard controls

- Loopback-only packaged launcher.
- Pydantic request validation and bounded enums/numbers.
- Stable request IDs and fingerprints.
- SQLite transactions and `BEGIN IMMEDIATE` for serialized decisions.
- Optimistic revisions, condition fingerprints and assignment tokens.
- Immutable imported evidence.
- Separate mutable databases.
- Exclusive resource claims.
- Missing-readiness fail-closed rules.
- Persistent quantity movement identities.
- Maintenance lock for offline destructive maintenance.
- No external adapter or physical-control command surface.

## 6. Assumptions

- Source files are synthetic snapshots, not live feeds.
- SKU weights are synthetic and consistent by SKU, not measured.
- Stage/resource-type mappings are demo policy, not warehouse topology.
- Task duration is configurable simulation time, not measured handling rate.
- Battery/calibration fields are not all assignment gates in the current V3 policy.
- The local caller is trusted to choose the correct demo persona.
- SQLite and a single API process are sufficient for demo scale.

## 7. Known tensions

1. V2's strict safety framing remains, but V3 intentionally implements a richer
   simulated write path. The write path is local SQLite, never physical OT.
2. V3 has both historical policy-v1 compatibility and current policy-v2 paths;
   saved historical work is not retroactively replanned.
3. Resource/browser edits can affect the simulator while source files remain
   unchanged; UI language must distinguish modeled state from external truth.
4. Some mutations are not persona-guarded. Loopback isolation is therefore a
   deployment control, not a convenience.
5. Demand forecasting supports decisions but is a transparent baseline, not AI.
