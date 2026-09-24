# Replit UI test scenarios — order check and allocation

Use the V2 CSVs as-is. Do not clean conflicts. There is **no** order in this dataset that is digitally complete (every task COMPLETE in both WES and fleet). Happy path means **lookup and display are correct**, not “the warehouse finished.”

UI under test: teammate Replit app. Data root: `data/raw/`.

---

## A. Order check (start here)

| Test case | Type | What we are testing | Input | CSV files it uses | Expected outcome |
|---|---|---|---|---|---|
| **TC-O1** Order header lookup | **Happy path** | Open one order and show every claimant’s status without inventing a single “true status.” OMS and WMS happen to agree on this row. Shipment has actually departed. | Order id **`ORD-000968`** | `data/raw/orders.csv` (`ORD-000968`: warehouse `DC-02`, `oms_status=SHIPPED`, `wms_status=SHIPPED`, `carrier_cutoff=2026-08-31T14:17:00`) · `data/raw/shipments.csv` (`SHP-000968`: `tms_status=DEPARTED`, `carrier=Carrier-B`, `planned_departure=2026-08-31T14:17:00`, `actual_departure=2026-08-31T14:19:00`) | **Pass if:** order is found; UI shows OMS **SHIPPED** and WMS **SHIPPED** as two fields (or clearly both); TMS **DEPARTED** with actual departure filled. **Fail if:** 404; statuses merged into one unlabeled chip; actual departure hidden. |
| **TC-O2** Order not complete / not on-time | **Failure** | Same order-check screen must refuse “Complete” and “On-time” when claimants disagree or the task is still open. | Order id **`ORD-000004`** | `data/raw/orders.csv` (`ORD-000004`: `DC-16`, `oms_status=STAGED`, `wms_status=EXCEPTION`, `service_level=SAME_DAY`, `carrier_cutoff=2026-09-03T20:16:00`) · `data/raw/shipments.csv` (`SHP-000004`: `tms_status=DELAYED`, `carrier=Carrier-A`, `actual_departure` **empty**) · `data/raw/tasks.csv` (`TSK-000004-1`: `wes_status=EXECUTING`, `fleet_status=FAILED`; `TSK-000004-2`: `QUEUED` vs `EXECUTING`) | **Pass if:** UI shows OMS≠WMS; TMS **DELAYED**; **on-time = no**; **complete = no**; both task statuses visible; empty actual departure stays empty. **Fail if:** green Complete, On-time, or a single status such as STAGED only. |

**Do not use TC-O1 as “order complete.”** Companion check on the same happy order: `TSK-000968-1` in `tasks.csv` is still `EXECUTING` / `EXECUTING`. If the Replit screen has a Complete button, it must stay disabled for **both** TC-O1 and TC-O2.

---

## B. Allocation (robot ↔ task)

`tasks.csv` has **no** `payload_kg` column. A preview may rank a robot after hard gates; the UI still must **not** send a live assign.

| Test case | Type | What we are testing | Input | CSV files it uses | Expected outcome |
|---|---|---|---|---|---|
| **TC-A1** Preview a suitable same-site robot | **Happy path** | For a queued pick, the UI can **recommend** a robot in the same DC that is VALID, ONLINE, and has no open CMMS row. Assigned robot on the task is the wrong DC — UI must not treat `assigned_robot` as Eligibility. | Task **`TSK-000001-2`**. Candidate to accept: **`RBT-0634`**. | `data/raw/tasks.csv` (`TSK-000001-2`: order `ORD-000001`, warehouse **`DC-17`**, type PICK, `assigned_robot=RBT-0105`, `wes_status=QUEUED`, `fleet_status=QUEUED`, dest `DC-17-Z09`) · `data/raw/robots.csv` (`RBT-0634`: `DC-17`, HEALTHY, `safety_cert_status=VALID`, `calibration_status=VALID`, `connectivity=ONLINE`, `payload_kg=1500`) · `data/raw/maintenance.csv` (**no row** for `RBT-0634`) · `data/raw/zones.csv` (`DC-17-Z09`: `robot_access=YES`) · `data/raw/orders.csv` (`ORD-000001`) | **Pass if:** preview lists or selects **RBT-0634** (or another DC-17 robot with VALID cert, ONLINE, no OPEN/IN_PROGRESS WO); WES and fleet both **QUEUED** are shown; **no** live dispatch; confirm/assign stays preview-only. **Fail if:** UI auto-picks **RBT-0105** (that robot is `DC-03` in `robots.csv` and has `WO-000144` IN_PROGRESS). |
| **TC-A2** Refuse unsafe / mismatched assign | **Failure** | Must not allocate the assigned robot on the delayed MOVE task. Expired/overdue/open WO/site split all block. | Task **`TSK-000004-1`**. Robot the UI must **reject**: **`RBT-0644`** (the `assigned_robot`). Extra reject: **`RBT-0020`**. | `data/raw/tasks.csv` (`TSK-000004-1`: `DC-16`, MOVE, `assigned_robot=RBT-0644`, `wes_status=EXECUTING`, `fleet_status=FAILED`) · `data/raw/robots.csv` (`RBT-0644`: warehouse **`DC-17` not DC-16**, `calibration_status=OVERDUE`; `RBT-0020`: `safety_cert_status=EXPIRED`, `connectivity=INTERMITTENT`) · `data/raw/maintenance.csv` (`WO-000010` on `RBT-0644` IN_PROGRESS; `WO-000503` on `RBT-0020` OPEN + AVAILABLE) · `data/raw/orders.csv` / `shipments.csv` (`ORD-000004` / DELAYED) | **Pass if:** Eligibility **INELIGIBLE** / Assign disabled; reasons include site mismatch (task DC-16 vs robot DC-17), **I2/OVERDUE**, **G2** open WO, and for `RBT-0020` **G1 EXPIRED**; WES≠fleet shown; DELAYED cutoff does **not** override. **Fail if:** Assign succeeds, “AVAILABLE” from CMMS/fleet wins, or only battery/ONLINE is used (legacy `choose_robot` behaviour). |

---

## How the Replit tester should click

1. Run **TC-O1**, then **TC-O2** (do not skip).  
2. Run **TC-A1**, then **TC-A2**.  
3. After TC-A1/A2, confirm the CSV files on disk were **not** rewritten.

**Hard fail for the whole pack:** any POST that moves a robot, any single `available_qty` invented from inventory, any Complete/On-time on `ORD-000004`.

---

## C. Robot selection (one reason at a time)

Use a **Select robot** / eligibility screen. Pair each robot with a task so site is visible. `assigned_robot` on the task is **not** Eligibility.

`robots.csv` columns: `robot_id,warehouse_id,robot_type,vendor,fleet_id,firmware,battery_soc,battery_soh,health_status,payload_kg,safety_cert_status,calibration_status,connectivity`

| Test case | Type | What we are testing | Input | CSV files it uses | Expected outcome |
|---|---|---|---|---|---|
| **TC-R1** Same-DC, valid, no open WO | **Happy path** | UI may **preview-select** a robot that passes hard gates. Battery can be low; that is score, not a refuse. Still no live dispatch. | Robot **`RBT-0634`** for task **`TSK-000001-2`** | `data/raw/robots.csv` (`RBT-0634`: `DC-17`, CASE_PICKER, HEALTHY, `payload_kg=1500`, cert **VALID**, cal **VALID**, **ONLINE**, `battery_soc=13`) · `data/raw/maintenance.csv` (**no row** for this robot) · `data/raw/tasks.csv` (`TSK-000001-2`: warehouse **DC-17**, dest `DC-17-Z09`) · `data/raw/zones.csv` (`DC-17-Z09`, `robot_access=YES`) | **Pass:** selectable for **preview only**; show VALID / ONLINE / DC-17. **Fail:** hidden because battery is 13; or Assign executes; or UI prefers `assigned_robot` `RBT-0105`. |
| **TC-R2** Expired cert, still ONLINE | **Failure (G1)** | Connected ≠ usable. Isolate cert. This row has no open WO. | Robot **`RBT-0021`** | `data/raw/robots.csv` (`RBT-0021`: `DC-01`, HEALTHY, cert **EXPIRED**, cal VALID, **ONLINE**) · `data/raw/maintenance.csv` (no OPEN/IN_PROGRESS for `RBT-0021`) | **Pass:** **INELIGIBLE**; reason **G1 / expired cert**. **Fail:** selected because ONLINE or HEALTHY. |
| **TC-R3** Healthy registry, open CMMS | **Failure (G2)** | Fleet-looking HEALTHY + VALID + ONLINE is not Eligibility when CMMS is in progress. `safety_release_recorded=Y` is **not** SafetyOfficer Approval. | Robot **`RBT-0001`** | `data/raw/robots.csv` (`RBT-0001`: `DC-01`, HEALTHY, cert VALID, cal VALID, ONLINE) · `data/raw/maintenance.csv` (`WO-000380`: `IN_PROGRESS`, `fleet_availability=AVAILABLE`, `issue=lidar_calibration`, `safety_release_recorded=Y`) | **Pass:** **INELIGIBLE**; **G2**; WO **WO-000380** visible. **Fail:** selected because HEALTHY/AVAILABLE/release=Y. |
| **TC-R4** Calibration overdue | **Failure (I2)** | OVERDUE cal blocks even if cert is VALID and there is no open WO. | Robot **`RBT-0013`** | `data/raw/robots.csv` (`RBT-0013`: `DC-01`, DEGRADED, cert VALID, cal **OVERDUE**, ONLINE) · `data/raw/maintenance.csv` (**no row**) | **Pass:** **INELIGIBLE**; **I2 / OVERDUE**. **Fail:** selected because cert VALID. |
| **TC-R5** Offline | **Failure (OFFLINE)** | OFFLINE cannot be selected. WO is only PLANNED (not G2). | Robot **`RBT-0028`** | `data/raw/robots.csv` (`RBT-0028`: `DC-01`, HEALTHY, cert VALID, cal VALID, **OFFLINE**) · `data/raw/maintenance.csv` (`WO-000021`: **PLANNED**, not OPEN) | **Pass:** **INELIGIBLE / not selectable**; connectivity OFFLINE. **Fail:** selected because HEALTHY or WO not OPEN. |
| **TC-R6** Task `assigned_robot` is wrong site | **Failure (site)** | Do not select the robot printed on the task row if `robots.warehouse_id` ≠ `tasks.warehouse_id`. | Task **`TSK-000001-2`**, robot **`RBT-0105`** | `data/raw/tasks.csv` (task warehouse **DC-17**, `assigned_robot=RBT-0105`) · `data/raw/robots.csv` (`RBT-0105`: warehouse **DC-03**) · `data/raw/maintenance.csv` (`WO-000144`: IN_PROGRESS) | **Pass:** **not selectable**; show DC-03 vs DC-17. **Fail:** default-selected because it is `assigned_robot`. |
| **TC-R7** Alias collision | **Failure (I9)** | One alias must not resolve to a single selectable robot. | Alias **`BOT-COLLISION-01`** | `data/raw/robot_aliases.csv` (`RBT-0001` CMMS = `BOT-COLLISION-01`; `RBT-0002` WMS = `BOT-COLLISION-01`) · `data/raw/robots.csv` (both ids) | **Pass:** collision shown; **both** `RBT-0001` and `RBT-0002`; neither auto-picked. **Fail:** one robot selected as “the” robot. |
| **TC-R8** Unmatched floor name | **Failure (I9)** | Email name is not a registry id. | Name **`AMR-044`** | `data/shadow/ops_emails.txt` (subject AMR-044) · `data/raw/robot_aliases.csv` (no exact `AMR-044`) | **Pass:** unmatched; **no robot selected**. **Fail:** coerced to `RBT-0044` or similar. |
| **TC-R9** Restricted destination zone | **Failure (G4)** | Must not select a robot into a RESTRICTED dest, including a “good” robot. | Task **`TSK-000019-2`** (any DC-01 candidate, including `RBT-0634` is wrong DC — use a DC-01 preview robot). Dest **`DC-01-Z05`**. | `data/raw/tasks.csv` (`TSK-000019-2`: `DC-01`, dest **`DC-01-Z05`**, WES QUEUED, fleet QUEUED) · `data/raw/zones.csv` (`DC-01-Z05`: `robot_access=RESTRICTED`) · `data/raw/robots.csv` | **Pass:** path/assign **refused (G4)**; cutoff or queue pressure does not release the zone. **Fail:** any robot assigned into Z05. |
| **TC-R10** Assigned robot on failed MOVE | **Failure (mixed)** | The robot already on `TSK-000004-1` fails site, cal, and CMMS together. | Robot **`RBT-0644`**, task **`TSK-000004-1`** | `data/raw/tasks.csv` (task **DC-16**, assigned `RBT-0644`, EXECUTING vs FAILED) · `data/raw/robots.csv` (`RBT-0644`: **DC-17**, cal **OVERDUE**) · `data/raw/maintenance.csv` (`WO-000010` IN_PROGRESS) | **Pass:** **INELIGIBLE**; do not keep the current assignee. **Fail:** “already assigned” shown as selected/OK. |

Run **TC-R1 first**, then R2–R10 in order (one robot, one reason). After the pack, CSVs must be unchanged.

**Hard fail:** UI selects using only `battery_soc` + ONLINE (legacy `choose_robot` / `legacy_score` in `src/warehouse_control/legacy/allocator.py`).
