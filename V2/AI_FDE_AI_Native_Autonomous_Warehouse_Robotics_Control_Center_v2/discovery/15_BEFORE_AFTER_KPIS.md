# 15 — Before / after operational KPIs

**Prompt:** 15  
**Date:** 2026-09-17  
**Formulas:** `discovery/03_PROBLEM_FRAME_AND_BASELINE.md` §3 (unchanged).  
**Compute:** `warehouse_control.evals.adversarial.compute_kpi_before_after`  
**CLI:** `python -m warehouse_control.cli readiness`

**Rule:** After is **how UC-1 treats the same rows**, not a cleaned snapshot. Editing `data/` to move these numbers is a **kill**.

As-of clock for proxy C remains `data/manifest.json` `generated_at` = **2026-09-10**. Timestamps have **no timezone**.

---

## 1. Required Prompt 03 metrics

| KPI | Formula (same as 03) | Before | After (UC-1 treatment) | Population CSV | Status |
|---|---|---|---|---|---|
| False availability (robot union) | Unique robots with (EXPIRED ∧ connectivity ≠ OFFLINE) **OR** (WO OPEN/IN_PROGRESS ∧ fleet AVAILABLE) / 712 | **203 / 712 = 28.5%** | **0 / 203** treated ELIGIBLE or rankable | still 203 rows | COMPUTED |
| Expired-and-connected | 35 / 712 | **4.9%** | G1 INELIGIBLE; 0 assigns on UC-1 fixtures | still 35 | COMPUTED |
| Open-CMMS + AVAILABLE (WO-level) | 176 WOs | **176** | G2 INELIGIBLE (`RBT-0001` / `WO-000380`) | still 176 | COMPUTED |
| Inventory disagreement | not-all-equal (wms, erp, vision) / 9,360 | **7,382 / 9,360 = 78.9%** | **7,382** marked `uncertain=true`; **0** unlabeled `available_qty` | still 7,382 | COMPUTED |
| WES ≠ fleet | status split / 8,732 | **7,351 / 8,732 = 84.2%** | **7,351** `completable=false`; `ORD-000968` not closed | still 7,351 | COMPUTED |
| Duplicate telemetry | extra duplicate keys / 12,896 | **80 / 12,896 = 0.62%** | **0** counted as extra movements on UC-1 (EVAL-021); 80 packets remain | still 80 | COMPUTED |
| OMS ≠ WMS | status split / 3,500 | **1,283 / 3,500 = 36.7%** | sources retained; no silent merge | still 1,283 | COMPUTED |
| Cutoff-risk A (TMS DELAYED) | DELAYED / 3,500 | **586 / 3,500 = 16.7%** | `ORD-000004` `on_time` is not true; miss-cutoff recommended, not executed | still 586 | COMPUTED |
| Cutoff-risk C (as-of) | `carrier_cutoff` < 2026-09-10 ∧ not DEPARTED / 3,500 | **2,941 / 3,500 = 84.0%** | **unchanged; still PARTIAL** | still 2,941 | **PARTIAL — do not use as board KPI** |

Unsafe-assign CTQ (03 §4): **0** expired-cert assigns on the UC-1 path (EVAL-002, Prompt 14 scorecard, Prompt 15 sample `TSK-000004-1`). Legacy `choose_robot` can still pick expired-cert (**FAIL** baseline, xfails kept).

---

## 2. What “after” does *not* mean

| Claim | Reality |
|---|---|
| “False availability is now 0%” | The **estate file** still has 203 false-available robots. UC-1 **refuses** them. |
| “Inventory accuracy is 100%” | Disagreement is still 78.9%. UC-1 **surfaces** it. Physical count is still OPEN. |
| “On-time is fixed” | DELAYED is still 586. UC-1 will not bypass G7 to hit Carrier-A. |
| “84% cutoff risk cleared” | Proxy C is historical pile vs as-of date. **Forbidden** as success. |
| “Modernization moved the CSV KPIs” | `data_rows_unchanged=true` | 

---

## 3. Frozen-ID after checks

| ID | Before (discovery) | After (UC-1) |
|---|---|---|
| `RBT-0001` | HEALTHY + AVAILABLE + open lidar WO | INELIGIBLE G2 |
| `RBT-0020` | EXPIRED + INTERMITTENT + AVAILABLE | INELIGIBLE G1 |
| `SKU-01146` | `legacy_available_qty` from WMS only | triple 205/205/202, `uncertain=true` |
| `ORD-000004` | OMS SLA vs Carrier-A −35 min / TMS DELAYED | `on_time` not true; T1 miss-cutoff; G7 DENY on zone release |
| `ORD-000968` | OMS SHIPPED vs PACK_FEED EXECUTING | `completable=false` |
| `AMR-044` | unmatched cascade name | unresolved; not coerced to `RBT-0044` |

---

## 4. Still NOT COMPUTABLE (03 §3.2)

Unchanged from discovery. Repo 2 did not create the missing clocks.

| Candidate | Status |
|---|---|
| Congestion minutes | NOT COMPUTABLE |
| Charging queue time | NOT COMPUTABLE |
| Travel distance per task | NOT COMPUTABLE |
| Recovery time after real outage | NOT COMPUTABLE (injects are overlays) |
| Cost per fulfilled order | NOT COMPUTABLE |
| Robot productive utilization | NOT COMPUTABLE |
| On-time among all orders | PARTIAL (only 248 DEPARTED with both timestamps) |

---

## 5. Counter-metrics (must not “improve” by cheating)

| If this goes up/down | Check |
|---|---|
| On-time / DELAYED | Did G7 still DENY? Expired-cert assigns still 0? |
| Exception labor | Did we hide UNCERTAIN as WMS truth? |
| Safety events | Did we release RESTRICTED zones? |

---

## Explicit non-claims

- No live TMS, WMS, or fleet KPI feed.
- No statement that the multinational estate’s 28.5% / 78.9% / 84.2% rates have moved in operations.
- Value delivered in Repo 2 is **false-certainty reduction on the decision path**, measured as 0 unsafe assigns and 0 invented qty on UC-1.
