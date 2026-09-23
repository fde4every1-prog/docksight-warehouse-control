# P01-v1-MODERNIZATION_BACKLOG

**Prompt:** 01 — Warehouse Brownfield Forensics  
**Artifact:** Prioritized backlog after forensics  
**Constraint:** No Spec → No Code. Baseline **2.0.0** frozen. Overlay **0.1.0** until a transformation lands with evals.

This backlog is for stakeholders and for Prompts 02–15. It does **not** authorize implementation in Prompt 01.

Priority: **P0** blocks any autonomy claim · **P1** required for the 10-day challenge brief · **P2** WRCC golden coverage beyond the brief · **P3** deferred (do not fake in 10 days).

---

## P0 — Spec and freeze (before any behavior change)

| ID | Item | Why | Exit |
|----|------|-----|------|
| P0-1 | Keep baseline 2.0.0 frozen | Reviewer must replay inherited diagnostics | `pyproject` / API / manifest stay 2.0.0 (already guarded in overlay tests) |
| P0-2 | Write WRCC-aligned specs in-repo (`specs/`) | Contract is currently **FAIL** / absent | Domain + AC files exist; Prompt 02 |
| P0-3 | TRACEABILITY_MATRIX.md | No requirement is linked to test or evidence | Every P1 item has spec → test → evidence |
| P0-4 | Executable eval harness from `evals/golden_cases.jsonl` | Questions are not tests | EVAL-001…006 run and fail unsafe answers |
| P0-5 | Authority model on paper | LLM must not gain a write path | Observe / recommend / human-gated / never-delegate |

---

## P1 — Ten-day committed transformations (maps to overlay T01–T08)

These match the challenge brief: three workflows, evals, two injects, KPIs, authority.

| Backlog ID | Overlay | Work | Golden / AC analog | Depends on |
|------------|---------|------|--------------------|------------|
| P1-1 | T03 | Contradiction observability (do not erase baseline counts) | Scenarios 6,7,13 | P0-1 |
| P1-2 | T01 | Canonical robot identity; preserve alias disagreement | WRCC-AC-004, scenario 6 | P0-2, P0-3 |
| P1-3 | T06 | Eval / TEVV harness | All EVAL-00x; later all 15 scenarios | P0-4 |
| P1-4 | T04 | Suitability gate (workflow 1: assignment) | EVAL-002; expired cert; CMMS vs AVAILABLE; payload XFAIL | P1-3 |
| P1-5 | T02 | Inventory reconciliation (workflow 2) | EVAL-001, EVAL-006, scenario 13 | P1-3 |
| P1-6 | T05 | Task/order exception + cutoff (workflow 3) | Scenario 3; EVAL-003; OMS/WES/fleet split clocks | P1-3 |
| P1-7 | T07 | Two injects: charging failure + cutoff cascade (or AS/RS) | Scenarios 2,3,12,14 analogs | P1-4, P1-6 |
| P1-8 | T08 | KPI before/after + do-not-automate list | Challenge brief last two bullets | P1-4…P1-7 |

**Invariants already evidenced (must become specs, then tests):**

- Expired safety cert ⇒ not assignable even if fleet AVAILABLE / ONLINE.  
- WMS/ERP/vision disagreement ⇒ uncertainty; do not invent physical truth.  
- WES status and fleet status are different clocks.  
- Safety-zone override to hit cutoff ⇒ refuse.  
- Stale fleet queue after outage ⇒ do not blindly replay.

---

## P2 — WRCC gaps that forensics proved are FAIL (Prompts 03–12)

Do these only after P0 specs exist. Order follows the prompt library.

| Backlog ID | Prompt | Item | Forensic tag |
|------------|--------|------|----------------|
| P2-1 | 03 | Identity resolver that **does not** overwrite canonical id from LLM or stale scan | FAIL / PARTIAL |
| P2-2 | 04 | Temporal model: event vs source vs ingest vs robot/WMS/control clocks; drift detector | FAIL on detector |
| P2-3 | 05 | WarehouseState / context graph (including UNKNOWN execution, freshness) | FAIL |
| P2-4 | 06 | Retrieval router: structured live facts vs semantic SOP; ban SOP for “is aisle blocked now?” | FAIL (no router) |
| P2-5 | 07 | Human-zone / blocked-aisle **hard gate**; UNKNOWN occupancy ⇒ refuse path | FAIL |
| P2-6 | 08 | Supervisor + DecisionEngine; Copilot cannot import ActionExecutor | FAIL |
| P2-7 | 09 | Preserve telemetry/WMS/charger conflicts; abstain if insufficient | FAIL |
| P2-8 | 10 | Idempotent dispatch; lost ack ⇒ UNKNOWN; no blind retry | FAIL |
| P2-9 | 11 | Edge / Wi-Fi degraded mode; local safety without cloud AI | FAIL |
| P2-10 | 12 | Reconnect reconciliation report; no silent overwrite of Supervisor decisions | FAIL |

---

## P3 — Named and deferred (do not pretend to ship in 10 days)

| Backlog ID | Overlay | Item | Why wait |
|------------|---------|------|----------|
| P3-1 | T09 | Global task prioritization beyond local battery heuristic | Needs P1-4 and P1-6 or it repeats local greed |
| P3-2 | T10 | Congestion / cutoff forecasting | Forecast must not override P2-5 hard gates |
| P3-3 | T11 | RAG over shadow mail / SOP | Retrieval ≠ authority; injection tests first (Prompt 13) |
| P3-4 | T12 | Autonomy beyond recommend | Requires production TEVV; this repo must never drive robots |
| P3-5 | — | Full 15-scenario scorecard (Prompt 14) and production-readiness pack (Prompt 15) | After P2 exists; otherwise every row is NOT PROVEN |

---

## Suggested 10-day use of this backlog

| Day | Backlog | Output the PM can see |
|-----|---------|------------------------|
| 1 | P01 artifacts (this folder) | Forensics complete |
| 2 | P1-1 counts + P1-2 identity notes | Evidence workbook |
| 3 | P1-6 journeys (3 orders + cascade) | Journey write-ups |
| 4 | P0-2…P0-5 + P1-3 | Specs + failing evals |
| 5–7 | P1-4, P1-5, P1-6 overlay code | Three workflows beside `legacy/` |
| 8 | P1-7 | Two inject traces |
| 9–10 | P1-8 | KPI delta + readiness gaps; P2/P3 still visible as unpaid debt |

---

## Explicit non-goals (from AGENTS.md)

- Do not bolt an LLM onto `/diagnostics` and call it modernization.  
- Do not delete contradictory rows to improve scores.  
- Do not bump baseline 2.0.0.  
- Do not enable physical control.
