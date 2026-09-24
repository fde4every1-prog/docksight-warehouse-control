# 11 — Agent suitability (OM 11) — NO-GO

**FDE OM:** 11 — Design agentic and multi-agent orchestration  
**Date:** 2026-09-18  
**Binding:** `discovery/04_USE_CASE_AND_AI_SUITABILITY.md`, ADR-001 Option C killed, ADR-002, G1–G8.

PDF essential artifacts for **an agentic architecture** are listed below as **N/A**. The required OM 11 output for *this* engagement is an **approved decision not to agentize**.

---

## Suitability assessment

| Question | Answer |
|---|---|
| Is the core work tool-using open-ended reasoning? | **No.** Cert expired, WO open, qty disagree, WES≠fleet are booleans. |
| Would an agent assign robots or write WMS? | That is Option C — **killed**. |
| Can the warehouse run if an LLM is down? | **Must yes.** UC-1 is deterministic. |
| Human-in-the-loop? | **Fail closed:** no structured Approval ⇒ G2/G7 DENY. Email is not HITL. |

**Decision:** **NO-GO for single-agent and multi-agent orchestration.**  
Autonomy ADR: `specs/06_autonomy_tiers.md` (T0 observe / T1 recommend / T5 prohibited). LLM never raises a tier.

---

## PDF artifacts — status

| Essential artifact | Status |
|---|---|
| Agent-suitability assessment | **This file** |
| Autonomy-level ADR | **HAVE** `06_autonomy_tiers.md` + ADR-002 |
| Agent responsibility map | **N/A** — no agents |
| Orchestration topology | **N/A** |
| Agent sequence / state machine | **N/A** |
| Tool/action catalogue | Tools = GET observe + stub execute (always refuse) |
| Identity/permission matrix | G1–G8; untrusted shadow; no agent identities |
| Shared-memory design | **N/A** |
| Handoff / termination / loop controls | **N/A** (no agent loops). DecisionEngine is one-shot ALLOW/DENY/ABSTAIN |
| Human approval / override matrix | **HAVE** G7 DENY; T3 Approval store **ABSENT** ⇒ fail closed |

Optional later UC-2: recommend-only text, cannot import ActionExecutor, EVAL-020 must pass. Still not OM 11 multi-agent.

---

## What we use instead

Deterministic `EligibilityPolicy` + `DecisionEngine` + in-memory inject replay. That is bounded autonomy without agents.
