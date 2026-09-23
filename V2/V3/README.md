# V3 — Repo 3 evidence pack

**Prepared:** 2026-09-22  
**Repo 3 source:** `C:\Users\Administrator\Downloads\Application Code Package\Draft\Warehouse-Local-Windows.zip`  
**Comparison baseline:** `..\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2`

## Purpose

This folder is the documentation baseline for the supplied Repo 3 package. It
keeps V2 unchanged so both versions can be reviewed side by side.

Repo 3 is a materially larger **local warehouse fulfillment simulator**. It adds
customer order intake, durable reservations and task execution, persona
workspaces, intervention workflows, resource lifecycle simulation, forecasts,
replay evidence, three web applications, and Windows packaging.

It is **not** a customer-production robot control system. The code remains a
loopback, unauthenticated/shared demo using synthetic data and simulated
resources. It has no AI model, no live WMS/FMS/PLC integration, and no physical
actuation.

## Document set

| Document | Purpose |
|---|---|
| [PRD.md](PRD.md) | Product requirements reconstructed from the as-built Repo 3 |
| [ARTIFACTS/00_EVIDENCE_REGISTER.md](ARTIFACTS/00_EVIDENCE_REGISTER.md) | Source provenance and evidence confidence |
| [ARTIFACTS/01_AS_BUILT_ARCHITECTURE.md](ARTIFACTS/01_AS_BUILT_ARCHITECTURE.md) | C4-style runtime, boundaries, data and API surfaces |
| [ARTIFACTS/02_DOMAIN_WORKFLOWS_AND_CONTROLS.md](ARTIFACTS/02_DOMAIN_WORKFLOWS_AND_CONTROLS.md) | Domain model, key journeys, authority and controls |
| [ARTIFACTS/03_FDE_OM21_EVIDENCE_MATRIX.md](ARTIFACTS/03_FDE_OM21_EVIDENCE_MATRIX.md) | AI FDE operating-model coverage and honest gaps |
| [ARTIFACTS/04_REQUIREMENTS_TRACEABILITY.md](ARTIFACTS/04_REQUIREMENTS_TRACEABILITY.md) | Requirement-to-code-to-test traceability |
| [ARTIFACTS/05_PRODUCTION_READINESS.md](ARTIFACTS/05_PRODUCTION_READINESS.md) | Risks, release gates and production NO-GO |
| [ARTIFACTS/06_V2_V3_COMPARISON.md](ARTIFACTS/06_V2_V3_COMPARISON.md) | Direct V2 versus V3 comparison |
| [ARTIFACTS/07_KEY_ARTIFACT_LOCATOR.md](ARTIFACTS/07_KEY_ARTIFACT_LOCATOR.md) | Where C4, ubiquitous language, evals, and risk/resilience live |
| [ARTIFACTS/08_DOMAIN_ER_DIAGRAM.md](ARTIFACTS/08_DOMAIN_ER_DIAGRAM.md) | Knowledge-sharing ER of the warehouse domain (entities, keys, relationships) |
| [ADRs/ADR-001-local-modular-monolith.md](ADRs/ADR-001-local-modular-monolith.md) | Local modular monolith and shared gateway |
| [ADRs/ADR-002-deterministic-simulation-no-ai-or-ot.md](ADRs/ADR-002-deterministic-simulation-no-ai-or-ot.md) | Deterministic simulation; no AI or physical control |
| [ADRs/ADR-003-immutable-brownfield-separate-state.md](ADRs/ADR-003-immutable-brownfield-separate-state.md) | Preserve source evidence; separate mutable state |
| [ADRs/ADR-004-transactional-ledger-and-idempotent-intake.md](ADRs/ADR-004-transactional-ledger-and-idempotent-intake.md) | Transactional stock ledger and durable intake |
| [ADRs/ADR-005-policy-v2-allocation-and-scheduling.md](ADRs/ADR-005-policy-v2-allocation-and-scheduling.md) | Per-SKU allocation and deterministic scheduling |
| [ADRs/ADR-006-demo-personas-loopback-boundary.md](ADRs/ADR-006-demo-personas-loopback-boundary.md) | Demo personas are not authentication |

## V3 verdict

| Claim | Verdict |
|---|---|
| Repo 3 local package exists and is materially beyond V2 | **PASS** |
| Deterministic end-to-end fulfillment simulation | **PASS, subject to packaged evidence** |
| Local persistence and restart-aware execution | **PASS, as-built design** |
| AI-native or agentic runtime | **NO — not implemented and not required** |
| Live warehouse integration or physical control | **NO** |
| Secure multi-user application | **NO** |
| Production deployment, monitoring and value proof | **NOT PROVEN** |
| Full OM 17–21 customer lifecycle | **PARTIAL / DEFERRED** |

## Evidence notes

- Repo 3's `TEST_REPORT.md` reports successful Linux builds, browser checks,
  database integrity checks and focused backend tests. This is retained as
  **packaged supplier evidence**, not presented as a fresh Windows rerun.
- A fresh Python compile check over `artifacts/api-server` passed.
- Fresh backend tests were not run because this machine does not currently have
  `pytest`; `pnpm` is also unavailable for a fresh frontend build.
- `PACKAGE_FILES_SHA256.json` contains 561 entries. Of those, 516 files in the
  supplied ZIP matched and 45 listed backup/replay payloads were absent. The
  package report explains that the complete tested payload was split across
  three archives; only the named ZIP was supplied for this V3 review.

## Status language

- **PASS** — direct code, data or test evidence supports the scoped claim.
- **PARTIAL** — some implementation exists, but the broader claim is not shown.
- **NOT PROVEN** — evidence is absent or was not independently rerun.
- **NO-GO** — a release or authority boundary prohibits the claim/action.
