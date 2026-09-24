# 04 — Options and trade-off (Repo 2)

**FDE Operating Model phase:** 8 — Generate, test and select options  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 08  
**Date:** 2026-09-17  
**Mode:** Decision, not build. No `src/` changes.

**Binding ADRs:** `specs/adr/ADR-001-solution-selection.md`, `specs/adr/ADR-002-llm-off-write-path.md`

**Selected default:** **Option A** (deterministic spine). **Option B** optional, **disabled by default**. **C killed. D not required.**

---

## File naming (why this is `04_` not `08_`)

The **prompt number** is 08. The **spec series** in `specs/` is already:

| File | Prompt |
|---|---|
| `specs/01_domain_model.md` | 05 |
| `specs/02_data_contracts.md` | 06 |
| `specs/03_evaluation_strategy.md` / `03_risk_and_harms.md` | 07 |
| **`specs/04_options_and_tradeoff.md`** | **08** (this file) |
| `specs/05_target_c4.md` (later) | 09 |

The library names this artifact `04_options_and_tradeoff.md`, not `08_`. ADRs are `ADR-001`, `ADR-002` under `specs/adr/`, not `08_ADR`.  
Discovery used `01_`–`04_` because those *were* OM/prompt numbers. Specs use a **separate 01–05 sequence**.

---

## Inputs from Prompts 04–07

| Input | How used |
|---|---|
| 04 GO / UC-1 required / UC-2 optional off | Default A+B |
| 04 classification #1–10 | C and D fail suitability |
| 03 RCA (joins/gates, not language) | A is sufficient for the brief |
| 05 invariants I1–I12 | Must hold under every option |
| 06 retain/drop | A reads CSV; must not clean |
| 07 EVAL-001–022 | A must pass hard `must_not`; B adds EVAL-020 |
| `docs/04` none of RAG/KG/agent mandatory | D not required |
| `AGENTS.md` anti-patterns | Kill C; do not bolt LLM on dashboard |

**Build vs buy:** **N/A**. This is a local synthetic repo. No vendor product is in scope.

---

## Options

### A — Deterministic reconciliation + eligibility + allocator only

UC-1: identity collisions, eligibility (cert/CMMS/cal/connectivity/payload/zone), inventory UNCERTAIN, WES/fleet conflict, event_time order, filter-then-score, diagnostics/API, keep `legacy_*` for before/after.

Non-AI alternative: **this is the non-AI option.**

Meets brief: three workflows, two injects, evals, KPIs, authority — without an LLM.

### B — A + exception copilot (recommend-only)

RAG/template over shadow emails + UC-1 evidence bundle. Output ActionProposal text only. Default **off**. EVAL-020 required if built. Warehouse must run if LLM is down (ADR-002).

Non-AI alternative: JSON/markdown evidence pack from A (sufficient).

### C — Agent that dispatches robots

LLM/agent with tools to assign missions / write WMS. **Expected kill.**

Non-AI alternative: A.

Fails EVAL-002/004/022, I10, 04 prohibited uses, Wi-Fi/outage inject (gates must not depend on cloud AI).

### D — Mandatory knowledge graph / digital twin

Platform requirement for Repo 2. Discovery did **not** prove missing graph/twin is the root cause (03: false certainty / missing joins). `docs/04`: not mandatory.

Non-AI alternative: A’s Conflict records + existing CSVs.

May be a later optional visualization; **not** a Repo 2 gate.

---

## Weighted trade-off (Repo 2 only)

Weights sum to 100. Score 1–5 (5 = best for this capstone).

| Criterion | W | A | B | C | D |
|---|---|---|---|---|---|
| Hits CB-4/5/6/7 with fixtures | 20 | 5 | 5 | 2 | 3 |
| Safety / EVAL `must_not` | 25 | 5 | 4 | 1 | 4 |
| Feasibility on this codebase | 15 | 5 | 3 | 2 | 2 |
| Matches 04 GO | 15 | 5 | 5 | 1 | 2 |
| Runs if LLM/cloud down | 10 | 5 | 4* | 1 | 3 |
| Complexity / waste | 10 | 5 | 3 | 1 | 2 |
| Stakeholder explainability | 5 | 4 | 5 | 2 | 3 |
| **Weighted** | 100 | **4.95** | **4.15** | **1.40** | **2.70** |

\*B scores 4 only if copilot is optional and gates stay in A.

---

## Kill criteria

| Option | Kill if |
|---|---|
| A | Cannot pass EVAL-001/002/006 on new path without cleaning `data/` |
| B | Copilot can import ActionExecutor / change Eligibility; or A does not run when LLM is down |
| C | **Killed now** — dispatch agent. Revive only with written SafetyOfficer + live OT (out of scope) |
| D | Treated as mandatory to “complete” Repo 2 |

---

## Decision

**Implement A in Prompts 09–15.**  
**Do not implement B in the first increment.** A later increment may add B behind a flag after A evals PASS.  
**Do not implement C or D as required.**

Preliminary architecture (Prompt 09) must realize A: DecisionEngine that can ABSTAIN; ActionExecutor stub **not** importable from any copilot module.
