# Definition of Done — Repo 2 increment

**Prompt 05.** A change is **Done** only if all boxes hold.  
No Test → No Claim. No Evidence → No Release.

## Always required

- [ ] Behavior matches cited invariants (I1–I12 subset)
- [ ] Automated test(s) pass on the **new** path
- [ ] Legacy path still callable for before/after (`legacy_score`, `legacy_available_qty`) unless the increment explicitly replaces a call site and records the delta
- [ ] Brownfield CSV/SQLite rows that conflict are **unchanged**
- [ ] `/health` still reports `physical_control: disabled` if API touched
- [ ] `TRACEABILITY_MATRIX.md` updated: requirement ↔ spec ↔ test ↔ evidence (PASS / PARTIAL / FAIL / NOT PROVEN)
- [ ] No LLM import on write/Eligibility/allocator modules
- [ ] Diagnostics or API that expose decisions list **evidence + Conflict + Uncertainty**, not a single invented truth

## UC-1 Done for the increment

| Increment | Done when |
|---|---|
| Identity | Collision report for `BOT-COLLISION-*`; no silent merge of `RBT-0001`/`RBT-0002` |
| Eligibility | Expired cert and open CMMS ⇒ INELIGIBLE; 0 unsafe assigns in tests |
| Inventory | Disagreeing qtys returned as UNCERTAIN; EVAL-001 must_not holds |
| Task/order | WES≠fleet ⇒ not COMPLETE; `ORD-000968` not falsely closed |
| Allocator | Filters then score; xfail *behaviors* pass on new function; `legacy_score` remains named |
| Time | Sort/compare uses `event_time` (EVAL-003) |

## Repo 2 (Prompt 15) Done — synthetic increment only

Closed 2026-09-17. See `discovery/15_RELEASE_GATES.md`. This is **not** customer production.

- [x] Three workflows demoed on frozen IDs
- [x] Two injects PASS
- [x] Before/after vs Prompt 03 formulas (population CSV unchanged)
- [x] EVAL-001–006 on new path
- [x] Authority gaps documented
- [x] UC-2 still optional and default off
- [x] FAIL / NOT PROVEN rows not hidden
- [x] `physical_control` disabled

## Not Done

- Tests pass by deleting xfail without implementing the gate
- Tests pass by editing `data/` to remove conflicts
- “HTTP 200” without operational assertion
- Copilot that can assign a robot
