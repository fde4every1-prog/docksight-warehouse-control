# OM 17–21 — lifecycle deferred (not missing by accident)

**FDE OM:** 17 Deploy · 18 Monitor · 19 Prove value · 20 AIMS lifecycle · 21 Retire  
**Date:** 2026-09-18  
**PDF:** “Releasing to the customer — 6 months repo 3.0”

These phases produce a **controlled live service** and an **authorised lifecycle state**. This V2 engagement is a **virtual proof**. Completing 17–21 here would mean **faking a production**. We document them as **deferred**, not incomplete homework.

---

## 17 Deploy progressively and integrate adoption

| PDF artifact | V2 |
|---|---|
| Release manifest / deployment record | **DEFER** — no customer environment |
| Pilot / canary / autonomy expansion | **DEFER** — autonomy stays T0/T1 preview; T5 off |
| Adoption dashboard / SOP updates | Demo dashboard is **observe-only**; not adoption telemetry |

If a sponsor later wants a “pilot”: ship the same GET app to a training server. Still no OT. That is a new mandate.

---

## 18 Monitor and validate operational resilience

| PDF artifact | V2 |
|---|---|
| Prod dashboards, drift, cost, agent-loop alerts | **N/A** — no prod, no agent, no tokens |
| Chaos in production | Inject replay is the **synthetic** drill (`16_OPERATIONS_RUNBOOK.md`) |

---

## 19 Prove value and tell the decision story

| PDF artifact | V2 |
|---|---|
| Before/after KPIs | **HAVE** `discovery/15_BEFORE_AFTER_KPIS.md` (treatment, not cleaned CSVs) |
| Cost-to-value / benefits-realisation $ | **DEFER** — no cost field (Prompt 03 NOT COMPUTABLE) |
| Executive SCQA | **HAVE** discovery 03 + PRD deck |
| Scale / change / stop recommendation | Stop live OT. Scale only the **virtual** packaging if asked |

---

## 20 Evaluate AIMS and decide lifecycle state

| PDF artifact | V2 |
|---|---|
| AIMS performance, internal audit, CAPA, management review | **N/A** — no certified AI management system |
| Scale / restrict / suspend / retire decision | Restrict = keep OT disabled. No AIMS vote required for a training repo |

---

## 21 Retire and capture reusable IP

| PDF artifact | V2 |
|---|---|
| Retirement plan, access revocation, model memory wipe | **N/A** — no hosted model or customer tenants |
| Reusable ADRs / C4 / eval / guardrail templates | **HAVE** — these files *are* the reusable FDE IP |

When this training system is deleted: delete the local clone. No credentials to revoke.

---

## Rule

Do not create fake deployment records, fake AIMS audits, or fake $ benefits to “complete” 17–21. That would fail OM 3 (evidence-backed value) and OM 4 (kill: lying with KPIs).
