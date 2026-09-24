# Dashboard UI test cases (one item at a time)

**For:** teammate verifying the observe-only dashboard  
**App:** `src/warehouse_control/static/dashboard.html`  
**API:** `src/warehouse_control/api.py`  
**Automated smoke (not a substitute for these clicks):** `tests/test_dashboard.py`

Do **one case**, mark Pass/Fail, then the next. Do not skip to a later ID. Do not rewrite any file under `data/`.

## How to start

```text
cd AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2
set PYTHONPATH=src
python -m uvicorn warehouse_control.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/  
Optional API browser: http://127.0.0.1:8000/docs  

**Stop the test pack** if the header ever shows `physical_control` as anything other than `disabled`.

---

## D-01 — Page is observe-only

| | |
|---|---|
| **Test description** | Open the home page. Confirm it is a control-tower wall, not a robot console. |
| **What we are testing** | UI loads; OT is off; no write buttons that actually POST. |
| **Files** | `src/warehouse_control/static/dashboard.html` · `src/warehouse_control/api.py` (`GET /`, `GET /ui`, `GET /health`) |
| **Steps** | Open `/`. Read header subtitle and the red/deny badge. |
| **Expected** | Title **Warehouse control tower**. Subtitle **Observe and refuse. Not a live warehouse.** Badge **`physical_control: disabled`**. |
| **Pass / Fail** | |

---

## D-02 — Estate KPI strip

| | |
|---|---|
| **Test description** | Four numbers at the top match the brownfield diagnostics, not a live plant. |
| **What we are testing** | Dashboard KPIs are counts from CSVs via `GET /diagnostics`. |
| **Files** | `src/warehouse_control/diagnostics.py` · `data/raw/robots.csv` · `data/raw/maintenance.csv` · `data/raw/inventory_snapshot.csv` · `data/raw/tasks.csv` |
| **Steps** | Wait for the four KPI tiles (not “Loading…”). |
| **Expected** | **35** Expired cert, still connected · **176** Open CMMS + AVAILABLE · **7382** Inventory qty disagreements · **7351** WES ≠ fleet tasks |
| **Pass / Fail** | |

---

## D-03 — Expired cert robot is refused (G1)

| | |
|---|---|
| **Test description** | Default robot is still connected but must not be treated as assignable. |
| **What we are testing** | Safety cert EXPIRED ⇒ Eligibility **INELIGIBLE** (G1). Connected ≠ usable. |
| **Files** | `data/raw/robots.csv` (row `RBT-0020`: `safety_cert_status=EXPIRED`, `connectivity=INTERMITTENT`) · `data/raw/tasks.csv` (`TSK-000004-1`) · `src/warehouse_control/eligibility/policy.py` · `GET /eligibility` |
| **Steps** | Leave **Robot id** = `RBT-0020`, **Task id** = `TSK-000004-1`. Click **Observe robot** (or use the auto-load). |
| **Expected** | Message **Do not assign. INELIGIBLE.** Output includes **G1 — Safety cert expired or missing**. |
| **Pass / Fail** | |

---

## D-04 — Open CMMS also refuses the same robot (G2)

| | |
|---|---|
| **Test description** | Same robot also has an open work order while Fleet still says AVAILABLE. |
| **What we are testing** | Open CMMS without a SafetyOfficer Approval record ⇒ **G2**. `safety_release_recorded=N` is not Approval. |
| **Files** | `data/raw/maintenance.csv` (`WO-000503`, `RBT-0020`, `cmms_status=OPEN`, `fleet_availability=AVAILABLE`, `safety_release_recorded=N`) |
| **Steps** | Same inputs as D-03. In the JSON, find `gates_failed` and `evidence`. |
| **Expected** | **G2 — Open / in-progress CMMS work order** is listed. Evidence id **WO-000503**. |
| **Pass / Fail** | |

---

## D-05 — Assign button does nothing

| | |
|---|---|
| **Test description** | Operator cannot dispatch from this screen. |
| **What we are testing** | Assign is blocked in the UI. API has no POST `/missions`. |
| **Files** | `dashboard.html` (`btn-assign`, `blocked("Assign")`) · `api.py` (GET-only; no `/missions`) |
| **Steps** | Click **Assign (blocked)**. Optionally watch Network tab. |
| **Expected** | Alert: assign is not available; physical control stays disabled. **No** POST request. **No** robot command. |
| **Pass / Fail** | |

---

## D-06 — Healthy-looking robot with open WO is still refused

| | |
|---|---|
| **Test description** | HEALTHY + VALID cert + ONLINE is not enough when CMMS is in progress. |
| **What we are testing** | Available ≠ suitable. G2 on a “good” registry row. |
| **Files** | `data/raw/robots.csv` (`RBT-0001`: HEALTHY, VALID, ONLINE) · `data/raw/maintenance.csv` (`WO-000380`, `IN_PROGRESS`, `fleet_availability=AVAILABLE`) |
| **Steps** | Set Robot id **`RBT-0001`**. Keep any known task id (e.g. `TSK-000004-1`). Click **Observe robot**. |
| **Expected** | **INELIGIBLE**. **G2** present. Work order **WO-000380**. Do **not** treat registry HEALTHY as a pass. |
| **Pass / Fail** | |

---

## D-07 — Inventory keeps three quantities (G5)

| | |
|---|---|
| **Test description** | Default SKU/location must show WMS, ERP, and vision — not one “available qty”. |
| **What we are testing** | Unequal qty ⇒ `uncertain=true`. Do not pick a winner by system name. |
| **Files** | `data/raw/inventory_snapshot.csv` line 2: `DC-01,SKU-01146,DC-01-Z03-B017,205,205,202,...` · columns `wms_qty,erp_qty,vision_qty` · `data/reference/skus.csv` (`SKU-01146`) · `src/warehouse_control/inventory/uncertainty.py` · `GET /inventory` |
| **Steps** | Leave Warehouse `DC-01`, SKU `SKU-01146`, Location `DC-01-Z03-B017`. Click **Observe inventory**. |
| **Expected** | Line **WMS 205 / ERP 205 / vision 202**. Message **Uncertain — keep WMS/ERP/vision.** JSON `uncertain: true`. |
| **Pass / Fail** | |

---

## D-08 — Pick as known is blocked

| | |
|---|---|
| **Test description** | UI must not let the operator allocate that bin as a single known quantity. |
| **What we are testing** | G5 / I3 in the product: no `true_qty` action. |
| **Files** | `dashboard.html` (`btn-pick`) · `src/warehouse_control/legacy/inventory.py` (`legacy_available_qty` is **not** the UI path) |
| **Steps** | Click **Pick as known (blocked)**. |
| **Expected** | Alert that pick is not available. CSV quantities **unchanged**. |
| **Pass / Fail** | |

---

## D-09 — Cutoff order is not on-time from OMS (I7)

| | |
|---|---|
| **Test description** | Default order is delayed in TMS; OMS staging must not be shown as on-time. |
| **What we are testing** | Carrier cutoff uses TMS DELAYED over OMS SLA. Miss cutoff is legal advice; zone release is not. |
| **Files** | `data/raw/orders.csv` (`ORD-000004`: `oms_status=STAGED`, `wms_status=EXCEPTION`) · `data/raw/shipments.csv` (`SHP-000004`: `tms_status=DELAYED`, `carrier=Carrier-A`, empty `actual_departure`) · `data/shadow/ops_emails.txt` (Carrier-A / OMS SLA stale) · `src/warehouse_control/fulfillment/cutoff.py` · `GET /orders/{id}/cutoff` |
| **Steps** | Leave Order id **`ORD-000004`**. Click **Observe cutoff**. |
| **Expected** | Message **Not on-time from OMS alone.** JSON `on_time: false`, `tms_status: DELAYED`, conflict `CUTOFF_STALE`. `physical_control: disabled`. |
| **Pass / Fail** | |

---

## D-10 — Release zone is denied (G7)

| | |
|---|---|
| **Test description** | Cutoff pressure must not open a safety zone. |
| **What we are testing** | Intent `release_zone` ⇒ Decision **DENY** G7. Execution not applied. |
| **Files** | `dashboard.html` (`btn-zone` + Safety decision preview) · `src/warehouse_control/decision/engine.py` · `GET /dashboard/snapshot` field `safety_preview` · `GET /preview/decide?intent=release_zone` |
| **Steps** | Read **Safety decision preview** panel. Then click **Release zone (denied)**. |
| **Expected** | Preview JSON `decision: DENY`, `reason_codes` includes **G7**, `execution.applied: false`. Button only alerts; no POST. |
| **Pass / Fail** | |

---

## D-11 — Shipped-looking order is not digitally complete (G6 / I4)

| | |
|---|---|
| **Test description** | OMS SHIPPED is not enough while the warehouse task is still EXECUTING. |
| **What we are testing** | Order completeness needs WES and fleet terminal COMPLETE. This panel’s cutoff call does not close the order. |
| **Files** | `data/raw/orders.csv` (`ORD-000968`: `oms_status=SHIPPED`, `wms_status=SHIPPED`) · `data/raw/tasks.csv` (`TSK-000968-1`: `wes_status=EXECUTING`, `fleet_status=EXECUTING`, `assigned_robot=RBT-0333`) · `src/warehouse_control/tasks/reconcile.py` |
| **Steps** | In the browser open `http://127.0.0.1:8000/dashboard/snapshot` and read `order_968`. Optional: `http://127.0.0.1:8000/tasks/TSK-000968-1/reconcile`. |
| **Expected** | `order_968.completable` is **false**. Task is still EXECUTING (not COMPLETE). Do not treat SHIPPED as done. |
| **Pass / Fail** | |

---

## D-12 — Task WES ≠ fleet (G6)

| | |
|---|---|
| **Test description** | The default task on the robot panel has split execution state. |
| **What we are testing** | Dual status retained. Not completable when WES ≠ fleet. |
| **Files** | `data/raw/tasks.csv` (`TSK-000004-1`: `wes_status=EXECUTING`, `fleet_status=FAILED`, `assigned_robot=RBT-0644`) |
| **Steps** | Open `http://127.0.0.1:8000/tasks/TSK-000004-1/reconcile`. |
| **Expected** | `conflict: true`, `kind: TASK_STATUS`, `completable: false`. Both statuses visible. |
| **Pass / Fail** | |

---

## D-13 — Alias collision is kept (I9)

| | |
|---|---|
| **Test description** | One alias string maps to two robots. UI must not merge them. |
| **What we are testing** | `IDENTITY_COLLISION`. Canonical id stays `robot_id`. |
| **Files** | `data/raw/robot_aliases.csv` (`RBT-0001` CMMS = `BOT-COLLISION-01`; `RBT-0002` WMS = `BOT-COLLISION-01`) · `src/warehouse_control/identity/resolver.py` · `GET /identity/alias/{alias}` |
| **Steps** | Leave Alias **`BOT-COLLISION-01`**. Click **Resolve alias**. |
| **Expected** | Message **Identity collision — keep both robots.** JSON lists **RBT-0001** and **RBT-0002**. No single “true” robot. |
| **Pass / Fail** | |

---

## D-14 — Unmatched floor name is not guessed

| | |
|---|---|
| **Test description** | Email name AMR-044 must not be coerced to a registry id. |
| **What we are testing** | Unmatched ⇒ ABSTAIN / unmatched flag. I9. |
| **Files** | `data/shadow/ops_emails.txt` (subject **AMR-044 low speed only**) · `identity/resolver.py` (`KNOWN_UNMATCHED_FLOOR_NAMES`) |
| **Steps** | Set Alias to **`AMR-044`**. Click **Resolve alias**. |
| **Expected** | **Unmatched floor name — do not guess a robot_id.** `unmatched: true`, `robot_ids: []`. |
| **Pass / Fail** | |

---

## D-15 — Inject replay does not write the warehouse

| | |
|---|---|
| **Test description** | Charger-down inject is in-memory only. Gates stay closed. |
| **What we are testing** | Overlay does not rewrite CSV. `execution_applied=false`. Safety bypass still DENY. |
| **Files** | `scenarios/inject_02.md` · `src/warehouse_control/injects/catalog.py` · `src/warehouse_control/injects/replay.py` · `data/raw/control_assets.csv` (read, not written) · `GET /injects/inject_02/replay?task_id=TSK-000004-1` |
| **Steps** | Select **inject_02 charger down**. Click **Replay inject**. Then confirm `data/raw/control_assets.csv` file timestamp/content unchanged. |
| **Expected** | Message **Gates intact. Execution applied=false.** JSON `physical_control: disabled`, `safety_bypass` not ALLOW. CSVs not modified. |
| **Pass / Fail** | |

---

## D-16 — Network is GET-only

| | |
|---|---|
| **Test description** | Whole session uses read APIs. |
| **What we are testing** | CORS and routes allow GET only. |
| **Files** | `api.py` (`allow_methods=["GET"]`) · `tests/test_dashboard.py` |
| **Steps** | DevTools → Network. Click every dashboard button once (including the three blocked ones). |
| **Expected** | Requests to `/health`, `/diagnostics`, `/dashboard/snapshot`, `/eligibility`, `/identity/…`, `/inventory`, `/orders/…/cutoff`, `/injects/…/replay` are **GET**. Zero POST/PUT/PATCH. Zero `/missions`. |
| **Pass / Fail** | |

---

## Fail the pack immediately if

- Badge is not `physical_control: disabled`
- Assign / Pick / Release appears to succeed
- Inventory shows a single `available_qty` as truth
- Alias resolver returns only one robot for `BOT-COLLISION-01`
- Any `data/` CSV was edited during the test

Automated companion: from repo root, `set PYTHONPATH=src` then `python -m pytest tests/test_dashboard.py -q`.
