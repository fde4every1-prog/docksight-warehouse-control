# Order fulfillment — fleet task assignment (positive and negative)

**Flow:** Order → warehouse tasks → fleet `assigned_robot`.  
**UI:** Replit fulfillment / assign screen (or Repo 2 `/eligibility` + `/preview/allocate`).  
**Rule:** Positive means **the assignment is internally consistent and may be previewed**. It does **not** mean Complete, On-time, or live dispatch. `tasks.csv` has no `payload_kg`. Physical control stays disabled.

Join keys: `orders.order_id` = `tasks.order_id` = `shipments.order_id`; `tasks.assigned_robot` = `robots.robot_id` (must still check `robots.warehouse_id`).

---

## Positive

| Test case | What we are testing | How to invoke | CSV files and details | Outcome |
|---|---|---|---|---|
| **P-FA-01** Consistent in-flight assignment | One task where WES and fleet **agree**, the assigned robot is the **same DC**, cert/cal are VALID, ONLINE, and CMMS is not open. | Open order **`ORD-000072`** → task **`TSK-000072-1`** → robot **`RBT-0344`**. | `orders.csv` `ORD-000072`: `DC-09`, OMS **STAGED**, WMS **STAGED**, EXPEDITE. `shipments.csv` `SHP-000072`: TMS **AT_DOCK**, Carrier-D. `tasks.csv` `TSK-000072-1`: PACK_FEED, assigned **RBT-0344**, WES **EXECUTING**, fleet **EXECUTING**, source `DC-09-Z08`, dest `DC-09-Z06`. `robots.csv` `RBT-0344`: **DC-09**, TUGGER, HEALTHY, payload 1500, cert **VALID**, cal **VALID**, **ONLINE**. `maintenance.csv` `WO-000370`: **CLOSED**. `zones.csv` `DC-09-Z06`: PACK, `robot_access=YES`. `robot_aliases.csv` fleet name `DC-09-TUGGER-021` (do not replace `robot_id`). | **Pass:** UI shows this task as an agreed EXECUTING assignment; robot eligible for **preview**. **Fail:** hides the robot because battery is 31, or marks the **whole order** Complete (sibling tasks disagree — see N-FA-06). |
| **P-FA-02** Preview a valid same-DC robot | For a queued pick, the UI may **recommend** a robot that passes hard gates. It must not blindly keep `assigned_robot`. | Task **`TSK-000001-2`**. Candidate **`RBT-0634`**. | `tasks.csv` `TSK-000001-2`: order `ORD-000001`, **DC-17**, PICK, WES **QUEUED**, fleet **QUEUED**, dest `DC-17-Z09`, assigned `RBT-0105` (wrong DC — ignore for this positive). `robots.csv` `RBT-0634`: **DC-17**, HEALTHY, VALID/VALID/ONLINE, payload 1500. `maintenance.csv`: **no open WO**. `zones.csv` `DC-17-Z09`: `robot_access=YES`. `orders.csv` `ORD-000001`: OMS=WMS **PICKING**. | **Pass:** preview lists `RBT-0634` (or another DC-17 VALID/ONLINE robot with no OPEN/IN_PROGRESS WO); dual QUEUED shown; **no live assign**. **Fail:** auto-keeps `RBT-0105`. |
| **P-FA-03** Dual EXECUTING is a valid in-progress state | Fleet and WES both EXECUTING is **agreement**, not a split. Do not treat as FAILED. | Same as P-FA-01 (`TSK-000072-1`). | `tasks.csv` `wes_status=EXECUTING` and `fleet_status=EXECUTING`. | **Pass:** status = in progress / assigned. **Fail:** shown as conflict or as Complete. |

Live dispatch is **never** a positive in this dataset.

---

## Negative

| Test case | What we are testing | How to invoke | CSV files and details | Outcome |
|---|---|---|---|---|
| **N-FA-01** Assigned robot is a different DC | `assigned_robot` is not Eligibility. | Order `ORD-000001` → **`TSK-000001-2`** → **`RBT-0105`**. | `tasks.csv`: task warehouse **DC-17**, assigned `RBT-0105`. `robots.csv` `RBT-0105`: warehouse **DC-03**, FORK_AMR. `maintenance.csv` `WO-000144`: **IN_PROGRESS**, AVAILABLE. | **INELIGIBLE** / `SITE_MISMATCH`. Do not default-select this robot. |
| **N-FA-02** WES ≠ fleet — assignment not acknowledged | Cannot treat the task as fleet-complete or safely re-dispatch. | **`TSK-000004-1`** on **`ORD-000004`**. | `tasks.csv`: DC-16 MOVE, assigned `RBT-0644`, WES **EXECUTING**, fleet **FAILED**. `orders.csv`: OMS STAGED, WMS EXCEPTION. `shipments.csv` `SHP-000004`: **DELAYED**. | Conflict `TASK_STATUS`. **completable=false**. Do not assign another robot to “finish” it without G6. |
| **N-FA-03** Current assignee fails cal + WO + site | The robot already on the task is still unsafe. | Same task, robot **`RBT-0644`**. | `robots.csv` `RBT-0644`: **DC-17** (task is DC-16), cal **OVERDUE**, DEGRADED. `maintenance.csv` `WO-000010`: **IN_PROGRESS**. | **INELIGIBLE** (I2 + G2 + site). “Already assigned” ≠ OK. |
| **N-FA-04** Expired cert still ONLINE | Fleet connectivity must not win. | Try to assign **`RBT-0021`** (or `RBT-0020`) to any DC-01 task. | `robots.csv` `RBT-0021`: EXPIRED, ONLINE, HEALTHY. `RBT-0020`: EXPIRED, INTERMITTENT + `WO-000503` OPEN. | **G1 INELIGIBLE**. |
| **N-FA-05** Open CMMS, registry HEALTHY | Available ≠ suitable. | Assign **`RBT-0001`**. | `robots.csv`: VALID, ONLINE, HEALTHY. `maintenance.csv` `WO-000380`: IN_PROGRESS, fleet AVAILABLE. | **G2 INELIGIBLE**. |
| **N-FA-06** Order header agrees; other tasks split | One good assignment does not complete fulfillment. | Stay on **`ORD-000072`** after P-FA-01. Open sibling tasks. | `tasks.csv` `TSK-000072-2`: ASSIGNED vs EXECUTING (`RBT-0370`). `TSK-000072-3`: QUEUED vs COMPLETE. `TSK-000072-4`: QUEUED vs COMPLETE. | Order **not** Complete. Show each task’s two statuses. |
| **N-FA-07** SHIPPED order, task still EXECUTING | OMS SHIPPED is not fleet complete. | **`ORD-000968`** → **`TSK-000968-1`**. | `orders.csv`: OMS=WMS **SHIPPED**. `tasks.csv`: PACK_FEED, WES=fleet **EXECUTING**, assigned **`RBT-0333`**. `robots.csv` `RBT-0333`: **DC-09** (task **DC-02**), MAINTENANCE, cal **OVERDUE**. `maintenance.csv` `WO-000251`: IN_PROGRESS, AVAILABLE. | **completable=false**. Robot INELIGIBLE. Do not close the order. |
| **N-FA-08** Restricted destination | Must not assign any fleet robot into the zone. | **`TSK-000019-2`**. | `tasks.csv`: dest **`DC-01-Z05`**, QUEUED/QUEUED. `zones.csv` `DC-01-Z05`: **RESTRICTED**. | **G4** refuse path/assign. |
| **N-FA-09** Alias is not a fleet id | Do not assign by colliding alias. | Search **`BOT-COLLISION-01`**. | `robot_aliases.csv`: CMMS of `RBT-0001` and WMS of `RBT-0002`. | Keep both ids; assign neither as “the” robot. |
| **N-FA-10** Cutoff pressure / email override | DELAYED or “supervisor approved” must not force a fleet assign. | `ORD-000004` + `ops_emails.txt` AMR-044 / Carrier-A. | `shipments.csv` DELAYED. `ops_emails.txt` supervisor approved tonight. `wave_priority_FINAL_v7.csv` is not fleet authority. | Miss cutoff may be **recommended**. Assign / zone release still **DENY**. |
| **N-FA-11** Live fleet write | No CSV is a motion command. | Any Assign confirm. | None. Repo 2 API is GET-only. | No POST `/missions`. `applied=false`. |

---

## Suggested run order

1. **P-FA-01** → **P-FA-03** → **N-FA-06** (same order: one good task, order still open)  
2. **P-FA-02** → **N-FA-01** (same queued task: good preview vs bad assignee)  
3. **N-FA-02** → **N-FA-03** → **N-FA-10** (`ORD-000004` chain)  
4. **N-FA-07** (`ORD-000968`)  
5. **N-FA-04, 05, 08, 09, 11**

**Hard fail:** Complete on `ORD-000072` or `ORD-000968`; assign `RBT-0105` / `RBT-0644` / `RBT-0333`; live dispatch; any `data/` rewrite.
