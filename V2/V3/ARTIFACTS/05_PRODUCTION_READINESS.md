# Repo 3 production-readiness review

## Decision

| Release target | Decision |
|---|---|
| Isolated local demonstration with synthetic data | **CONDITIONAL GO** |
| Shared internal network pilot | **NO-GO** |
| Customer production fulfillment system | **NO-GO** |
| Live WMS/FMS/PLC/robot write path | **PROHIBITED** |

The conditional local-demo GO requires a target-machine dependency install,
test rerun, loopback binding and integrity check. Repo 3's prior report is useful
evidence but is not a substitute for executing the supplied Windows package.

## Strengths

- Explicit simulation and no-physical-control statements.
- Deterministic policies rather than opaque model decisions.
- Immutable inherited evidence and separate mutable state.
- Transactional acceptance/accounting and durable movement identities.
- Restart-aware task clocks and resource claims.
- Idempotent intake and retry state.
- Rich role-specific audit and correction records.
- Failure, replacement, recovery, charging and replay scenarios.
- Packaged tests, browser checks and database integrity report.

## P0 blockers for any shared or production use

| ID | Blocker | Evidence | Required disposition |
|---|---|---|---|
| P0-01 | No authentication or trusted identity | Caller sets `X-Demo-Persona` | Implement production IAM/session |
| P0-02 | Incomplete authorization on mutating routes | Orders/scenarios and `assign-tasks` are not fully role-guarded | Deny by default; policy enforcement tests |
| P0-03 | No CSRF/origin protection model | Same-origin local demo only | Threat model and controls |
| P0-04 | No real external contract or safety case | No WMS/FMS/OT adapter by design | Separate field engagement |
| P0-05 | Physical truth and feasibility absent | Synthetic weights/topology/timing/state | Integrate verified sources and site validation |
| P0-06 | Single-process SQLite | Local package architecture | Production datastore/HA decision |
| P0-07 | No production observability/SLO/on-call | No service metrics/error budget | Operability and incident program |
| P0-08 | No independent security/assurance evidence | Regression evidence is functional | Security testing and independent review |
| P0-09 | Delivery manifest scope ambiguous | 45 backup/replay entries absent | Supply all archives or scoped manifest |
| P0-10 | Target Windows verification incomplete | Tools/dependencies unavailable here | Repeatable clean-host CI/package test |

## P1 hardening gaps

- Split the oversized API facade into explicit application/domain adapters.
- Generate a complete OpenAPI contract for all supported runtime routes.
- Define database migration versioning and rollback.
- Automate verified backup/restore, including WAL/SHM handling.
- Add structured logs, metrics, traces and correlation IDs.
- Add rate limiting, body limits and resource-exhaustion tests.
- Add dependency/SBOM/license/vulnerability evidence.
- Add secrets/configuration policy and environment validation.
- Add data retention, privacy and audit-export policy.
- Add multi-process/concurrency/load/long-duration tests.
- Add explicit business KPI baselines and targets.
- Resolve policy-v1 compatibility retirement criteria.

## Threat summary

| Threat | Current control | Residual |
|---|---|---|
| Caller impersonates role | Loopback/trusted local use | Critical if network-exposed |
| Unauthorized order/config/scenario mutation | Some route-level demo checks | High |
| Duplicate request/movement | Idempotency keys and movement IDs | Lower, test rerun required |
| Stale concurrent correction | Revision/fingerprint/token checks | Moderate |
| Source evidence overwritten | Separate app stores | Low in normal flow |
| SQLite corruption/process interruption | Transactions and backups | Recovery drill not independently proven |
| Spreadsheet formula injection | Escaped generated export | Low for that export |
| Unsafe resource assignment | Explicit readiness/claim rules | Physical suitability still unknown |
| Misleading AI/forecast claim | Docs identify statistical baseline | Governance/UI consistency required |
| Accidental physical integration | No adapter exists | Must remain a hard release gate |

## Release gates

### Gate L — local demo

- [ ] Create isolated Python 3.11 environment and install pinned requirements.
- [ ] Rerun backend tests on temporary databases.
- [ ] Rerun frontend typecheck/build or verify shipped assets from clean package.
- [ ] Run active SQLite integrity and foreign-key checks.
- [ ] Confirm launcher binds only to `127.0.0.1`.
- [ ] Confirm synthetic data classification.
- [ ] Reconcile manifest scope.

### Gate S — shared application

All Gate L items plus:

- [ ] Authenticated identities and server-side RBAC.
- [ ] Authorization coverage for every mutating route.
- [ ] CSRF/TLS/network/secrets/security controls.
- [ ] Production database/migrations/backups.
- [ ] Observability, alerting, SLO and incident runbooks.
- [ ] Load, concurrency, recovery and security testing.
- [ ] Privacy, retention and audit requirements.

### Gate P — production/physical integration

All Gate S items plus:

- [ ] Site mandate, hazard analysis and independently approved safety case.
- [ ] Verified topology, weights, capacities, state freshness and command authority.
- [ ] Versioned external contracts and idempotent command/result protocol.
- [ ] Shadow mode, canary, rollback and manual fallback.
- [ ] Independent TEVV and operational acceptance.
- [ ] Real before/after value measurement.

## Residual claims

- **Local deterministic simulator:** supported.
- **AI-native autonomous control center:** not supported as a runtime claim.
- **Production-ready warehouse platform:** not supported.
- **Modernization complete:** not supported.
- **Safe live robot control:** not supported and outside current authority.
