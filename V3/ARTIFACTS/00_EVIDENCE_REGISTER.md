# Repo 3 evidence register

**Source archive:** `C:\Users\Administrator\Downloads\Application Code Package\Draft\Warehouse-Local-Windows.zip`  
**Archive root:** `warehouse-local/`  
**Assessment date:** 2026-09-22

## Evidence levels

| Level | Meaning |
|---|---|
| E1 | Directly inspected code, configuration, schema or packaged data |
| E2 | Directly executed in this review environment |
| E3 | Repo 3's packaged report of a prior execution |
| E4 | Design/document statement without matching execution evidence |

## Primary evidence

| Evidence | Level | What it supports | Limitation |
|---|---|---|---|
| `replit.md` | E1 | Product surfaces, stack, role boundaries, simulation posture | Living project narrative, not an independent test |
| `artifacts/api-server/CONTROL_TOWER.md` | E1 | As-built PRD, accounting rules, ADRs and verification record | Combines specification and reported evidence |
| `artifacts/api-server/fulfillment_api.py` | E1 | Transactional API, source overlays, inventory, executor and forecast routes | Large single module; inspection is not runtime proof |
| `artifacts/api-server/fulfillment_v2.py` | E1 | Current per-SKU policy and scheduling | Simulated only |
| `artifacts/api-server/persona_api.py` | E1 | Persona/intervention controls and audit | Demo header is not authentication |
| `artifacts/api-server/robot_lifecycle.py` and `lifecycle_api.py` | E1 | Charging, failure, kill, recovery and assignment APIs | Simulated resources only |
| `artifacts/api-server/bazaar_api.py` | E1 | Durable order intake/outbox and retry | Same local gateway; no external service assurance |
| `artifacts/api-server/replay_*` | E1 | Isolated replay and merge tooling | Several replay payloads are not in this ZIP |
| `lib/api-spec/openapi.yaml` | E1 | Generated-client contract for selected public APIs | Does not describe every FastAPI route |
| `local_server.py` | E1 | Loopback launcher and three static web apps | No TLS/auth; local only |
| `artifacts/*/src` | E1 | Core, Bazaar and Fleet web applications | Not freshly built here |
| `.local/fulfillment.sqlite`, `.local/bazaar.sqlite` | E1 | Packaged persistent demo state | Snapshot, not production telemetry |
| `TEST_REPORT.md` | E3 | Prior Linux build, HTTP, browser, DB and 25-test results | Not independently rerun on this Windows host |
| `CONTROL_TOWER.md` verification record | E3 | Prior 73-test and browser-flow results | Reported by the package |
| Python compile check | E2 | `artifacts/api-server` source parses/compiles | Does not execute behavior |
| SHA-256 manifest check | E2 | 516 present files match hashes | 45 manifest entries are absent |

## Fresh checks in this review

| Check | Result |
|---|---|
| `python -m compileall -q artifacts/api-server` | **PASS** |
| `python -m pytest artifacts/api-server -q` | **NOT RUN** — `pytest` not installed |
| `pnpm` typecheck/build | **NOT RUN** — `pnpm` not installed |
| `PACKAGE_FILES_SHA256.json` verification | 516 present files matched; 45 missing; 0 mismatched |

The 45 missing manifest files are backup and replay payloads under
`artifacts/api-server/.local/backups/` and `.local/replays/`. Repo 3's own
`TEST_REPORT.md` says the complete tested payload was split into three ZIPs.
Therefore this named ZIP is treated as the runnable Repo 3 package, not as the
complete evidence bundle.

## V2 comparison evidence

| V2 file | Use |
|---|---|
| `..\..\V2\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2\discovery\FDE_OM21_SPINE.md` | V2 operating-model boundary and OM 17–21 deferral |
| `..\..\V2\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2\TRACEABILITY_MATRIX.md` | V2 requirements, evals and residual gaps |
| `..\..\V2\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2\specs\adr\ADR-001-solution-selection.md` | V2 deterministic Option A decision |
| `..\..\V2\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2\specs\adr\ADR-002-llm-off-write-path.md` | V2 no-LLM/write-path decision |
| `..\..\V2\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2\discovery\15_90_DAY_ROADMAP.md` | Repo 3 candidate themes and explicit future boundary |

## Claims that must not be inferred

- “Updated” does not mean production-approved.
- Persistent simulated execution does not mean live robot execution.
- Persona checks do not mean authentication or production RBAC.
- Statistical forecasts do not mean AI/ML.
- Source correction in app-owned SQLite does not mean an external WMS/ERP write.
- Packaged test reports do not replace target-environment reruns.
- Local replay does not establish live operational resilience or business value.
