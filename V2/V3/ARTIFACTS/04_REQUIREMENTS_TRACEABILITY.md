# Repo 3 requirements traceability

## Product requirements

| ID | Requirement | Implementation evidence | Verification evidence | Status |
|---|---|---|---|---|
| R3-01 | Separate Bazaar order entry | `artifacts/fde-bazaar`; `bazaar_api.py` | Bazaar tests/report | **PASS, packaged** |
| R3-02 | Durable delivery retry/outbox | `bazaar_api.py`; Bazaar SQLite | Intake/idempotency tests | **PASS, packaged** |
| R3-03 | Stable request identity | `bazaar_api.py`; `fulfillment_api.py` | Duplicate/body-change tests | **PASS, packaged** |
| R3-04 | Selected-warehouse atomic acceptance | `fulfillment_v2.py` | Policy-v2 tests and browser flow | **PASS, packaged** |
| R3-05 | Conservative source-minimum stock | `fulfillment_v2.py`; inventory schema | Boundary/accounting tests | **PASS, packaged** |
| R3-06 | No double debit at Pick | movement ledger; order progress | 100→90 and 60+30 cases reported | **PASS, packaged** |
| R3-07 | Per-SKU staged work | policy-v2 task creation | lifecycle regressions | **PASS, packaged** |
| R3-08 | Deterministic resource eligibility | readiness and selector modules | fulfillment/fleet tests | **PASS, packaged** |
| R3-09 | Restart-safe task clocks/effects | persisted due times, claims, movement IDs | recovery tests reported | **PASS, packaged** |
| R3-10 | Supervisor exception workflow | `persona_api.py`; Core UI | persona tests/browser flow | **PASS, packaged** |
| R3-11 | Fleet repair and recovery | `fleet_repair.py`; lifecycle modules | fleet/lifecycle tests | **PASS, packaged** |
| R3-12 | Battery/charging lifecycle | `robot_lifecycle.py` | lifecycle tests and UI test config | **PASS, packaged** |
| R3-13 | Admin policy/audit/config | `persona_api.py`; config routes | role tests | **PASS, packaged** |
| R3-14 | Immutable brownfield evidence | separate source root and databases | code inspection | **PASS** |
| R3-15 | Transparent demand forecast | `demand_forecast.py` | 25 focused package tests | **PASS, packaged** |
| R3-16 | Legacy review without dispatch | `review_api.py` | pure adapter/code inspection | **PASS** |
| R3-17 | Isolated replay | `replay_runner.py`, `replay_api.py` | replay tests/report | **PARTIAL: payloads incomplete** |
| R3-18 | Local Windows package | PowerShell scripts, `local_server.py`, prebuilt apps | Prior Linux package test only | **PARTIAL** |
| R3-19 | No AI/agent dependency | dependency/code search | direct inspection | **PASS** |
| R3-20 | No physical/external actuation | simulation modules; no OT adapter | direct inspection/docs | **PASS for absence** |

## Safety and authority requirements

| ID | Requirement | Evidence | Status |
|---|---|---|---|
| SAFE-01 | Missing/blocking readiness evidence fails closed | `fleet_readiness.py`, policy docs/tests | **PASS, simulator** |
| SAFE-02 | Exclusive resource claims | fulfillment/lifecycle state | **PASS, packaged** |
| SAFE-03 | Failure/recovery cannot duplicate completed work | movement IDs and recovery tests | **PASS, packaged** |
| SAFE-04 | Source corrections preserve protected accounting | persona/inventory correction code | **PASS, packaged** |
| SAFE-05 | No real command adapter | architecture/code search | **PASS** |
| SAFE-06 | Shared/network mutation requires authenticated authorization | Not implemented | **FAIL for production** |
| SAFE-07 | Physical feasibility/certification | No real evidence | **NOT PROVEN** |

## Non-functional requirements

| ID | Requirement | Evidence | Status |
|---|---|---|---|
| NFR-01 | Loopback default | `local_server.py` | **PASS** |
| NFR-02 | Atomic state transitions | SQLite transaction boundaries | **PASS, design/test report** |
| NFR-03 | Concurrency conflict detection | revisions/fingerprints/tokens | **PASS, local** |
| NFR-04 | Auditability | intervention events, movements, progress, replay | **PASS, local** |
| NFR-05 | Portability | Windows scripts and prebuilt assets | **PARTIAL: not rerun here** |
| NFR-06 | Performance at supplied catalog scale | Reported 9,360-row profiling | **PARTIAL: prior evidence** |
| NFR-07 | Availability/SLO | No production service data | **NOT PROVEN** |
| NFR-08 | Scalability/multi-instance | Single-process SQLite | **NOT PROVEN** |
| NFR-09 | Security | Caller-controlled personas and open mutations | **FAIL for shared use** |
| NFR-10 | Complete contract documentation | Runtime routes exceed selected OpenAPI | **PARTIAL** |

## Fresh review verification

| Check | Result |
|---|---|
| Python source compilation | **PASS** |
| Backend behavior rerun | **NOT RUN** — missing `pytest` |
| Frontend typecheck/build rerun | **NOT RUN** — missing `pnpm` |
| File hashes | 516 matched, 45 absent, 0 mismatched |

## Exit criteria before calling V3 independently verified on Windows

1. Install pinned Python dependencies in an isolated environment.
2. Run the focused and full backend suites against temporary databases.
3. Install the pinned pnpm toolchain and run typecheck/build.
4. Run lifecycle Playwright tests using a supported Chromium.
5. Start the extracted package on loopback and execute API/UI smoke journeys.
6. Run SQLite integrity and foreign-key checks on the supplied active stores.
7. Obtain the two companion evidence archives or regenerate the package manifest
   so the delivered archive and manifest have one unambiguous scope.
