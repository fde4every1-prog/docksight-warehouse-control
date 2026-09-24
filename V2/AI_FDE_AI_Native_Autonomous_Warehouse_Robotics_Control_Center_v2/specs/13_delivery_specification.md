# 13 — Delivery specification (OM 13)

**FDE OM:** 13 — Approve ADRs and delivery specification  
**Date:** 2026-09-18  
**ADRs:** `specs/adr/ADR-001-solution-selection.md`, `ADR-002-llm-off-write-path.md` (Accepted).  
**Trace:** `TRACEABILITY_MATRIX.md`. **Ready/Done:** `DEFINITION_OF_READY.md`, `DEFINITION_OF_DONE.md`.

This is the **build-ready spec for the virtual increment**, not a customer go-live pack.

---

## Approved baseline

| Item | Pointer |
|---|---|
| C4 target | `specs/05_target_c4.md` |
| C4 as-built | `specs/14_as_built_c4.md` |
| API | `specs/05_api_contracts.md` + `api.py` |
| Data | `specs/02_data_contracts.md` |
| Gates | `specs/06_hard_gates_and_authority.md` |
| Evals | `evals/golden_cases_repo2.jsonl`, harness |
| UI | GET `/` dashboard |

---

## NFRs (virtual)

| NFR | Requirement | Evidence |
|---|---|---|
| Safety | `physical_control: disabled`; executor `applied=false` | `/health`, tests |
| Integrity | Do not clean `data/` | DoD |
| Determinism | Same fixtures ⇒ same eligibility | pytest |
| Authority | Untrusted text cannot flip G1/G2 | EVAL-020 |
| Observability | Conflicts, gates, abstains | `evals/observability.md` |
| Portability | Python 3.11+ local | `pyproject.toml` |
| Performance | Not a KPI; snapshot diagnostics may take seconds | Acceptable for demo |
| Availability | Single local process | No SLA |
| Cost | No token spend on write path | No LLM |

---

## Telemetry / logging

`evals/observability.md`. No LLM traces. Decision trace shape is mandatory for evals.

Rollback: **git revert** of the increment. No OT rollback (nothing applied). Disable flag is the code default, not a feature toggle to enable.

---

## Evaluation cases

EVAL-001–022 + Prompt 15 simultaneous pressure. Threshold: `must_not` 100% on UC-1; unsafe expired-cert assign = 0.

---

## Backlog (explicitly not this increment)

| Item | Why later |
|---|---|
| Wire `/robots/{id}` through IdentityResolver | GAP-3 |
| T3 Approval store | GAP-1 |
| Command ids | GAP-2 |
| CI on a shared remote | workflow file exists; remote optional |
| UC-2 copilot | Optional, default off |
| OM 17–21 | `discovery/17_21_LIFECYCLE_DEFERRED.md` |

---

## Agent specifications

**None.** See `specs/11_agent_suitability.md`.
