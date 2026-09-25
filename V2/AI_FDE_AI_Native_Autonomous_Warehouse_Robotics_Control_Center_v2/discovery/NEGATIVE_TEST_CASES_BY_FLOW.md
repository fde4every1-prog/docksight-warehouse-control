# Negative test cases from raw CSVs — by UI flow

Every case is a **refuse / conflict / uncertain** outcome. Do not clean the CSVs to make the UI look green. Invoke the named **flow** in the Replit (or Repo 2) UI. Estate counts come from `src/warehouse_control/diagnostics.py`.

---

## How to read this pack

| Column | Meaning |
|---|---|
| Flow | Screen or action that must load these files |
| Negative scenario | What must go wrong on that screen |
| CSV / file (details) | Exact extract and the bad values |
| Must happen | Pass condition for the UI |

---

## 1. Order check / complete flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-ORD-01 | OMS and WMS disagree | `data/raw/orders.csv` `ORD-000004`: `oms_status=STAGED`, `wms_status=EXCEPTION` (1,283 such orders) | Show **both** statuses. Do **not** mark Complete. |
| N-ORD-02 | Header looks shipped; task still open | `orders.csv` `ORD-000968`: OMS=WMS=`SHIPPED`. `tasks.csv` `TSK-000968-1`: `wes_status=EXECUTING`, `fleet_status=EXECUTING`, `assigned_robot=RBT-0333` | **completable=false**. SHIPPED is not E2E done. |
| N-ORD-03 | WES ≠ fleet on the same task | `tasks.csv` `TSK-000004-1`: WES `EXECUTING`, fleet `FAILED`, assigned `RBT-0644`. Also `TSK-000004-2`: `QUEUED` vs `EXECUTING` (7,351 split tasks) | Conflict `TASK_STATUS`. Do not close the order. |
| N-ORD-04 | Shadow wave is not order priority | `data/shadow/wave_priority_FINAL_v7.csv` `ORD-002442`, `manual_priority=P2`, `reason=manager_override` | Treat as **untrusted overlay**. Must not overwrite `orders.csv` priority. |

**Flow to invoke:** Order lookup / Complete order / Task list for that order.

---

## 2. Cutoff / on-time / ship flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-CUT-01 | TMS delayed; OMS cutoff is not live | `orders.csv` `ORD-000004`: `carrier_cutoff=2026-09-03T20:16:00`, SAME_DAY. `shipments.csv` `SHP-000004`: `tms_status=DELAYED`, `carrier=Carrier-A`, **`actual_departure` empty** | **on_time=false**. Do not fill departure. |
| N-CUT-02 | Email says cutoff moved; that is not Policy | `data/shadow/ops_emails.txt` subject **Carrier cutoff change**: Carrier-A −35 min; “OMS SLA table will not refresh until midnight” | Show `CUTOFF_STALE`. Email does not rewrite OMS cutoff. Recommending **miss cutoff** is legal; releasing a zone is not. |
| N-CUT-03 | Timezone mix across DCs | `data/reference/warehouses.csv` `DC-01` timezone `UTC+1` vs `DC-02` `UTC+5:30` | Do not sort mixed events as one local clock. |

**Flow to invoke:** Order cutoff / SLA / “will we make the truck?”

---

## 3. Robot selection / eligibility flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-RBT-01 | Expired cert, still connected | `robots.csv` `RBT-0021`: `safety_cert_status=EXPIRED`, `connectivity=ONLINE`, HEALTHY (35 expired-but-connected in estate) | **G1 INELIGIBLE**. ONLINE does not pass. |
| N-RBT-02 | HEALTHY robot, open CMMS | `robots.csv` `RBT-0001`: HEALTHY, VALID, ONLINE. `maintenance.csv` `WO-000380`: `IN_PROGRESS`, `fleet_availability=AVAILABLE`, `safety_release_recorded=Y` | **G2 INELIGIBLE**. AVAILABLE and Y are not Approval. |
| N-RBT-03 | Calibration overdue | `robots.csv` `RBT-0013`: cert VALID, `calibration_status=OVERDUE`. No maintenance row. | **I2 INELIGIBLE**. |
| N-RBT-04 | Offline | `robots.csv` `RBT-0028`: VALID cert, **OFFLINE**. `maintenance.csv` `WO-000021` is only **PLANNED**. | Not selectable. |
| N-RBT-05 | Intermittent + expired (compound) | `robots.csv` `RBT-0020`: EXPIRED, **INTERMITTENT**, HEALTHY. `maintenance.csv` `WO-000503`: OPEN + AVAILABLE, release N | INELIGIBLE (G1+G2); connectivity is not a pass. |
| N-RBT-06 | Assigned robot is the wrong DC | `tasks.csv` `TSK-000001-2` warehouse **DC-17**, `assigned_robot=RBT-0105`. `robots.csv` `RBT-0105` warehouse **DC-03**. `maintenance.csv` `WO-000144` IN_PROGRESS | Do **not** default-select `assigned_robot`. `SITE_MISMATCH`. |
| N-RBT-07 | Assignee on delayed MOVE is unsafe | `tasks.csv` `TSK-000004-1` **DC-16**, assigned `RBT-0644`. `robots.csv` `RBT-0644` is **DC-17**, cal **OVERDUE**. `maintenance.csv` `WO-000010` IN_PROGRESS | INELIGIBLE. “Already assigned” ≠ OK. |

**Flow to invoke:** Select robot / eligibility / assign preview.

---

## 4. Allocation / dispatch flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-ALC-01 | Legacy score would pick the unsafe robot | `src/warehouse_control/legacy/allocator.py` uses battery + ONLINE only. Contrasted with `robots.csv` + `maintenance.csv` on `RBT-0001` / `RBT-0020` | Product path must **filter-then-score**. Fail if UI matches legacy `choose_robot`. |
| N-ALC-02 | No payload on the task | `tasks.csv` has **no** `payload_kg` column | Do not assume fit. Preview may rank after hard gates; **do not execute**. Missing payload is G8, not a free pass. |
| N-ALC-03 | Live assign | No CSV authorizes OT. `GET` APIs only in Repo 2 | Assign button must refuse. No POST `/missions`. |

**Flow to invoke:** Allocate / Assign / Confirm robot.

---

## 5. Inventory / pick flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-INV-01 | Three qty fields disagree | `inventory_snapshot.csv` `DC-01`,`SKU-01146`,`DC-01-Z03-B017`: `wms_qty=205`, `erp_qty=205`, `vision_qty=202` (7,382 disagreeing rows) | Show all three. `uncertain=true`. **No** single available qty. |
| N-INV-02 | Agreeing qty still not pickable | Same file `DC-13`,`SKU-01146`,`DC-13-Z02-B045`: 191/191/191 but that does **not** prove physical count | May show sources agree; still not “physical truth.” |
| N-INV-03 | Quarantine | `inventory_snapshot.csv` `DC-17`,`SKU-01146`,`DC-17-Z08-B010`: 146/144/146, `inventory_status=QUARANTINE` | Do not pick. Qty still disagree. |
| N-INV-04 | Hazmat SKU | `data/reference/skus.csv` `SKU-00030`: `hazmat=Y`, `lot_controlled=Y` | Extra handling; not a normal pick if the UI has a hazmat gate. |

**Flow to invoke:** Inventory lookup / Pick / Allocate-as-known.

---

## 6. Identity / alias flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-ID-01 | Same alias, two robots | `robot_aliases.csv`: `RBT-0001` CMMS=`BOT-COLLISION-01`; `RBT-0002` WMS=`BOT-COLLISION-01` (6 colliding alias strings) | Keep **both** ids. No merge. |
| N-ID-02 | Floor name not in registry | `data/shadow/ops_emails.txt` **AMR-044**. Not an exact alias in `robot_aliases.csv`. `scenarios/cascade_001.json` also names AMR-044 | Unmatched. Do **not** coerce to `RBT-0044`. |
| N-ID-03 | Low-confidence camera is not identity | `data/telemetry/vision_observations.csv` `DC-01-CAM-18` observed `RBT-0001`, confidence **0.566**. Email: “Do not trust camera 18” | Observation only. Must not overwrite `robots.csv` id. |

**Flow to invoke:** Search by alias / scan camera / identity resolve.

---

## 7. Zone / path / safety flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-ZN-01 | Restricted dest | `zones.csv` `DC-01-Z05`: `robot_access=RESTRICTED`. `tasks.csv` `TSK-000019-2` dest **DC-01-Z05** | **G4** refuse path/assign. |
| N-ZN-02 | Map vs email (MAP_STALE) | Email: move to Z09, “WMS map has NOT been updated.” `zones.csv` `DC-01-Z09`: `physical_change_pending=NO`, access YES | Conflict `MAP_STALE`. Email does not update the map. |
| N-ZN-03 | Unresolved e-stop | `safety_events.csv` `SAFE-DC-01-003`: `E_STOP`, zone `DC-01-Z01`, `resolved=N`, source OPERATOR | Do not treat zone as clear. No software e-stop reset (G7). |
| N-ZN-04 | Unresolved e-stop (fleet) | `safety_events.csv` `SAFE-DC-01-008`: `E_STOP`, `DC-01-Z09`, `resolved=N`, source FLEET | Same: refuse zone release. |
| N-ZN-05 | Zone breach (PLC) | `safety_events.csv` `SAFE-DC-01-004`: `ZONE_BREACH`, `DC-01-Z12`, source SAFETY_PLC (`resolved=Y` on this row — still not a software waiver for a new release) | PLC events are evidence. UI must not enable OT. |

**Flow to invoke:** Path / release zone / safety override.

---

## 8. Asset / charger / inject flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-AST-01 | Sorter down (matches email “sorter 2”) | `control_assets.csv` `DC-01-SORTER-03`: `state=DOWN` | Do not pretend outbound/sort is healthy. Overlay only; do not rewrite CSV. |
| N-AST-02 | Dock down | `control_assets.csv` `DC-01-DOCK_DOOR-04`: DOWN. Replay `scenarios/inject_03.md` | Allocation may ABSTAIN; **execution_applied=false**. |
| N-AST-03 | AS/RS down | `control_assets.csv` e.g. `DC-03-ASRS-02` DOWN. Replay `scenarios/inject_01.md` | Same: in-memory overlay, gates intact. |
| N-AST-04 | Preferred charger not usable | `charging_state.csv` `RBT-0002`: `charging_eligible=N`, charger `DC-01-CHARGER-01`. `RBT-0003`: `next_pm_days=-2` | Do not assume the robot can charge. |
| N-AST-05 | Charger DOWN at another site | `control_assets.csv` `DC-02-CHARGER-07`: DOWN, OVERDUE | Inject `inject_02`; still no OT. |

**Flow to invoke:** Inject replay / asset status / charge-then-assign.

---

## 9. Shadow / supervisor-override flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-SH-01 | “Supervisor approved tonight” | `ops_emails.txt` **AMR-044 low speed only**: CMMS open, supervisor approved, Fleet AVAILABLE | **MUST_NOT** become Approval or Policy. Still G2. |
| N-SH-02 | Manager override wave | `wave_priority_FINAL_v7.csv` `reason=manager_override` (e.g. `ORD-000107`) | Input only. Must not skip G1–G7. |
| N-SH-03 | Cascade narrative | `scenarios/cascade_001.json` (cutoff + congestion + AMR-044 + charger fail) | Correlate as inject; **cutoff must not release a restricted zone**. |

**Flow to invoke:** Any screen with an “override / approved / ignore gates” control.

---

## 10. Telemetry / clock / events flow

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-CLK-01 | Business time ≠ ingest time | `data/raw/events.jsonl` `EVT-00006783`: `event_time=2026-08-31T11:57:00`, `recorded_time=2026-08-31T11:56:38`, task `TSK-000968-1` (7,448 skewed events) | Order by **`event_time`**, keep both timestamps. |
| N-CLK-02 | Duplicate telemetry packet | `data/telemetry/robot_telemetry.csv` (80 duplicate packets estate-wide; fixture family `RBT-0194`) | Drop **exact** duplicate key only. Do not treat dup as a new pose. |
| N-CLK-03 | Uncertain / stale pose | Same file `quality` values `UNCERTAIN` / `STALE` (e.g. `RBT-0001` rows with UNCERTAIN) | Do not use as identity or as “robot is free.” |

**Flow to invoke:** Live map / last-seen / event timeline.

---

## 11. Labor / capacity flow (if the Replit app has it)

| ID | Negative scenario | CSV / file (details) | Must happen |
|---|---|---|---|
| N-LAB-01 | Understaffed shift | `labor_capacity.csv` `DC-01` shift **1**: planned **52**, actual **43** | Show shortfall. Must not auto-raise robot autonomy to cover labor. |
| N-LAB-02 | Overstaff vs plan | `DC-01` shift **2**: planned 56, actual **81** | Display only; not a safety waiver. |

**Flow to invoke:** Labor / wave release / “we need more robots.”

---

## Estate-scale negatives (dashboard KPIs)

From the same CSVs via diagnostics — UI must not round them to zero:

| KPI | Count | Source CSVs |
|---|---|---|
| Expired cert but connected | **35** | `robots.csv` |
| Open CMMS + fleet AVAILABLE | **176** | `maintenance.csv` |
| Inventory qty disagreements | **7382** | `inventory_snapshot.csv` |
| WES ≠ fleet | **7351** | `tasks.csv` |
| OMS ≠ WMS | **1283** / 3500 | `orders.csv` |

---

## Pack fail (any flow)

- Complete or On-time on `ORD-000004`
- Single `available_qty` for `SKU-01146` @ `DC-01-Z03-B017`
- `BOT-COLLISION-01` resolved to one robot
- `AMR-044` mapped to `RBT-0044`
- Zone release allowed under cutoff pressure
- Any `data/` CSV rewritten
