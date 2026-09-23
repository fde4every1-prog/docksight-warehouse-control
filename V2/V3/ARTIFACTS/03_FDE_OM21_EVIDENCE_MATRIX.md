# Repo 3 — AI FDE Operating Model 21 evidence matrix

## Verdict

Repo 3 extends the V2 synthetic proof into a durable local product simulation.
It strengthens OM 9–16 and supplies limited local evidence related to OM 17–18.
It does **not** establish customer deployment, production monitoring, realized
value, AIMS operation or retirement. OM 17–21 are therefore not “complete.”

The complete OM 1–16 evidence spine remains in the separate V2 repository in
this workspace. Repo3's embedded `brownfield/` folder is a trimmed, read-only
baseline for legacy inspection; it is not a copy of V2's complete discovery,
specification, hard-gate and EVAL evidence.

| Band | Repo 3 result |
|---|---|
| OM 1–8 — Discover and select | **Inherited from V2; product scope evolved** |
| OM 9–16 — Design, engineer, assure, operate locally | **Strong for local simulation** |
| OM 17 — Deploy progressively | **PARTIAL: local package only** |
| OM 18 — Monitor resilience | **PARTIAL: simulator state/replay, not production** |
| OM 19 — Prove value | **NOT PROVEN** |
| OM 20 — AIMS lifecycle | **NOT PROVEN / N/A until governed AI system** |
| OM 21 — Retire and reusable IP | **PARTIAL: packaging/reuse; no retirement exercise** |

## Phase-by-phase evidence

| OM | Workflow | Repo 3 evidence | Status |
|---:|---|---|---|
| 1 | Mandate and immersion | V2 charter/evidence inherited; Repo 3 package reframes product as local fulfillment simulator | **PARTIAL update** |
| 2 | Current process/architecture | As-built surfaces documented in `replit.md`, `CONTROL_TOWER.md`, code and this pack | **PASS, local** |
| 3 | Problem, RCA and value | V2 baseline inherited; V3 solves customer-to-task persistence but has no approved benefit baseline | **PARTIAL** |
| 4 | Regulation/use-case qualification | Simulation/no-OT boundary explicit; no customer legal/regulatory assessment | **PARTIAL** |
| 5 | Domain model | Orders, sub-orders, allocations, tasks, movements, resources, interventions and forecasts encoded | **PASS** |
| 6 | Data/knowledge readiness | 19 source datasets, source audit, conservative quantities and lineage boundaries | **PASS, synthetic** |
| 7 | Evals, impact and risk | Large regression suite and scenario tests reported; production impact and independent assurance absent | **PARTIAL** |
| 8 | Options and selection | Deterministic/no-ML approach preserved; Repo 3 decisions reconstructed as ADRs | **PASS** |
| 9 | Information architecture | Immutable evidence, separate SQLite state, movement ledger, outbox, replay and forecasts | **PASS** |
| 10 | Application architecture | Three SPAs, shared FastAPI gateway, typed selected API, local launcher | **PASS, local** |
| 11 | Agentic architecture | No agent/LLM runtime; deterministic policy remains suitable | **N/A by decision** |
| 12 | Security/guardrails/suppliers | Validation, revisions, claims, fail-closed readiness; authentication and network controls absent | **PARTIAL / demo only** |
| 13 | ADRs/delivery specification | `CONTROL_TOWER.md`, this PRD and V3 ADR set | **PASS** |
| 14 | Engineer | Python/TypeScript implementation, tests, prebuilt assets and Windows package | **PASS, package scope** |
| 15 | Evaluate/attack/assure | Prior 73-test and browser evidence; package report adds 25 focused tests; fresh Windows rerun absent | **PARTIAL** |
| 16 | Operations/recovery/evidence | Local setup, backup/replay/reset/forecast maintenance, restart-aware scheduler | **PASS, local demo** |
| 17 | Progressive deployment | Loopback Windows package and prior extracted-package smoke test only | **PARTIAL** |
| 18 | Operational resilience | Persistent clocks, idempotency, replay and recovery simulation; no service SLO/on-call/production chaos | **PARTIAL** |
| 19 | Prove value | Data can support lead-time/hold metrics; no controlled before/after or financial value proof | **NOT PROVEN** |
| 20 | AIMS lifecycle | No deployed AI model and no AIMS/CAPA/audit lifecycle | **N/A / NOT PROVEN** |
| 21 | Retire and reusable IP | Portable package, OpenAPI and artifacts are reusable; no production decommission/credential revocation | **PARTIAL** |

## What Repo 3 adds beyond V2

- Durable customer order intake and retry/outbox behavior.
- Transactional reservations and quantity-movement ledger.
- Staged, restart-aware simulated execution.
- Per-SKU policy-v2 allocation and partial multi-SKU fulfillment.
- Core, Bazaar and Fleet web applications.
- Persona-specific exception and correction workflows.
- Resource failure, replacement, recovery, battery and charging simulation.
- Statistical demand forecast and saved explanation data.
- Offline replay, backup and maintenance utilities.
- Local Windows package and persistent demo state.

## What remains outside the evidence

- Real field immersion and current customer stakeholder acceptance.
- A Repo3 rerun of V2's named G1–G8 and EVAL-001–022 against the new simulated
  executor; V2 results cannot be transferred automatically to changed code.
- Real inventory, robot, topology, rates or sensor truth.
- Production IAM, security testing and data protection.
- Live external integration and safe command authority.
- Progressive customer rollout or rollback.
- Service-level monitoring, drift, cost and incident operations.
- Demonstrated operational or financial value.
- Governed AI lifecycle.
- End-of-life and retirement execution.

## FDE stop gates

1. **Do not call Repo 3 production-ready.**
2. **Do not expose the package beyond loopback under the current authority model.**
3. **Do not connect any endpoint to physical or external write paths.**
4. **Do not relabel the forecast as AI/ML.**
5. **Do not mark OM 17–21 complete from local simulation evidence.**
