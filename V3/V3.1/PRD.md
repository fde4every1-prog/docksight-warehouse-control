# PRD for Code Generation

## 1. Product summary

Build a local warehouse fulfillment control-tower simulator that behaves like a packaged demo product rather than a live operational system. The generated app must support customer order intake, conservative inventory reservation, staged fulfillment execution, role-based exception handling, simulated fleet disruption, and read-only reporting surfaces while remaining fully local and loopback-bound.

This repo already follows a multi-app design with a shared Python FastAPI backend and multiple frontend surfaces. The generated code should preserve that structure and produce a user experience similar to the existing implementation.

## 2. Product boundaries

### 2.1 In-scope behavior
The app must simulate all core warehouse operations locally:
- customer order intake
- selected-warehouse acceptance logic
- inventory reservation and movement ledger
- task execution states and progress tracking
- robot readiness, charging, and lifecycle behavior
- persona-driven exception handling
- advisory transfer and batching comparisons
- KPI and predictive-maintenance review surfaces

### 2.2 Out-of-scope behavior
The generated application must explicitly avoid:
- live robot control
- live WMS/FMS/ERP/PLC integrations
- real authentication or RBAC
- secure production deployment
- any real external system writes
- autonomous operational action by an AI agent
- industrial safety certification or physical feasibility proofs

### 2.3 Canonical invariants
The generated implementation must preserve the following core business rules and boundaries. These invariants are intentionally strict because they define the product’s simulated operating logic and keep the app safe and deterministic.

- I1: Imported brownfield sources are immutable evidence.
- I2: The same request identity and body cannot create a second order; a changed body is rejected.
- I3: A new Bazaar order is accepted entirely inside its selected warehouse or not at all.
- I4: Free stock is a conservative nonnegative minimum of warehouse source quantities after eligibility and is debited once at acceptance.
- I5: Pick releases reservation and moves quantity into picked state without a second free-stock debit.
- I6: Movement effects use durable identities and are not replayed on restart.
- I7: Missing or blocking readiness evidence fails closed; repair and safety-release flags are not bypasses.
- I8: Resource claims are exclusive; completed stages remain completed during recovery.
- I9: An LLM or predictive score cannot create tasks, reserve stock, repair robots, or dispatch work.
- I10: No adapter writes to a real WMS, FMS, PLC, or robot.
- I11: Demo persona headers are not authentication.
- I12: Demand forecast remains a statistical baseline; the maintenance model is a separate labelled experiment.

### 2.4 Product goals
The product must prioritize the following goals:
- Accept idempotent multi-line Bazaar orders and persist delivery, reservations, tasks, claims, and audit events.
- Allocate conservatively and keep each new Bazaar order inside its selected warehouse.
- Execute staged simulated work with restart-safe clocks and persistent state.
- Give Supervisor, Fleet, and Admin distinct demo workspaces.
- Show resource failure, replacement, charging, and recovery without duplicating stock effects.
- Compare transfer and batching plans against deterministic baselines on frozen scenarios.
- Publish read-only monthly KPI definitions and maintenance model metadata with clear synthetic labels.
- Package the app for local Windows-style loopback use.
- Preserve inherited brownfield evidence as immutable context.

### 2.5 Product non-goals
The system must not be designed as a production warehouse control solution. It must explicitly avoid:
- Real robot, PLC, WCS, WMS, ERP, or fleet-manager control.
- Sensor or physical-inventory ground truth.
- An agent that plans and executes warehouse work automatically.
- Using an LLM when it is unconfigured or substituting a hidden heuristic.
- Treating predictive-maintenance scores as a safety interlock or live health status.
- Treating KPI scenarios as observed history or causal improvement evidence.
- Secure login, production RBAC, tenant isolation, or internet exposure.
- Certified safety, delivery SLA, or production resilience claims.
- Learned demand forecasting or route optimization as a live operational control.
- Automatic migration of historical work onto the current policy.

### 2.6 Persona definitions
The implementation must model the following personas clearly and consistently in both backend logic and frontend UX.

| Persona | Primary jobs | Allowed demo actions | Hard limit |
|---|---|---|---|
| Order Fulfillment Supervisor | Order flow and inventory exceptions | Queue, resolve discrepancies, prioritize, approve and recover work | Cannot certify physical truth |
| Asset & Fleet Manager | Simulated readiness and advisory review | Repair readiness evidence, fail/kill/recover simulator resources, charge batteries, review maintenance scores | Cannot act on a score alone |
| Control Tower Admin | Policy, audit, and config | Inspect policy and audit surfaces, support config, read model and KPI views | No operational approval authority |

The repo’s demo-header pattern should be used to simulate persona scope without implying production authentication.

## 3. Functional architecture

### 3.1 Shared backend
The backend should be a single local FastAPI service mounted under `/api`, plus static frontend mounts at app routes.

Required API groups:
- `/api/fulfillment`
- `/api/personas`
- `/api/bazaar`
- `/api/replays`
- `/api/review`
- `/api/monthly-kpis`
- `/api/predictive-maintenance`
- `/api/batching`
- `/api/batching/transfer`

### 3.2 Core fulfillment system
The main operational domain should include:
- orders and order lines
- warehouse selection and validation
- stock availability checks
- free/reserved/picked inventory states
- persistent movement ledger
- staged tasks with durable IDs and timestamps
- deterministic allocation logic
- policy-based simulator execution

The implementation must model the following workflow:
- customer creates order
- order is validated against selected warehouse
- free stock is debited conservatively
- reservation is created
- tasks move through staged fulfillment states
- progress is persisted and visible to supervisor and admin views

### 3.3 Bazaar order intake flow
The Bazaar surface must feel like a customer-facing intake app:
- new multi-line order form
- warehouse selector
- delivery/service selection
- order review before submit
- accepted/rejected state with reasons
- retry or receipt history view

The app must support stable request identity and idempotent duplicate handling.

### 3.4 Persona and workflow system
The app must include demo personas that simulate role-driven workflows without real authentication.

Required personas:
- Customer / Bazaar user
- Order Fulfillment Supervisor
- Asset & Fleet Manager
- Admin / Reviewer

Each persona must see different action surfaces:
- customer: order submission, tracking, retry inspection
- supervisor: fulfillment monitoring, discrepancy handling, work approval
- fleet: readiness repair, failure/kill/recover simulation, charging state
- admin/reviewer: audit, KPI, comparison, model review, and config views

The repo uses a demo header approach (`X-Demo-Persona`-style behavior). The generated app should follow that pattern.

## 4. Required product surfaces

### 4.1 Main warehouse app (`/`)
This is the primary operational dashboard.

Required features:
- fulfillment overview
- inventory and reservations summary
- task board or work summary
- exception / discrepancy indicators
- filters by warehouse, status, task type, and robot
- role-aware actions

### 4.2 FDE Bazaar app (`/fde-bazaar/`)
This should act like the customer-facing order app.

Required features:
- order form
- warehouse mapping and SKU selection
- order validation
- order receipt and history
- failed-order reason view
- retry flow for valid reattempts

### 4.3 Robot Fleet Simulator (`/robot-lifecycle/`)
This app should model the simulated robotic fleet.

Required features:
- robot inventory and readiness states
- battery and charging status
- simulated fail/kill/recover actions
- replacement candidates and eligibility checks
- fleet issue list and repair workflow

### 4.4 Transfer lab (`/robot-lifecycle/transfer-lab`)
This should be a compare-only workspace, not an operational executor.

Required features:
- frozen DC-01 snapshot
- eligible robot selection
- capacity and capability checks
- validate plan before acceptance
- compare outcomes without mutating fulfillment state
- reject invalid outputs

### 4.5 Client pitch app (`/docksight-client-pitch/`)
This is a presentation-only surface.

Required features:
- marketing/pitch deck view
- narrative and summary slides
- no operational state writes

## 5. Functional requirements

### 5.1 Order processing
The implementation must support:
- multi-line order creation
- warehouse decision and validation
- all-or-nothing acceptance within the selected warehouse
- stable request identity and duplicate suppression
- delivery/retry tracking
- failure reporting with specific reasons

### 5.2 Inventory accounting
The app must enforce conservative inventory logic.

Required rules:
- maintain separate free, reserved, and picked quantities
- use a conservative source minimum rather than optimistic assumed stock
- prevent double-debit on pick or movement replay
- store movement IDs and state transitions durably
- keep evidence imports immutable

### 5.3 Task lifecycle
The app must support tasks moving through a persisted lifecycle, such as:
- queued
- claimed
- picked
- moved
- packed
- staged
- completed

Task status must be deterministic and restart-safe.

### 5.4 Fleet disruption handling
The app must simulate:
- failure blocks
- kill and replacement logic
- recovery state transitions
- battery drain and charging thresholds
- maintenance readiness failure
- claim exclusivity and safe replacement windows

### 5.5 Advisory-only comparison flows
The app must contain transfer and batching functionality that is computationally rich but never writes to live fulfillment operations.

Required behavior:
- plan suggestions are validated before acceptance
- invalid plans are rejected without persistence
- compare-only results are displayed
- no direct execution of planner output against live warehouse tasks

### 5.6 Reporting surfaces
The app must expose read-only reporting for:
- monthly KPI summaries
- labelled synthetic historical scenario data
- forecast comparisons and low-stock indicators
- maintenance model metadata and scorecards

These must be clearly marked as demo or synthetic data.

## 6. UI and UX requirements

The UI should feel like a polished local warehouse operations product, not a generic admin dashboard.

### 6.1 Layout style
Use a modern local demo aesthetic with:
- cards for operational metrics
- clear status badges
- tables for order, task, and robot data
- side navigation for app surfaces
- contextual action buttons for roles
- concise labels explaining demo-only assumptions

### 6.2 Screen requirements
The generated app should include these screens or views:
1. Home dashboard
2. new order form
3. order detail / receipt view
4. inventory overview
5. fulfillment board
6. fleet lifecycle dashboard
7. transfer compare lab
8. KPI dashboard
9. predictive-maintenance overview
10. admin / audit view

### 6.3 UX constraints
- no live production UI assumptions
- no real auth flow
- no external system actions
- no misleading “live robotic control” labels
- explicit synthetic/demo marking everywhere appropriate
- local-first UI behavior with immediate state changes and validation feedback

## 7. Data model requirements

Core entities must include:
- Warehouse
- SKU
- ProductCatalog
- Order
- OrderLine
- Reservation
- SubOrder
- Movement
- Task
- Robot
- ControlAsset
- Issue
- Intervention
- ForecastRun
- KPIResult
- ModelCard
- TransferScenario
- BatchScenario

Persistence must include:
- SQLite storage for demo data
- separate mutable app state vs immutable evidence files
- request IDs and idempotency keys
- movement IDs for ledger integrity
- assignment tokens and revision markers

## 8. Endpoint design expectations

The generated app should include route patterns similar to:

- `POST /api/bazaar/orders`
- `GET /api/bazaar/orders`
- `GET /api/bazaar/orders/{id}`
- `POST /api/fulfillment/orders`
- `GET /api/fulfillment/orders`
- `GET /api/fulfillment/resources/robots`
- `GET /api/fulfillment/lifecycle`
- `POST /api/fulfillment/lifecycle/tasks/{id}/kill`
- `POST /api/fulfillment/resources/{id}/recover`
- `GET /api/personas/workspace`
- `GET /api/batching/transfer`
- `POST /api/batching/transfer/validate`
- `GET /api/monthly-kpis`
- `GET /api/predictive-maintenance`

The exact implementation names may vary, but the logic and route grouping must remain consistent with this repo’s architecture.

## 9. Non-functional requirements

### 9.1 Local deployment
The app must run locally from the repo and rely only on loopback configuration.

### 9.2 Determinism
Policies and task assignment must be deterministic and auditable.

### 9.3 Auditability
The app must preserve timestamps, movement records, claims, intervention data, and review evidence.

### 9.4 Demo safety
The app must maintain a clear statement that it is a synthetic warehouse simulation.

## 10. Acceptance criteria for AI-generated code

The generated implementation is acceptable if it satisfies all of the following:

1. It runs locally from the repository without external service dependencies.
2. It serves multiple frontend apps from one origin.
3. It supports Bazaar order creation and warehouse-based acceptance.
4. It enforces conservative inventory accounting and prevents double-debit behavior.
5. It includes a simulated lifecycle and fleet disruption workflow.
6. It has role-aware interfaces for supervisor, fleet, and admin/reviewer personas.
7. It includes a deterministic transfer/batching compare flow that does not affect live fulfillment.
8. It includes KPI and predictive-maintenance surfaces with clearly labeled synthetic data.
9. It uses SQLite and local state patterns consistent with the repo.
10. It clearly communicates that the product is a local demo, not a real warehouse control system.

## 11. AI generation guidance

An AI agent generating code from this PRD should prioritize the implementation in this order:

### Phase 1: core backend
- FastAPI app scaffolding
- SQLite schema design
- order intake and idempotency logic
- reservation and movement ledger
- task lifecycle state machine

### Phase 2: operational UI
- main dashboard
- Order creation page
- order detail / history pages
- inventory and reservations views
- task board or fulfillment status page

### Phase 3: fleet and exception workflow
- robot state view
- fail/kill/recover workflow
- battery and charging simulation
- repair/readiness actions
- persona-based actions

### Phase 4: transfer and reporting
- transfer compare lab
- batching sandbox logic
- monthly KPI cards
- predictive maintenance viewer

### Phase 5: packaging and running locally
- launcher script and local server binding
- route mounting for static apps
- synthetic/demo labeling
- readiness check for loopback-only deployment

## 12. Definition of done

The resulting product should feel like a local warehouse fulfillment simulator with which a stakeholder can understand the operational story and user flow, even though it is not a production-ready operational system. It should strongly resemble the repo’s existing architecture and functionality, including:
- order intake workflow,
- deterministic fulfillment simulation,
- fleet lifecycle management,
- read-only comparison and KPI reporting,
- and a multi-app local product experience.

## 13. Final AI prompt

Use the following prompt for the code-generation agent:

> Build a repository-aligned warehouse fulfillment control-tower simulator in Python FastAPI and React TypeScript. The app must mirror this repo’s architecture: a single local loopback server launches multiple frontend apps and a shared backend under /api. Implement a Bazarr-style order intake flow, conservative inventory reservation logic, lifecycle-based fulfillment task states, a fleet simulator for robot failure/recovery/charging, role-based persona workspaces, and read-only KPI/predictive-maintenance surfaces. Keep all execution simulated and local. Do not connect to real warehouses, robots, or external systems. Include a transfer lab and batching sandbox that are validation-gated and compare-only, not live operational execution. Use SQLite for local persistent state and mount the frontend surfaces as separate apps under /, /fde-bazaar, /robot-lifecycle, and /docksight-client-pitch. The result should be functionally and visually similar to the current repo’s demo product, not a generic CRUD app.

This version is intentionally repo-specific and implementation-oriented so it can guide an AI agent toward producing output similar to the existing project’s functionality and UI.
