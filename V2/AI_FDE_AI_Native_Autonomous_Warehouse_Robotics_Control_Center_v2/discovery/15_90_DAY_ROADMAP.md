# 15 — 90-day roadmap (future only)

**Prompt:** 15  
**Date:** 2026-09-17  
**Mode:** Planning note. **Do not build Repo 3 in this increment.**  
**Clock:** 90 days after stakeholder acceptance of the Repo 2 synthetic proof — not after this file is written.

Repo 3 in the capstone path is **the participant’s own 10 prompts** after this 15-prompt library. That work is listed here as **future**. It is not started.

Physical control remains **disabled** unless a *separate* engagement with a real safety case exists. This roadmap does not authorize OT.

---

## 1. What is already done (do not redo)

- Discover (Prompts 01–04 / FDE OM 1–4)
- Specs + ADRs (Prompts 05–11)
- UC-1 observe / refuse / allocate / evals (Prompts 12–14)
- This production-readiness review (Prompt 15)

---

## 2. Days 1–30 — harden the proof, still synthetic

| Work | Why | Exit |
|---|---|---|
| Swap **new** CLI/API call sites to `allocate` / `evaluate_eligibility`; keep `choose_robot` named but not on the demo path | GAP-4: legacy still callable FAIL | Demo script never prints a `legacy_score` winner as the recommendation |
| Wire IdentityResolver into any new read model; leave SQLite `/robots/{id}` documented as legacy | GAP-3 | Collision report visible on the robot the operator looks up |
| Add a structured **Approval** object (schema only, no email parser) | GAP-1 | G2 still fail-closed until a real record exists |
| Document payload-missing G8 rankable exception; add payload to *new* task fixtures only if sourced | GAP-5 | Do not invent kg on 8,732 CSV tasks |
| Population KPI dashboard using **03 formulas** + UC-1 treatment column | CB-7 | 84% as-of never on the board |

**Out:** UC-2 copilot, Azure, live fleet, CSV cleaning.

---

## 3. Days 31–60 — optional UC-2 (default off) and data-ops, still no OT

| Work | Why | Exit |
|---|---|---|
| Recommend-only copilot **if** a sponsor asks for narrative | 04 UC-2 optional | Must not import ActionExecutor; EVAL-020 still PASS |
| Cycle-count **process** design for UNCERTAIN SKUs (people + scan), not a WMS overwrite job | Inventory OPEN | Triple still retained |
| Event-time + timezone policy for a future live feed | GAP-6 | Naive CSV stays as historical evidence |
| Command-id / idempotency **contract** against `fleet_api_v2.yaml` (still no POST) | GAP-2 | Refuse-replay remains until keys exist |
| Independent read of TRACEABILITY FAIL rows in a stakeholder pack | Prompt 15 | FAIL/NOT PROVEN still visible |

**Kill if:** copilot can assign; “ignore gates” becomes a tool.

---

## 4. Days 61–90 — Repo 3 only if a new mandate exists

This library **stops** at OM 16 / Repo 2. A later 10-prompt Repo 3 might cover OM 17–21 (operate, transfer, value). Do **not** invent that library here.

Candidate themes **if** the next mandate is issued (not committed):

- Operator runbook for exception_handlers using UC-1 traces
- Before/after measurement plan on a *live* slice (new data, new consent)
- Safety case to even *discuss* `physical_control`
- Explicit decision: keep Option A only, or turn UC-2 on behind a flag

**Still prohibited without a new safety case:** fleet POST, WMS write, PLC, speed change, zone release, cert waiver from text.

---

## 5. What this 90-day plan will not do

- Build Azure / cloud OT
- Claim ISO/IEC 42001
- Resolve AMR-044 by guessing `RBT-0044`
- Make WMS = ERP = vision
- Use DELAYED→0 or 84% as-of as a bonus metric
- Start the participant’s 10 Repo 3 prompts unless they ask

---

## 6. Decision required from the stakeholder

| Ask | Recommended answer |
|---|---|
| Is Repo 2 enough to show FDE Discover→proof? | **Yes** (synthetic). |
| Is the warehouse modernized? | **No.** |
| Enable physical control for the showcase? | **No.** |
| Start Repo 3 / own 10 prompts? | Only when they explicitly start that phase. |
