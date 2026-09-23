# Product Requirements Document — Warehouse Fulfillment Control Tower V3

**Status:** As-built PRD reconstructed from Repo 3  
**Date:** 2026-09-22  
**Product class:** Local, deterministic warehouse fulfillment and resource-lifecycle simulator  
**Release posture:** Demo/POC only; production and physical-control **NO-GO**

## 1. Product statement

V3 demonstrates how customer orders can enter a warehouse control tower,
reserve conservative inventory, progress through simulated warehouse tasks,
surface exceptions to role-specific workspaces, and preserve auditable state
without changing the inherited brownfield source files or controlling physical
equipment.

The product is an operational simulation, not an AI agent. Decisions are made
by explicit policies, SQLite transactions and deterministic scheduling.

## 2. Problem

V2 proved that brownfield robot, maintenance, inventory and task evidence can
be reconciled and gated. It did not provide a durable customer-to-fulfillment
product journey. Operators still needed a product surface that could:

1. accept idempotent multi-line orders;
2. reserve stock without inventing physical truth or double-debiting;
3. assign suitable simulated resources to staged work;
4. persist progress across process restarts;
5. expose holds, discrepancies and recovery actions by persona;
6. demonstrate failures, charging and replacement behavior;
7. retain the original evidence snapshot for review.

## 3. Goals

- Provide separate customer order entry through FDE Bazaar.
- Persist order delivery, reservations, tasks, resource claims and audit events.
- Allocate conservatively using the minimum of free WMS, ERP and vision values.
- Keep each new Bazaar order within its selected warehouse.
- Execute `Pick → Move → Pack_feed → Stage` per SKU using simulated resources.
- Fail closed on missing or contradictory resource-readiness evidence.
- Give Supervisor, Fleet and Admin distinct demo workspaces and interventions.
- Support resource failures, recovery, replacement, charging and restart safety.
- Provide transparent, statistical demand forecasts without claiming ML.
- Package all three applications for local Windows use on loopback.
- Preserve the inherited brownfield files as immutable evidence.

## 4. Non-goals

- Real robot, PLC, WCS, WMS, ERP or fleet-manager control.
- Sensor or physical-inventory ground truth.
- LLM, RAG, knowledge-graph or autonomous-agent execution.
- Secure login, production RBAC, tenant isolation or internet exposure.
- Certified safety, feasibility, delivery SLA or production resilience.
- Learned demand forecasting or spatial route optimization.
- Automatic migration of historical work to the current policy.
- OM 17–21 customer deployment, live value proof, AIMS operation or retirement.

## 5. Personas

| Persona | Primary jobs | Permitted demo actions | Important limit |
|---|---|---|---|
| Customer / Bazaar user | Create and inspect orders | Submit, inspect delivery, retry failed handoff | Does not start warehouse tasks |
| Order Fulfilment Supervisor | Manage order flow and inventory exceptions | Inspect queue, resolve scoped discrepancies, prioritize, approve/recover work | Cannot certify physical truth |
| Asset & Fleet Manager | Maintain simulated resource readiness | Repair readiness evidence, fail/kill/recover simulator resources, manage charging | Cannot approve Supervisor-owned operational decisions |
| Control Tower Admin | Inspect policy/audit and register/configure demo resources | Read all scopes; manage supported configuration/registration | No operational approval authority |
| Reviewer / FDE participant | Compare legacy and new behavior | Inspect source records and pure legacy allocator | Review surface does not dispatch |

The `X-Demo-Persona` header and UI selector are demonstrations of role scope,
not identity or authentication.

## 6. Product surfaces

1. **Core Warehouse** (`/`) — fulfillment, workspaces, inventory, resources,
   audit/review and configuration.
2. **FDE Bazaar** (`/fde-bazaar/`) — customer order entry and receipt/history.
3. **Robot Fleet Simulator** (`/robot-lifecycle/`) — resource lifecycle,
   failures, replacement, recovery and charging.
4. **Shared FastAPI gateway** (`/api`) — all application and legacy-review APIs.
5. **SQLite state** — separate fulfillment and Bazaar stores plus immutable
   inherited CSV/JSONL/SQLite evidence.

## 7. Functional requirements

### FR-1 — Bazaar order intake

- Accept one or more distinct SKU lines with positive integer quantities.
- Require a known warehouse for new Bazaar orders.
- Support `Same_Day`, `Next_Day` and `Standard`.
- Set immutable UTC deadlines at creation +6h, +12h and +24h respectively.
- Generate a stable order identity and persist an HTTP outbox record atomically.
- Retry with the same request identity and body without creating duplicates.
- Reject reuse of an identity with a different body.

### FR-2 — Acceptance and inventory accounting

- Validate every Bazaar line against allocatable stock in the selected warehouse
  within one reservation transaction.
- Reject the full Bazaar order if any line is short; do not use another warehouse.
- For compatibility callers, allocate each SKU independently to one warehouse
  and permit available sibling lines to proceed.
- Compute location free stock as nonnegative
  `min(wms_qty, erp_qty, vision_qty)` subject to eligibility/blockers.
- At acceptance, debit each free source quantity and credit reservation once.
- At successful Pick, release reservation and move quantity into picked/in-process
  state without debiting free stock again.
- Protect all movement effects with durable identities.

### FR-3 — Planning and execution

- Model each SKU as location Picks followed by Move, Pack_feed and Stage.
- Use a configurable task duration, default 45 simulated seconds.
- Persist task start, due and completion timestamps and exclusive claims.
- On restart, continue the saved clock and never replay stock effects.
- Prioritize eligible work by deadline using deterministic tie-breaks.
- Keep completed stages and unaffected work unchanged during recovery.

### FR-4 — Resource eligibility

- Require healthy robots with a nonblank, non-expired certificate status.
- Require online/intermittent connectivity and nonblocking maintenance evidence.
- Require warehouse, type and payload compatibility using SKU-level synthetic
  weights with no global fallback.
- Require control assets to be available, clear, compatible and unclaimed.
- Reject missing maintenance/CMMS evidence.
- Never treat repair or a safety-release flag as a bypass for independent gates.

### FR-5 — Lifecycle simulator

- Show authoritative simulated resource state and active/recovery work.
- Permit Fleet to fail or kill an assignment using request and assignment tokens.
- Attempt exact-stage replacement after a kill; otherwise leave work waiting.
- Persist an explicit failed-resource block until Fleet recovery.
- Auto-dock idle known-battery robots below 10%; stop charging at 100%.
- Prevent active claims from docking or being reassigned.

### FR-6 — Supervisor workspace

- Show fulfillment queue, detail, progress, deadlines and holds.
- Separate discrepancies/interventions from low-stock monitoring.
- Require comments/evidence where specified and retain audit history.
- Preserve reservations and picked quantities when correcting free-stock evidence.
- Reevaluate held work without silently starting or double-reserving it.

### FR-7 — Fleet workspace

- Search and paginate active robot/control-asset readiness issues.
- Expose complete blocker context and optimistic revisions.
- Apply multi-record readiness repair atomically.
- Retain before/after history while leaving imported source files unchanged.
- Clear an issue only when all current blockers are resolved.

### FR-8 — Admin and audit

- Allow Admin to inspect all interventions, policy and audit records.
- Allow only supported resource registration/configuration actions.
- Reject unsupported fields, stale revisions and unsafe changes while active work
  exists.
- Do not imply the demo persona mechanism is production authorization.

### FR-9 — Demand forecast

- Persist a transparent mean-demand baseline over completed IST calendar days.
- Include zero-demand days and report short/no-history coverage.
- Produce ceiling-rounded 7-day and 30-day forecasts.
- Retain saved run inputs where available and never reconstruct missing history.
- Replace fixed low-stock thresholding with the persisted 7-day forecast.
- Label this as a statistical baseline, not a trained model.

### FR-10 — Review and replay

- Keep inherited datasets and six legacy inspection views available.
- Keep the legacy allocator inspection pure: no dispatch and no persistence.
- Permit isolated replay against copied SQLite state and report descriptive
  comparisons without modifying the live demo database.
- Export generated order projections atomically with spreadsheet-injection
  escaping.

## 8. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Bind the packaged launcher to `127.0.0.1` by default. |
| NFR-2 | Preserve imported brownfield files; mutable state belongs in separate SQLite stores. |
| NFR-3 | Use transactions for acceptance, reservation, movement and intervention consistency boundaries. |
| NFR-4 | Make command retries idempotent and reject changed-body identity reuse. |
| NFR-5 | Use optimistic revisions/tokens for concurrent mutable workflows. |
| NFR-6 | Recover persisted clocks and claims without duplicate task or stock effects. |
| NFR-7 | Keep policy decisions deterministic and independent of AI availability. |
| NFR-8 | Record assumptions and simulated/synthetic labels in API/UI evidence. |
| NFR-9 | Provide searchable/paginated operational collections. |
| NFR-10 | Support Python 3.11 and packaged prebuilt web assets on local Windows. |

## 9. Product KPIs

These are required measurement definitions, not current success claims.

| KPI | Definition | V3 evidence state |
|---|---|---|
| Intake idempotency | Duplicate orders per repeated request identity | Test-covered in packaged suite; fresh rerun not performed |
| Stock accounting integrity | Duplicate/missing quantity movements | Ledger/design evidence; production volume not proven |
| Unsafe assignment rate | Assignments violating encoded readiness gates | Simulator tests reported; physical feasibility not proven |
| Recovery correctness | Recovered tasks that duplicate completed work/stock effects | Test scenarios reported |
| Order completion lead time | Accepted-to-completed duration by service and hold reason | Data available in SQLite; no target/benefit baseline approved |
| Held-order aging | Time in stock/resource/recovery hold by reason | Data available; target absent |
| Forecast error | WAPE/MAE against later observed demand | **Not implemented/proven**; current forecast is a baseline |
| Operator intervention closure | Time and recurrence by intervention kind | Auditable data available; target absent |
| Availability/resilience | Uptime, restart recovery, error budget | **Not production-measured** |

## 10. Acceptance criteria for the V3 demo

1. All three local applications load from one loopback origin.
2. A new Bazaar order is persisted before delivery and handed to Core using a
   stable request identity.
3. Insufficient selected-warehouse stock rejects the Bazaar order atomically.
4. A feasible order reserves stock exactly once and creates staged tasks.
5. Simulated tasks retain clocks/claims across restart and complete without
   duplicate stock movement.
6. Ineligible or claimed resources are not selected.
7. Fleet failure/kill/recovery paths preserve completed work.
8. Supervisor corrections preserve reserved and picked accounting.
9. Imported brownfield source files remain unchanged.
10. Every UI and document clearly states simulation/no physical control.

## 11. Release gates

### Local demonstration — MAY RELEASE

- Package integrity for the runnable archive is confirmed.
- Required Python runtime/dependencies are installed.
- Apps bind to loopback.
- Active SQLite databases pass integrity checks.
- Focused backend and browser tests are rerun on the target Windows package.
- Demo data is synthetic and contains no real operational/private data.

### Shared network or customer pilot — MUST NOT RELEASE

Blocked until authentication/RBAC, CSRF and API authorization, secrets,
network/TLS controls, database migration/backup/restore, observability, load and
concurrency tests, vulnerability/dependency management, incident response,
privacy review and tenant/data isolation are implemented and independently
assured.

### Physical or external-system write path — PROHIBITED

Requires a separate mandate, real interfaces, hazard analysis, safety case,
command/idempotency contracts, independent verification, operational approvals
and site-specific certification. V3 supplies none of that authority.

## 12. Open decisions

- Whether Repo 3 remains a local teaching product or becomes a candidate pilot.
- Which system owns authenticated identity and authorization in any shared use.
- Which external systems, if any, can provide authoritative inventory and
  resource state.
- Approved business targets for lead time, holds, recovery and forecast error.
- Whether the statistical forecast is sufficient or an evaluated predictive
  model is justified by future data.
