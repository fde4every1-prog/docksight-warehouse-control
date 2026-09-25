# 14 — As-built C4 (OM 14)

**FDE OM:** 14 — Engineer (as-built views)  
**Date:** 2026-09-18  
**Target:** `specs/05_target_c4.md`  
**Code:** `src/warehouse_control/`

Target was written before Prompts 12–15. This file is what **actually runs**.

---

## Context (as-built)

Unchanged from target: synthetic local process; no live fleet/WMS/PLC; FDE / demo operator uses CLI, GET API, and dashboard. Copilot **ABSENT**. Option C **ABSENT**.

---

## Container (as-built)

```text
FastAPI warehouse_control
  GET /  /ui                 dashboard HTML
  GET /dashboard/snapshot
  GET /health                physical_control=disabled
  GET /diagnostics
  GET /identity/...
  GET /eligibility
  GET /inventory
  GET /tasks/{id}/reconcile
  GET /orders/{id}/cutoff
  GET /preview/allocate
  GET /preview/decide
  GET /injects/{id}/replay
  GET /robots/{id}           LEGACY SQLite-only (GAP-3)
  GET /robots/{id}/rejection-reasons
  GET /execution/status      stub
  CORS GET *                 for Replit observe
CLI  diagnostics | allocate | cutoff | explain | inject | evals | readiness
CSV/SQLite data/             brownfield, not cleaned
pytest tests/                42 passed + 3 xfail legacy
```

No POST `/missions`. No `robotId` write client.

---

## Component (as-built vs target)

| Target TO-BUILD | As-built module | Status |
|---|---|---|
| IdentityResolver | `identity/resolver.py` | Built |
| EligibilityPolicy | `eligibility/policy.py` | Built |
| InventoryUncertainty | `inventory/uncertainty.py` | Built |
| TaskReconciler | `tasks/reconcile.py` | Built |
| CutoffAwareness | `fulfillment/cutoff.py` | Built |
| FilterThenScore | `allocator/filter_score.py` | Built |
| DecisionEngine | `decision/engine.py` | Built |
| ActionExecutor | `execution/executor.py` | STUB |
| CopilotService | — | ABSENT |
| Dashboard | `static/dashboard.html` | Built after target spec |
| Eval harness | `evals/` | Built |
| `choose_robot` | `legacy/allocator.py` | LEGACY-KEEP FAIL |

---

## Tests / CI

Local: `PYTHONPATH=src pytest -q`  
CI: `.github/workflows/pytest.yml`

Prompt/configuration registry: **N/A** (no LLM). Model versions: **N/A**. Data pipelines: read CSV on request, not a warehouse ETL.
