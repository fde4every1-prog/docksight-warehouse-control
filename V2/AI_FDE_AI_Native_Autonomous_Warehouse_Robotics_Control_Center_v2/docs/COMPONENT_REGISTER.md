# Component register (OM 12 — SBOM-lite)

**FDE OM:** 12 — Security, guardrails, supplier controls  
**Date:** 2026-09-18  
**Not:** AIBOM / model card (no hosted model). Full SPDX optional later.

Runtime is local Python. No LLM supplier. No OT vendor connection.

---

## Application components

| Component | Path | Role | Trust |
|---|---|---|---|
| FastAPI app | `src/warehouse_control/api.py` | GET observe + dashboard | Product surface |
| Dashboard | `src/warehouse_control/static/dashboard.html` | Read-only UI | GET only |
| IdentityResolver | `identity/` | Alias collisions | Trusted join |
| EligibilityPolicy | `eligibility/` | G1–G8 | Trusted gates |
| InventoryObservation | `inventory/` | Triple qty | Retain conflict |
| FilterThenScore | `allocator/filter_score.py` | Product allocate | Must not call as OT |
| DecisionEngine | `decision/engine.py` | ALLOW/DENY/ABSTAIN | No execute |
| ActionExecutor | `execution/executor.py` | Stub | Always `applied=false` |
| Legacy allocator | `legacy/allocator.py` | FAIL baseline | Do not use as product |
| Eval harness | `evals/` | GS-1–15 | Synthetic |
| CSV/SQLite | `data/` | Brownfield evidence | Do not clean |

**ABSENT:** CopilotService, live fleet client, WMS client, PLC.

---

## Python runtime (requirements.txt)

| Package | Version pin | Use |
|---|---|---|
| fastapi | 0.115.0 | API |
| uvicorn | 0.30.6 | Server |
| pydantic | 2.9.2 | Transitive/validation |
| pytest | 8.3.3 | Tests |

Optional / not product runtime: `python-pptx` (PRD deck generator only).

No `openai`, `langchain`, `anthropic`, Azure AI packages.

---

## Contracts (not implemented clients)

`contracts/fleet_api_v1.yaml`, `fleet_api_v2.yaml`, `order_event_schema.json` — **evidence**. Do not POST.

---

## Guardrails (already encoded)

Threat model: `specs/07_threat_model.md`. Injection: `tests/test_untrusted_content.py`. Exit plan for a future LLM: **do not import executor**; turn UC-2 off; UC-1 still runs (ADR-002).

Supplier assessment: **none** (no model vendor). If UC-2 is ever added, this register must gain the model name, eval ids, and an exit flag.
