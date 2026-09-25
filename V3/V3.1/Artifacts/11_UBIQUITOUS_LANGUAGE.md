# Ubiquitous language

**Case:** Autonomous Warehouse Robotic Control Tower  
**Scope:** Brownfield warehouse evidence and the Repo 3 local fulfillment simulator  
**Status:** Working canonical vocabulary  
**Date:** 2026-09-24

## Purpose

This glossary defines the shared language for the warehouse control-tower repo. It
keeps brownfield evidence, simulated operational state, advisory intelligence, and
decision authority distinct. The terms below should be used consistently in
requirements, APIs, UI labels, tests, ADRs, and evidence reports.

The repository contains two related vocabulary layers:

1. **Brownfield evidence language:** imported CSV, JSONL, legacy SQLite, and source
   observations. These records preserve competing system views and are not silently
   promoted to physical truth.
2. **V3 product language:** the local simulator's mutable SQLite state, workflows,
   policies, lifecycle controls, forecasts, interventions, replay, and advisory labs.

A term from one layer must not be used to imply facts that belong only to the other.

## Bounded contexts

| Context | Owner | Canonical concepts |
|---|---|---|
| Brownfield Review | Reviewer | SourceRecord, Diagnostic, Conflict, Uncertainty, LegacyAllocation |
| Bazaar Intake | Bazaar / customer surface | BazaarOrder, Service, DeliveryAttempt, Outbox, RequestIdentity |
| Fulfillment | Supervisor / Core | ParentOrder, SubOrder, Allocation, Task, Progress |
| Inventory Accounting | Core | FreeQuantity, Reservation, PickedQuantity, Movement |
| Resource Readiness | Fleet / Core | Robot, ControlAsset, MaintenanceEvidence, Claim, Eligibility |
| Lifecycle Simulation | Fleet Simulator | Battery, Charging, FailureBlock, Replacement, Recovery |
| Intervention | Persona workflows | Issue, Proposal, Approval, Verification, AuditEvent |
| Forecasting | Core | ForecastRun, DailyInput, ForecastItem, Coverage |
| Maintenance Review | Fleet / Supervisor / Admin | ModelCard, RetrospectiveScore, ReviewPriority, Freshness |
| Replay | Admin / Reviewer | Snapshot, SimulationRun, Benchmark, ReplayReport |
| Transfer Lab | Reviewer | FrozenSnapshot, TransferScenario, ValidatedPlan, CompareRun |
| Detached Batching | Reviewer | SyntheticScenario, BatchCandidate, ValidatedPlan, CompareRun |
| KPI Audit | Read-only reporting | SourceCohort, ScenarioCohort, MetricDefinition |

## Core warehouse terms

| Term | Definition | Do not conflate with |
|---|---|---|
| **Warehouse** | A distribution-center scope identified by `warehouse_id`, containing inventory, zones, resources, work, and observations. | Region, zone, site-wide physical truth |
| **Warehouse ID** | Stable scope key such as `DC-01`. It is required to interpret many other identifiers. | A vendor, fleet, or robot identifier |
| **Zone** | A warehouse-scoped logical/physical area such as `DC-01-Z03`, with type, access, density, map version, and physical-change metadata. | A bin, location, route, or safety certification |
| **Location** | A stock location recorded in inventory evidence, often an encoded value such as `DC-01-Z03-B017`. | A zone; the zone relationship may be derived from the encoded value |
| **SKU** | A product/catalogue identifier such as `SKU-00035`, with description, unit of measure, temperature, lot, serial, and hazmat properties. | An inventory row or an order line |
| **Vendor** | A reference organization associated with robotics or other equipment/services. | A warehouse operator or system of record |
| **Control asset** | A warehouse equipment resource used by simulated stages, such as a conveyor, charger, pack station, dock door, vision gate, or ASRS. | A robot, a maintenance work order, or a physical command |
| **Labor capacity** | Warehouse staffing capacity by shift, including planned/actual workers and certified role counts. | Robot capacity or proof that labor is currently available |

## Demand and fulfillment terms

| Term | Definition | Do not conflate with |
|---|---|---|
| **Bazaar order** | A customer-facing order request originating in the Bazaar application. | A Core parent order before acceptance |
| **Request identity** | Stable identity and body fingerprint used to make order handoff idempotent. | An order number that can safely be reused with changed content |
| **Delivery attempt** | A recorded attempt to hand a Bazaar order to Core, including success or actionable failure. | Physical shipment delivery |
| **Outbox** | Durable Bazaar handoff record that retries delivery after persistence and restart. | A message broker or external guarantee |
| **Parent order** | Core's accepted aggregate representing the fulfillment request and its overall progress. | A raw source order or a Bazaar request that was rejected |
| **Sub-order** | SKU/warehouse-scoped fulfillment work derived from a parent order. | A shipment or a task |
| **Allocation** | A decision assigning a sub-order quantity to an eligible warehouse/location/source. | Reservation, pick completion, or a physical stock movement |
| **Task** | A staged unit of simulated work with task type, order context, state, timing, and possibly a resource claim. | A robot command or a generic to-do item |
| **Task stages** | The simulated sequence `Pick -> Move -> Pack_feed -> Stage`. | Arbitrary task types from brownfield evidence, which may also include `REPLENISH` |
| **Progress** | The durable projection of fulfillment stage and order status exposed to users and integrations. | Raw WES/fleet status or physical completion proof |
| **Priority** | An ordering signal used by a workflow or scheduler, such as service/cutoff order or a manual override. | Safety authorization or permission to bypass constraints |
| **Cutoff** | The deadline associated with an order/service or carrier departure. | A promise that physical execution can meet the deadline |
| **Held work** | Accepted or observed work that cannot currently progress because a business, inventory, resource, or readiness condition blocks it. | Cancelled work or completed work |

## Inventory accounting terms

| Term | Definition | Do not conflate with |
|---|---|---|
| **Free quantity** | Conservative nonnegative available quantity derived from eligible source quantities, currently the minimum of WMS, ERP, and vision free values. | Total on-hand, reserved quantity, or forecast availability |
| **Reservation** | Quantity committed to accepted fulfillment but not yet successfully picked. | A free-stock debit performed at pick |
| **Picked quantity** | Quantity moved from reservation into picked/in-process state after successful Pick. | Completed shipment quantity |
| **Movement** | Durable idempotent accounting event recording a quantity transition. | A robot movement command or a route segment |
| **Protected accounting** | Reservation and picked totals that corrections cannot directly overwrite. | Immutable source evidence; app-owned modeled state may be corrected under workflow |
| **Inventory observation** | A source-specific or observed quantity statement from WMS, ERP, vision, or another evidence source. | Canonical physical truth |
| **Shortage** | Failure to meet the required eligible quantity for an order or line at acceptance time. | A low-stock forecast alert |
| **All-or-nothing acceptance** | For a new Bazaar order, every line must be accepted within the selected warehouse or the request is rejected without Core reservation/task creation. | Partial fulfillment of historical/non-Bazaar flows |

## Resource and lifecycle terms

| Term | Definition | Do not conflate with |
|---|---|---|
| **Robot** | A warehouse resource record with identity, warehouse, type, vendor, capacity, status, certification, connectivity, and lifecycle evidence. | A physical robot under live control |
| **Eligibility** | Deterministic result that a robot or control asset satisfies the current stage's policy constraints. | A guarantee of physical safety or certification |
| **Readiness evidence** | Evidence required to consider a resource selectable, including maintenance, availability, safety, and related fields. | A predictive score or a caller-selected persona |
| **Maintenance evidence** | CMMS/fleet records used by readiness policy, including status, availability, issue, and release information. | A maintenance recommendation or model score |
| **Claim** | Exclusive persisted ownership of a resource for a simulated task or stage. | A reservation of inventory |
| **Assignment token** | Versioned identity used to protect a simulated task assignment against stale or duplicate operations. | Authentication or physical authorization |
| **Battery state** | Persisted simulated charge/health state used by lifecycle behavior and, where applicable, eligibility. | Predictive maintenance risk |
| **Charging state** | Persisted simulator state indicating whether a robot is charging and associated charge progression. | A charger asset's maintenance state |
| **Failure block** | Persisted simulator block created by a failure/kill event that prevents normal continuation until explicit recovery. | A maintenance hold or a safety release |
| **Replacement** | Same-stage simulator recovery attempt that finds another eligible resource without duplicating completed work. | Automatic physical substitution |
| **Recovery** | Explicit workflow that removes only the simulator failure block while preserving independent readiness and safety blockers. | A blanket safety release |
| **Maintenance hold** | Hard feasibility constraint caused by blocking maintenance/readiness evidence until authorized technical release. | A soft predictive alert |

## Forecasting and maintenance intelligence

| Term | Definition | Do not conflate with |
|---|---|---|
| **Forecast run** | Versioned persisted calculation for a forecast date, observation window, method, and generated outputs. | A live sensor feed |
| **Daily input** | Warehouse/SKU/day demand input retained for explaining a forecast. | A task or inventory movement |
| **Forecast item** | Forecast result for one warehouse/SKU pair, including daily demand, 7/30-day estimates, history units, history days, and coverage status. | An allocation eligibility decision |
| **Coverage** | Description of how much attributable history exists, such as `observed`, `short_history`, or `no_history`. | Confidence or a guarantee of accuracy |
| **Statistical demand baseline** | Current transparent mean daily ordered-units method used to estimate warehouse/SKU demand. | A trained AI model or an LLM output |
| **Preventive-maintenance alert** | Read-only human-review prioritization for elevated estimated failure risk in the documented horizon. | A diagnosis, safety interlock, readiness decision, or automatic work order |
| **Retrospective score** | Frozen model output evaluated on historical observations and served as JSON for review. | Current robot health or live telemetry |
| **Model card** | Versioned description of model intent, data, features, evaluation, threshold, and limitations. | Operational approval |
| **Review priority** | Display category such as `review`, `monitor`, or `unavailable` produced by the maintenance snapshot. | A command to repair or stop a robot |
| **Freshness** | Age and snapshot status of an output relative to its observation end date. | Evidence that the latest physical state is known |

## Advisory AI and human decision terms

| Term | Definition | Do not conflate with |
|---|---|---|
| **LLM proposal** | A structured suggestion generated from bounded context, such as a transfer plan or task-grouping candidate set. | An approved plan or an executable command |
| **Candidate** | Individually feasible group or plan element that can be considered by a validator. | A committed task grouping |
| **Deterministic validator** | Authoritative rule engine that checks identifiers, feasibility, overlap, capacity, deadlines, and other hard constraints. | A quality hint or hidden fallback |
| **Validated plan** | Proposal that passes deterministic validation for its specific snapshot and constraints. | Human approval or dispatch |
| **Human approval** | Explicit accountable decision by an authorized workflow owner after reviewing proposal, evidence, validation, and freshness. | Demo persona selection or automatic acceptance |
| **Advisory** | A result intended to inform review and comparison, with no authority to mutate protected operational state. | Autonomous action |
| **Automatic execution** | System action that changes operational state without an explicit human decision. This is prohibited for LLM proposals in the current product boundary. | Deterministic scheduler progress under established policy |
| **No fallback substituted** | On provider failure, timeout, malformed output, or rejected proposal, no hidden heuristic is used to create a replacement decision. | A deterministic validator rejecting invalid output |

## Evidence and authority terms

| Term | Definition | Do not conflate with |
|---|---|---|
| **Immutable evidence** | Imported source file or record preserved without app mutation for review and comparison. | Current mutable simulator state |
| **Effective evidence** | Current evidence set selected by an explicit source/revision policy for a workflow. | Truth established solely by source name |
| **Source conflict** | Two or more observations or statuses disagree for the same conceptual entity. | A software defect that should be silently normalized |
| **Uncertainty** | Material lack of reliable evidence, identity, freshness, completeness, or agreement. | A permission to guess |
| **Diagnostic** | Structured finding about data quality, contradiction, risk, or unresolved condition. | A corrective action that has already been approved |
| **Revision** | Version/fingerprint used to detect stale edits or decisions. | A model version alone |
| **Audit event** | Durable record of actor, action, time, reason, before/after context, and evidence. | A log line without accountability |
| **Persona** | Demo workflow scope such as Customer, Supervisor, Fleet, Admin, or Reviewer. | Secure identity or production RBAC |
| **Decision authority** | The role or deterministic system component permitted to make a particular decision. | A model's ability to generate text or a score |
| **Physical control** | Command or actuation of real robots, PLCs, WMS/FMS/ERP, or other external operational systems. | Local simulated state transition |

## Canonical status vocabulary

| Status family | Canonical values or examples | Meaning |
|---|---|---|
| Fulfillment | `planned`, `held`, `active`, `completed`, `cancelled`, `in_recovery` | Product-level order/work lifecycle; exact route contracts govern values |
| Task/WES | `QUEUED`, `ASSIGNED`, `EXECUTING`, `COMPLETE`, `BLOCKED` | Brownfield observed execution view |
| Fleet task | `QUEUED`, `ASSIGNED`, `EXECUTING`, `COMPLETE`, `FAILED` | Brownfield observed fleet view |
| Robot health | `HEALTHY`, `DEGRADED`, `MAINTENANCE` | Source/simulator robot state; not a predictive score |
| Connectivity | `ONLINE`, `INTERMITTENT`, `OFFLINE` | Robot connectivity observation |
| Safety certificate | `VALID`, `EXPIRING`, `EXPIRED` | Certification evidence state |
| Maintenance | `OPEN`, `IN_PROGRESS`, `PLANNED`, `CLOSED` | Work-order status; readiness policy may treat blocking values specially |
| Inventory | `AVAILABLE`, `HOLD`, `QUARANTINE` | Inventory source/status evidence |
| Model review | `review`, `monitor`, `unavailable` | Read-only maintenance review category |
| Evidence confidence | `observed`, `short_history`, `no_history`, `unknown` | Coverage or evidence state; not a probability unless explicitly labelled |

## Naming rules

1. Use `warehouse_id`, `robot_id`, `order_id`, `task_id`, `sku`, `zone_id`, and
   `asset_id` exactly in API and evidence-facing contracts.
2. Say **warehouse/SKU** when referring to forecast grain; do not call a forecast an
   inventory allocation.
3. Say **free quantity**, **reservation**, and **picked quantity** for accounting
   states; do not use “available” for all three.
4. Say **maintenance review score** or **retrospective score**; do not call it live
   health, diagnosis, safety, or a maintenance hold.
5. Say **proposal**, **validated plan**, and **approval** as separate lifecycle steps.
6. Say **simulated execution** for local state changes and **physical control** only
   for real external actuation, which is outside this repo.
7. Say **source conflict** or **uncertainty** when evidence disagrees or is missing;
   do not silently select a source because its system name sounds authoritative.
8. Keep V2 brownfield terms and V3 runtime terms distinct when the same business idea
   has different semantics or persistence.

## Common forbidden conflations

- A robot's source `health_status` is not a predictive-maintenance score.
- A predictive-maintenance score is not a readiness gate, safety decision, or repair.
- A forecast is not inventory availability and does not reserve stock.
- A task is not a physical robot command.
- A claim is not an inventory reservation.
- A successful API response is not proof of physical completion.
- A demo persona is not authenticated identity.
- A validated LLM plan is not approved, dispatched, or physically executed.
- An immutable source observation is not mutable simulator truth.
- A carrier shipment is not the same entity as a warehouse task.
- A location encoded with a zone prefix is not a separately modelled zone row.
- A status conflict is not resolved merely because one system is called WMS, WES,
  fleet, ERP, or vision.

## Source references

- `artifacts/fde-artefacts/02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`
- `artifacts/fde-artefacts/08_DOMAIN_ER_DIAGRAM.md`
- `artifacts/fde-artefacts/10_CSV_ENTITY_RELATIONSHIP_DIAGRAM.md`
- `artifacts/fde-artefacts/PRD.md`
- `artifacts/api-server/CONTROL_TOWER.md`
- `artifacts/api-server/FULFILLMENT_API.md`
- `artifacts/api-server/BAZAAR_API.md`
- `artifacts/api-server/PERSONA_API.md`
- `artifacts/api-server/BATCHING_CONTRACT.md`
- `artifacts/api-server/models/predictive-maintenance/model_card.md`
