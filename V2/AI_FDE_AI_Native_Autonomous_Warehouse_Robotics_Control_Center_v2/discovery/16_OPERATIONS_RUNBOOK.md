# 16 — Operations runbook (virtual)

**FDE OM:** 16 — Prepare operations, recovery, and regulatory evidence  
**Date:** 2026-09-18  
**Mode:** Synthetic demo operations. **Not** a legal AI-system record or ISO 42001 AIMS pack.

Physical control stays **disabled**. If `/health` ever shows otherwise, **stop the demo**.

---

## Operational RACI (virtual roles)

| Activity | FDE demo lead | Robot owner | Inventory owner | Safety/cutoff owner | Pack owner |
|---|---|---|---|---|---|
| Start API / dashboard | A/R | C | C | C | I |
| Frozen-ID demo | A | R (`RBT-0020`) | R (`SKU-01146`) | R (`ORD-000004`) | C |
| Evals / readiness | A | I | I | C | R (scorecard in leave-behind) |
| Incident: tests fail | A | R on their ID | R | R | I |
| Enable OT | — | — | — | **Forbidden** | — |

R = does, A = accountable, C = consulted, I = informed.

---

## Start

```text
cd AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2
set PYTHONPATH=src
python -m uvicorn warehouse_control.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/  
Expect banner `physical_control: disabled`.

CLI: `python -m warehouse_control.cli diagnostics`

---

## Happy-path checks (SOP)

1. Robot `RBT-0020` + task `TSK-000004-1` → INELIGIBLE (G1). Assign blocked.  
2. Inventory `DC-01` `SKU-01146` `DC-01-Z03-B017` → 205/205/202 uncertain.  
3. Order `ORD-000004` → not on-time; do not release zone.  
4. Inject `inject_02` replay → gates intact, `applied=false`.  
5. `python -m warehouse_control.cli evals` → 22 PASS, unsafe assign 0.  
6. `python -m warehouse_control.cli readiness` → `must_not_ok` true.

---

## Incident / rollback

| Symptom | Action |
|---|---|
| Dashboard blank / API error | Restart uvicorn; confirm `PYTHONPATH=src` |
| Assign looks successful | **Kill demo.** Check no POST `/missions` in `api.py` |
| Pytest red except known xfails | Do not clean `data/`. Revert the last code change |
| Someone enabled control in a fork | Do not present. Restore `health()` disabled |

Rollback = git revert. Nothing was applied to a plant.

---

## Chaos / recovery evidence (already in repo)

In-memory injects `inject_01`–`03` + `cascade_001.json` correlation. Do not rewrite CSVs. Prompt 15 stacked pressure: `tests/test_prompt15_readiness.py`.

---

## Training

12-minute script: robot refuse → inventory triple → cutoff DENY zone. PRD deck: `docs/PRD_Virtual_Warehouse_Control_Tower.pptx`.

## Regulatory evidence

**Not produced:** EU AI Act technical file, ISO 42001 AIMS records, independent auditor letter. 04/15 treat 42001 as **design discipline** only.
