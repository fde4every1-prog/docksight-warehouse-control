# ADR-001 — Solution selection (Repo 2)

**Status:** Accepted  
**Date:** 2026-09-17  
**Prompt:** 08  
**Deciders:** FDE participant (training); no named client sponsor (01 UNKNOWN)

---

## Context

Repo 1 is a synthetic brownfield warehouse. Phase 1 (Prompts 01–04) GO: deterministic control plane; LLM off write path. Phase 2 specs 05–07 defined invariants I1–I12, retain/drop contracts, and EVAL-001–022. We must pick a Repo 2 solution shape before C4 (Prompt 09) and code (Prompt 12).

`docs/04_target_capabilities.md`: rules/services/optimization are valid; KG, twin, RAG, agents are **not** mandatory. `AGENTS.md`: do not bolt an LLM on a dashboard; do not make KG/twin/agent mandatory unless warranted.

Build vs buy: **N/A** (local synthetic repo).

---

## Options considered

| ID | Name | Disposition |
|---|---|---|
| A | Deterministic reconciliation + eligibility + filter-then-score allocator | **Selected** |
| B | A + recommend-only exception copilot | **Optional, default off** — not in first increment |
| C | Agent that dispatches robots | **Killed** |
| D | Mandatory knowledge graph / digital twin | **Not required** |

Detail and scores: `specs/04_options_and_tradeoff.md`.

---

## Decision

Repo 2 first increment **shall implement Option A only** (UC-1).

Option B **may** be added later only if: A evals PASS; copilot emits ActionProposal; Eligibility/Policy/Execution unchanged by untrusted text (EVAL-020); A runs with LLM down.

Option C **shall not** be implemented in this engagement.

Option D **shall not** be a Repo 2 completion gate.

Related: ADR-002 (LLM off write path) is a constraint on A and B.

---

## Consequences

**Good:** Matches 03 RCA (joins/gates); can pass hard evals deterministically; demo does not need Azure/LLM; three workflows and two injects are implementable on existing CSVs.

**Trade-off:** Unstructured emails are not auto-parsed in increment 1 (FINAL_v7 still joinable as CSV). Stakeholders see structured Conflict/Uncertainty, not a chat agent.

**Follow-on:** Prompt 09 C4 for A; Prompt 10 hard gates; Prompt 12 code. Do not open agent/tool APIs.

---

## Evidence

- `discovery/04_USE_CASE_AND_AI_SUITABILITY.md` UC-1 GO, C kill
- `discovery/03_PROBLEM_FRAME_AND_BASELINE.md` false certainty hypothesis
- `evals/golden_cases_repo2.jsonl` EVAL-002, 004, 022
