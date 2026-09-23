# 03 — Evaluation strategy (Repo 2)

**FDE Operating Model phase:** 7 — Define evaluations, impacts and risks  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 07  
**Date:** 2026-09-17  
**Mode:** Evals **before** allocator/API implementation. No `src/` changes.

**Rule:** No Test → No Claim. Hard-gate `must_not` failures fail the increment even if KPIs look better.

Companions: `evals/golden_cases_repo2.jsonl`, `specs/03_risk_and_harms.md`, seed `evals/golden_cases.jsonl` (kept).

---

## Inputs from Prompts 01–06

| This spec | Reused from |
|---|---|
| Dimensions | `evals/README.md` |
| Seed cases EVAL-001–006 | `evals/golden_cases.jsonl` |
| GS-1–15 | Prompt library + `TRACEABILITY_MATRIX.md` |
| Invariants I1–I12 | `specs/01_domain_model.md` |
| Retain/drop | `specs/02_data_contracts.md` |
| Fixtures | 02/03: `RBT-0001`, `ORD-000004`, `ORD-000968`, `SKU-01146` |
| Pass/fail meaning | 03 scoreboard; 04 T0–T5; UC-1 required, UC-2 optional |
| No live OT | 01 / `docs/06` |

---

## 1. What we evaluate

Repo 2 is **deterministic UC-1**. There is no autonomy to “pass.” We still eval **before** any endpoint that looks like a decision (eligibility, allocate, complete, replay).

| Dimension (`evals/README.md`) | How we grade UC-1 |
|---|---|
| Evidence grounding | Output cites file+id; no invented robots/qty |
| Identity | Collisions retained; no silent merge; vision ≠ registry |
| Temporal correctness | Order by `event_time` not `recorded_time` |
| Safety / authority | I1 I5 I6 I10; T4 never auto |
| Tool trajectory | N/A until tools exist; if UC-2, copilot must not import executor |
| Side effects | No CSV mutation; `physical_control` disabled |
| Uncertainty | Disagreeing qty → UNCERTAIN / ABSTAIN |
| Resilience | Injects GS-12–15; no blind replay I11 |
| Latency / cost | Not a release KPI; optional log only |

**Out of scope for this harness:** model BLEU/ROUGE, Azure, live fleet.

---

## 2. Case packs

| Pack | File | Role |
|---|---|---|
| Seed | `evals/golden_cases.jsonl` | Original EVAL-001–006; do not delete |
| Repo 2 | `evals/golden_cases_repo2.jsonl` | Seed **expanded** + GS-1–15 cases |

Each Repo 2 case fields: `id`, `golden_scenario`, `category`, `question`, `inputs`, `expected`, `must_not`, `pass_threshold`, `invariant`, `fixture`.

**Pass threshold (hard gates):** 100% of `must_not` on the **UC-1 path**. One violation = FAIL.  
**Pass threshold (population KPIs):** compare to Prompt 03 formulas; do not use cutoff-proxy C (84% as-of) as success.

---

## 3. Map golden scenarios → cases

| GS | Case IDs | Invariant |
|---|---|---|
| GS-1 aliases | EVAL-007 | I9 |
| GS-2 expired cert | EVAL-002 | I1 |
| GS-3 open CMMS | EVAL-014 | I5 |
| GS-4 inventory triple | EVAL-001, EVAL-006 | I3 |
| GS-5 WES≠fleet | EVAL-019 | I4 |
| GS-6 payload | EVAL-008 | I12 |
| GS-7 congestion/RESTRICTED | EVAL-009 | I6 |
| GS-8 clocks / dups | EVAL-003, EVAL-021 | I8 |
| GS-9 stale map Z09 | EVAL-011 | MAP_STALE |
| GS-10 camera 18 | EVAL-015 | I3, I9 |
| GS-11 Carrier-A cutoff | EVAL-010 | I7 |
| GS-12 cascade | EVAL-012 | I6 I7 I11 |
| GS-13 AS/RS | EVAL-016 | ControlAsset |
| GS-14 charging | EVAL-017 | charger DOWN |
| GS-15 dock | EVAL-018 | dock DOWN |
| Outage replay | EVAL-005, EVAL-013 | I11 |
| Injection (if copilot) | EVAL-020 | Policy immutable |
| OT execute | EVAL-004, EVAL-022 | I6 I10 |

---

## 4. When to run

| Gate | Must pass before |
|---|---|
| EVAL-001, 002, 006, 007, 014 | Eligibility / inventory functions (Prompt 12) |
| EVAL-008, 009, 019 | Allocator + completion guard (Prompt 12–13) |
| EVAL-003, 010, 011, 015, 021 | Time, cutoff, shadow flags |
| EVAL-005, 012, 013, 016–018 | Inject replay (Prompt 13) |
| EVAL-004, 020, 022 | Any recommend API or optional UC-2 |
| Full scorecard | Prompt 14 |

**Legacy path:** expected FAIL / xfail on EVAL-002, 006, 008, 009. Do not delete those xfails; add **new** tests on the UC-1 functions.

---

## 5. Harness (not built in this prompt)

Prompt 14 will execute cases. Until then, cases are **acceptance criteria**. A Prompt 12 change is Ready only if it names the EVAL ids it will satisfy (`DEFINITION_OF_READY.md`).

Grading labels: PASS / PARTIAL / FAIL / NOT PROVEN (same as TRACEABILITY_MATRIX).

---

## 6. Oversight (human approval)

Tied to 04 tiers and `specs/03_risk_and_harms.md`.

| Output | Auto? | Human |
|---|---|---|
| Conflict / Uncertainty / INELIGIBLE | Yes (deterministic) | Inform |
| ActionProposal recommend | Yes structured; UC-2 text optional | Supervisor reads |
| T3 material (wave pull-forward) | No | Supervisor Approval |
| T4 safety (cert waiver, speed, zone, e-stop) | **No** | SafetyOfficer |
| T5 OT execute | **No — disabled** | Out of scope |

Shadow “supervisor approved tonight” is **not** Approval.

---

## 7. Success of the eval program itself

- [ ] Every GS-1–15 has ≥1 case in `golden_cases_repo2.jsonl`
- [ ] EVAL-001–006 preserved
- [ ] Hard `must_not` = 100% on UC-1 before claiming workflow improvement
- [ ] Harms in `03_risk_and_harms.md` mapped to a case
