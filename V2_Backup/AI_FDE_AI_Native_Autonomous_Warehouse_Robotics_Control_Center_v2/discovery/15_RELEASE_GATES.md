# 15 — Release gates

**Prompt:** 15  
**Date:** 2026-09-17  
**Binding:** No Test → No Claim. No Evidence → No Release. Physical control stays **disabled**.

Two different “releases” exist. Mixing them is how a training repo gets sold as a warehouse.

| Track | What “release” means here | Decision |
|---|---|---|
| **R2** — synthetic Repo 2 increment | Specs 05–15 + UC-1 observe/refuse + evals + this review | **MAY ship as the capstone proof** |
| **P0** — customer / live OT | Connected fleet, WMS write, safety PLC, production KPI movement | **MUST NOT ship** from this repo |

---

## 1. Repo 2 increment gates (R2)

All must be true. Evidence: `tests/test_prompt15_readiness.py`, Prompt 14 harness, TRACEABILITY.

| ID | Gate | Status |
|---|---|---|
| R2-1 | UC-1 expired-cert assigns = 0 on fixtures / sample allocate | **MET** |
| R2-2 | EVAL-001–006 `must_not` hold on the **new** path | **MET** (22/22 including 007–022) |
| R2-3 | Three workflows on frozen IDs: assign, inventory UNCERTAIN, cutoff | **MET** |
| R2-4 | ≥2 injects replay without G7 waiver | **MET** (inject_02, inject_03) |
| R2-5 | Simultaneous pressure (expired + inventory + cutoff + cascade + ignore-gates) refuses composite waiver | **MET** |
| R2-6 | `/health` `physical_control: disabled`; executor `applied=false` | **MET** |
| R2-7 | LLM / copilot cannot import ActionExecutor | **MET** (copilot ABSENT) |
| R2-8 | `data/` contradictions not cleaned; 3 legacy xfails kept | **MET** |
| R2-9 | Before/after uses Prompt 03 formulas; 84% as-of is not the success KPI | **MET** |
| R2-10 | TRACEABILITY lists FAIL / PARTIAL / NOT PROVEN in the open | **MET** if matrix + this folder stay together |
| R2-11 | UC-2 still optional and default **off** | **MET** |

**R2 result:** increment **complete**. Stakeholder demo is observe / refuse / explain, not motion.

---

## 2. Hard gates that must never flip for a demo (G1–G8)

| Gate | Release rule |
|---|---|
| G1 expired/missing cert | INELIGIBLE. Text cannot waive. |
| G2 open CMMS | INELIGIBLE unless structured SafetyOfficer record (ABSENT ⇒ fail closed). |
| G3 payload | When known, undersized robot INELIGIBLE. Missing payload is G8, not invented kg. |
| G4 zone / occupancy | RESTRICTED / UNKNOWN / blocked dest not assignable. Cutoff does not override. |
| G5 inventory uncertain | No unlabeled `available_qty`. Triple retained. |
| G6 WES≠fleet | `completable=false`; `ORD-000968` not closed. |
| G7 safety | `release_zone` / speed / e-stop / cert waiver **DENY**. Always. |
| G8 UNKNOWN | ABSTAIN (replay-all, unmatched ack, catch-all). |

Fail any of these on the **UC-1** path ⇒ **do not claim R2**.

---

## 3. Customer / live gates (P0) — not met, not in scope

Do **not** treat a checked R2 box as a P0 box.

| ID | Gate | Status |
|---|---|---|
| P0-1 | Command ids / idempotent fleet acks | **ABSENT / NOT PROVEN** |
| P0-2 | Structured T3/T4 approval store (role, expiry, single-use) | **ABSENT** |
| P0-3 | IdentityResolver on the legacy `/robots/{id}` read path | **NOT MET** (SQLite-only) |
| P0-4 | Call-site swap: production assign uses filter-then-score, not `choose_robot` | **NOT MET** (`choose_robot` still callable FAIL baseline) |
| P0-5 | Timezone-stamped clocks; event_time estate-wide | **NOT PROVEN** |
| P0-6 | Physical inventory process (cycle count) without wiping SoR | **OPEN** |
| P0-7 | Live inject / chaos on real chargers, docks, AS/RS | **NOT PROVEN** |
| P0-8 | Connected OT with `physical_control` still **disabled** until a *separate* safety case | **NOT STARTED** (and must stay disabled here) |
| P0-9 | Independent safety assessment / ISO 42001 | **NOT PROVEN** |
| P0-10 | Population DELAYED / on-time movement measured in operations, not fixtures | **NOT PROVEN** |

**P0 result:** **NO-GO**. Enabling `physical_control` or POST `/missions` to “finish the demo” is a **kill**.

---

## 4. Kill switches (any one stops the claim)

- LLM or agent on Eligibility, allocator, or executor import
- Cleaning `data/` so KPIs look green
- Deleting the three known-legacy xfails without keeping a named FAIL baseline
- Claiming cutoff-proxy C (**2,941 / 3,500 = 84.0%** as-of) as the business on-time KPI
- Safety-zone release to hit Carrier-A
- “Modernization complete” while FAIL / NOT PROVEN rows are omitted from TRACEABILITY
- HTTP 200 presented as operational success

---

## 5. Who may say what in a stakeholder review

| Allowed | Not allowed |
|---|---|
| “UC-1 refuses expired-cert and open-CMMS robots in tests.” | “The warehouse is now safe.” |
| “False-available robots: 203 still in data; 0 treated eligible.” | “False availability is 0% in the estate.” |
| “We recommend missing cutoff rather than bypassing G7.” | “We will hit Carrier-A.” |
| “Physical control is disabled on purpose.” | “We can turn it on for the demo.” |

See `15_AUTHORITY_AND_GAPS.md` for T0–T5.
