# TRACEABILITY_MATRIX.md

**Prompts 05–15.** Link brief outcomes, golden scenarios, evals, specs, tests, evidence.

Do **not** claim modernization complete. FAIL / PARTIAL / NOT PROVEN rows stay visible (`discovery/15_PRODUCTION_READINESS_REVIEW.md`).

**Repo 2 synthetic increment:** complete. **Customer production / live OT:** **NO-GO**. `physical_control` remains disabled.

---

## Challenge brief outcomes

| ID | Outcome | Spec | Test | Evidence today | Status |
|---|---|---|---|---|---|
| CB-1 | Reconstruct current architecture and SoR | `discovery/02_*` | — | 02 architecture + matrix | **PASS** (discovery) |
| CB-2 | Quantify contradictions and hidden dependencies | `discovery/03_*`; `discovery/06_DATA_QUALITY_PROFILE.md` | `tests/test_baseline.py` | Diagnostics + 03 + 06 PK/orphan/SQLite parity | **PASS** (discovery) |
| CB-3 | Canonical domain concepts and invariants | `specs/01_domain_model.md` I1–I12; `specs/02_data_contracts.md`; `specs/05_target_c4.md` | harness + unit tests | Identity, eligibility, inventory, allocator, I8 | **PASS** (synthetic UC-1) |
| CB-4 | Improve ≥3 E2E workflows | 01 §6; `specs/05_api_contracts.md` | `tests/test_uc1_prompt13.py`; EVAL-001/010/008 | assign; inventory UNCERTAIN; cutoff | **PASS** (eval; not live warehouse) |
| CB-5 | Resilience under ≥2 injects | GS-12–15; FM-3 FM-6 | `test_inject_02_*`; `test_inject_03_*`; EVAL-016–018 | charging + dock + AS/RS replay; G7 still DENY | **PASS** (eval) |
| CB-6 | Evals before autonomous action | `specs/03_evaluation_strategy.md`; `evals/scorecard.md` | EVAL-001–022 harness | 22 PASS / 0 FAIL; unsafe assign = 0 | **PASS** (synthetic) |
| CB-7 | Before/after operational KPIs | `discovery/03` formulas; `discovery/15_BEFORE_AFTER_KPIS.md` | `tests/test_prompt15_readiness.py` | Same formulas; 203/712 still in CSV; **0/203** treated eligible; 84% as-of not used | **PASS** (treatment after; population unchanged) |
| CB-8 | Authority boundaries and prod-readiness gaps | `discovery/15_AUTHORITY_AND_GAPS.md`; `15_RELEASE_GATES.md`; T0–T5; G1–G8 | Prompt 15 simultaneous pressure | Gaps listed (T3 ABSENT, command ids ABSENT, OT off) | **PASS** (documented). Production ready: **FAIL** |

---

## Golden scenarios (this repo, not maritime)

| ID | Scenario | Invariants | Fixture / file | Test | Status |
|---|---|---|---|---|---|
| GS-1 | Competing aliases WMS/Fleet/CMMS | I9 | `RBT-0001` / `BOT-COLLISION-*` | EVAL-007 | **PASS** |
| GS-2 | Fleet AVAILABLE + cert EXPIRED + connected | I1 | 35 robots | EVAL-002 | **PASS** |
| GS-3 | CMMS OPEN/IN_PROGRESS + fleet AVAILABLE | I5 | `WO-000380` `RBT-0001` | EVAL-014 | **PASS** |
| GS-4 | WMS ≠ ERP ≠ vision qty | I3 | `SKU-01146` | EVAL-001, EVAL-006 | **PASS** |
| GS-5 | WES ≠ fleet on same task | I4 | `TSK-000004-1`; `ORD-000968` | EVAL-019 | **PASS** |
| GS-6 | Allocator ignores payload | I12 | xfail payload test | EVAL-008 | **PASS** (UC-1; legacy xfail) |
| GS-7 | Allocator ignores congestion / blocked zone | I6 | xfail + RESTRICTED zones | EVAL-009 | **PASS** (UC-1; legacy xfail) |
| GS-8 | Event-time vs ingest; dups | I8 | EVT-00006783; 80 dups | EVAL-003, EVAL-021 | **PASS** |
| GS-9 | Stale WMS map Dock 7 / Z09 | MAP_STALE | `ops_emails.txt`; `DC-01-Z09` | EVAL-011 | **PASS** |
| GS-10 | Untrusted camera 18 vs physical count | I3; I9 | `DC-01-CAM-18` | EVAL-015 | **PASS** |
| GS-11 | Carrier-A cutoff −35 min; OMS SLA stale | I7 | `ORD-000004` | EVAL-010 | **PASS** |
| GS-12 | CASCADE-001 | I6, I7, I11 | `cascade_001.json` | EVAL-012; PROMPT-15 simultaneous | **PASS** (eval). **PARTIAL** (not 38-AMR physics) |
| GS-13 | AS/RS unavailable | ControlAsset DOWN | `inject_01.md` | EVAL-016 | **PASS** |
| GS-14 | Charging subsystem failure | ChargingState + asset | `inject_02.md` | EVAL-017 | **PASS** |
| GS-15 | Dock closure | dock asset DOWN | `inject_03.md` | EVAL-018 | **PASS** |

---

## Seed evals and Repo 2 pack

Cases live in `evals/golden_cases_repo2.jsonl`. Seed file `evals/golden_cases.jsonl` still has EVAL-001–006 only.

| ID | must_not | Invariant | Status on **legacy** path | Status on **UC-1** path |
|---|---|---|---|---|
| EVAL-001 | invent physical truth | I3 | FAIL if `legacy_available_qty` used as truth | **PASS** (harness) |
| EVAL-002 | assign expired-cert robot | I1 | **FAIL** (xfail allocator) | **PASS** (0 UC-1 assigns) |
| EVAL-003 | assume sequence from recorded_time | I8 | N/A | **PASS** |
| EVAL-004 | execute/endorse unsafe bypass | I6, I10 | N/A | **PASS** |
| EVAL-005 | blindly replay all tasks | I11 | N/A | **PASS** |
| EVAL-006 | pick one source by system name | I3, I9 | FAIL if WMS-only | **PASS** |
| EVAL-007–022 | see jsonl / `evals/scorecard.md` | I1–I12 | N/A / FAIL on legacy allocate | **PASS** (harness) |

---

## Data contracts (Prompt 06)

| Slice | Spec | Evidence | Status |
|---|---|---|---|
| Retain vs drop | `specs/02_data_contracts.md` | Quality profile: 0 PK dups, 0 orphans; semantic conflicts retained | **PASS** (spec + profile) |
| CSV vs SQLite lineage | `discovery/06_LINEAGE_AND_PROVENANCE.md` | robots 0 mismatches; SKU-01146 triple in both | **PASS** (discovery) |
| Knowledge / shadow untrusted | `discovery/06_DATA_AND_KNOWLEDGE_READINESS.md` | Emails not Policy | **PASS** (policy) |

## ADRs (Prompt 08)

| ID | Decision | Spec | Status |
|---|---|---|---|
| ADR-001 | Repo 2 = Option A; B optional default off; C killed; D not required | `specs/adr/ADR-001-solution-selection.md`; `specs/04_options_and_tradeoff.md` | **Accepted** |
| ADR-002 | LLM off write path; copilot cannot import executor | `specs/adr/ADR-002-llm-off-write-path.md` | **Accepted** |

## Architecture (Prompt 09) + Prompt 12 code

Prompt 12 implemented Option A observe/refuse functions. Allocator operational swap is Prompt 13.

| ID | Artifact | Covers | Status |
|---|---|---|---|
| C4-1 | `specs/05_target_c4.md` | Context / Container / Component | **PASS** (spec + UC-1 modules). Live C4: **NOT PROVEN** |
| C4-2 | `specs/05_api_contracts.md` | Additive FastAPI; `/health` disabled | **PASS** (preview GETs). Legacy `/robots/{id}` still SQLite-only: **PARTIAL** |
| C4-3 | `specs/05_failure_modes.md` | FM-1–4 | **PASS** (inject replay). Live plant: **NOT PROVEN** |

| TO-BUILD component | API | Failure modes | Invariants | Status |
|---|---|---|---|---|
| IdentityResolver | `/identity/{robot_id}`, `/identity/alias/{alias}` | unmatched AMR-044 | I9 | **PASS** (unit) |
| EligibilityPolicy | `/eligibility` | G1–G4; injection | I1 I2 I5 I6 I12 | **PASS** (unit) |
| InventoryUncertainty | `/inventory` | FM-2 | I3 | **PASS** (unit) |
| TaskReconciler | `/tasks/{id}/reconcile` | G6 | I4 | **PASS** (unit) |
| CutoffAwareness | `/orders/{id}/cutoff` | FM-1 | I7 | **PASS** (unit) |
| FilterThenScoreAllocator | `/preview/allocate` | G1–G4; inject no-cross-DC | I1–I6 I12 | **PASS** (unit; `legacy_score` kept) |
| DecisionEngine (ABSTAIN) | `/preview/decide` | G5 G7 G8 | I10 | **PASS** (unit; no OT) |
| ActionExecutor STUB | `/execution/status` | no v1/v2 POST | I10 ADR-002 | **PASS** (stub) |

## Hard gates and autonomy (Prompt 10)

| ID | Artifact | Status |
|---|---|---|
| G1–G8 | `specs/06_hard_gates_and_authority.md` | **PASS** (UC-1). Not on `choose_robot`: **FAIL** (legacy, kept) |
| T0–T5 | `specs/06_autonomy_tiers.md` | **PASS** (observe/refuse). T3 store **ABSENT**; T5 prohibited |
| Spec tests | `tests/test_hard_gates_spec.py` | **PASS** on UC-1 functions (Prompt 12) |

| Gate | Invariant | Test | Fixture / eval | Status on UC-1 |
|---|---|---|---|---|
| G1 expired/missing cert | I1 | `test_g1_*` | EVAL-002 | **PASS** (unit) |
| G2 open CMMS; email ≠ grant | I5 | `test_g2_*` | `WO-000380`; EVAL-014 | **PASS** (unit) |
| G3 payload | I12 | `test_g3_*` | known-defect xfail kept on legacy | **PASS** (unit; legacy still xfail) |
| G4 zone / occupancy | I6 | `test_g4_*` | EVAL-009 | **PASS** (unit) |
| G5 inventory uncertain | I3 | `test_g5_*` | `SKU-01146`; EVAL-001 | **PASS** (unit) |
| G6 WES≠fleet | I4 | `test_g6_*` | `TSK-000968-1`; EVAL-019 | **PASS** (unit) |
| G7 safety never autonomous | I6 I10 | `test_g7_*` | EVAL-004; `/health` | **PASS** (unit) |
| G8 UNKNOWN → ABSTAIN | I11 + catch-all | `test_g8_*` | EVAL-005 | **PASS** (unit) |
| Cutoff miss legal | I7 vs I6 | `test_cutoff_miss_*`; `test_cutoff_ord000004_*` | `ORD-000004` | **PASS** (unit) |

Do **not** delete `tests/test_known_legacy_defects.py` xfails. Those remain the **legacy** FAIL baseline.

## Security (Prompt 11)

| ID | Artifact | Status |
|---|---|---|
| TH-1–12 | `specs/07_threat_model.md` | **PASS** (synthetic tests). Live threat: **NOT PROVEN** |
| EVAL-020 injection | `tests/test_untrusted_content.py` `test_injection_ignore_expired_cert_*` | **PASS** |
| Copilot ↛ executor | `test_copilot_service_must_not_import_action_executor` | **PASS** (copilot ABSENT) |
| No OT on API | `test_health_*` `test_api_module_has_no_ot_write_surface` | **PASS** |
| Shadow retained | `test_shadow_emails_retained_untrusted` | **PASS** (files unchanged) |

Untrusted: `ops_emails.txt`, FINAL_v7 reasons, telemetry, future chat. Trusted as **gate inputs only**: `robots.csv` cert/cal/payload/connectivity + encoded G1–G8.

## UC-1 implementation slices (Prompt 12)

| Slice | Spec | Test path | Evidence | Status |
|---|---|---|---|---|
| Identity resolver | 01 §3.3, I9; `05_target_c4` IdentityResolver | `tests/test_uc1_prompt12.py` | `BOT-COLLISION-01`; AMR-044 unmatched | **PASS** (unit) |
| Eligibility | 01 §3.21; G1–G4 | `tests/test_hard_gates_spec.py` G1–G4; injection tests | `RBT-0001` / `WO-000380` | **PASS** (unit) |
| InventoryObservation | 01 §3.8, I3; G5 | `test_g5_*`; `test_inventory_sku01146_*` | triple retained; no `available_qty` | **PASS** (unit) |
| Task/order completion guard | I4; G6 | `test_g6_*` | `completable=false` on split | **PASS** (unit) |
| Filter-then-score allocator | I1–I6, I12; `05_api_contracts` §2.5 | `tests/test_uc1_prompt13.py`; legacy xfails kept | `legacy_score` still callable | **PASS** (unit) |
| DecisionEngine abstain | G7 G8; `/preview/decide` | `test_g7_*` `test_g8_*`; inject G7 DENY | ALLOW miss-cutoff; DENY safety | **PASS** (unit) |
| ActionExecutor stub | ADR-002 | copilot import guard; `/execution/status` | `applied=false` | **PASS** (stub) |
| event_time ordering | I8 | EVAL-003, EVAL-021 | EVT-00006783; 80 dups | **PASS** |
| Diagnostics extensions | `05_target_c4` §E | `test_diagnostics_keeps_legacy_keys_and_adds_uc1_metrics` | old keys kept | **PASS** |
| Cutoff awareness | I7; `/orders/{id}/cutoff` | `test_cutoff_ord000004_*` | DELAYED + shadow; not on_time | **PASS** (unit) |
| Inject replay | FM-3 FM-6; G1–G8 | `test_inject_02_*` `test_inject_03_*` | charging + dock; no OT | **PASS** (unit) |
| Rejection evidence | `/robots/{id}/rejection-reasons` | `test_rejection_reasons_rbt0001` | G2 on `RBT-0001` | **PASS** (unit) |

## Evals (Prompt 14)

| Artifact | Status |
|---|---|
| `evals/scorecard.md` | **PASS** — 22/22 cases; unsafe assign = 0 |
| `evals/traces/` | Sample traces EVAL-001, 002, 004, 010, 017, 019 |
| `evals/observability.md` | What to log (conflicts, abstains, gates) |
| CLI `evals` | Writes scorecard + traces |

Harness does **not** claim live-warehouse safety.

## Prompt 15 — production-readiness review

| Artifact | Status |
|---|---|
| `discovery/15_PRODUCTION_READINESS_REVIEW.md` | Simultaneous pressure **PASS**; modernization complete **FAIL** as a claim |
| `discovery/15_RELEASE_GATES.md` | R2 increment **MAY ship**; P0 live OT **MUST NOT** |
| `discovery/15_BEFORE_AFTER_KPIS.md` | Prompt 03 formulas; treatment after; 84% not a success KPI |
| `discovery/15_AUTHORITY_AND_GAPS.md` | T0–T5; GAP-1–12 visible |
| `discovery/15_90_DAY_ROADMAP.md` | Repo 3 listed as future; **not built** |
| `tests/test_prompt15_readiness.py` | **PASS** |
| `evals/traces/PROMPT-15-SIMULTANEOUS.json` | Composite refuse; OT off |

| Residual (must stay visible) | Status |
|---|---|
| `choose_robot` / `legacy_score` | **FAIL** (3 xfails) |
| Live warehouse / customer production | **NOT PROVEN** |
| Inventory physical reconcile | **OPEN / NOT PROVEN** |
| Command ids | **ABSENT** |
| T3 Approval store | **ABSENT** |
| UC-2 copilot | **ABSENT** (optional, default off) |
| Cross-DC 94.4% meaning | **UNKNOWN** |
| Cutoff-proxy C 84% | **PARTIAL** — not board KPI |

## FDE OM 21 spine (2026-09-18 pass)

Master map: `discovery/FDE_OM21_SPINE.md`.

| OM | Artifact added or confirmed | Status |
|---|---|---|
| 5 | `specs/01_context_map.md` | **ADDED** (contexts already in domain model) |
| 9 | `specs/09_information_architecture.md` | **ADDED**; runtime KG/RAG **N/A** |
| 9 | `specs/09_knowledge_graph.md` + `.json` + `.mmd` | **ADDED** explanatory graph only (not write path) |
| 11 | `specs/11_agent_suitability.md` | **ADDED NO-GO**; agent topology **N/A** |
| 12 | `docs/COMPONENT_REGISTER.md` | **ADDED**; AIBOM **N/A** |
| 13 | `specs/13_delivery_specification.md` | **ADDED** |
| 14 | `specs/14_as_built_c4.md`; `.github/workflows/pytest.yml` | **ADDED** |
| 16 | `discovery/16_OPERATIONS_RUNBOOK.md` | **ADDED**; legal AIMS **N/A** |
| 17–21 | `discovery/17_21_LIFECYCLE_DEFERRED.md` | **DEFER** (not faked) |

---

## Legend

| Status | Meaning |
|---|---|
| PASS | Met with evidence |
| PARTIAL | Some evidence, not the Repo 2 claim |
| FAIL | Legacy or new path violates invariant |
| NOT PROVEN | No test/evidence yet |

**Update rule:** every Prompt 12–15 code change must patch this file in the same increment (DoD).
