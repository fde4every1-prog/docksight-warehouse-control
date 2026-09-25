# 06 — Data quality profile

**Prompt 06.** Methods match `diagnostics.py` and Prompt 03 unless noted.  
**Do not treat disagreement as a defect to delete.**

---

## 1. Structural quality (keys)

| Check | Result |
|---|---|
| Duplicate PKs on warehouses, robots, orders, tasks, shipments, inventory triple, WO, safety, zones, assets, charging, SKUs, vendors, labor, shadow order_id, alias triple | **0** |
| 1:1 order ↔ shipment | **Yes** (3500/3500) |
| 3 aliases per robot | **712 × 3 = 2136** |
| 1 charging row per robot | **Yes** |
| Orphan FKs (task robot/order, alias, maint, tele, vision, inv sku/wh, events, shadow, zones on tasks) | **0** |

Structural rectangularity was also a V2 release check (`VERIFICATION.md` CSV rectangularity PASS).

---

## 2. Semantic quality (intentional brownfield)

Methods re-run 2026-09-17 except where cited from 03.

### Alias collisions

| | |
|---|---|
| Method | Count alias strings with frequency > 1 (`diagnostics.py`) |
| Count | **6** colliding strings (`BOT-COLLISION-00` … `05`) |
| Robots involved | **4** (`RBT-0001`–`RBT-0004`) |
| Unique alias strings | 2130 / 2136 |
| Retain? | **Yes** (I9). Dropping collisions is forbidden. |

### Inventory truth conflicts

| | |
|---|---|
| Method | `len({wms_qty, erp_qty, vision_qty}) > 1` |
| Any-of-three | **7,382 / 9,360 (78.9%)** |
| wms ≠ erp | **4,601** |
| wms ≠ vision | **5,415** |
| PK uniqueness | 0 dup (`warehouse_id`,`sku`,`location`) |
| Status mix | AVAILABLE 8009, QUARANTINE 690, HOLD 661 |
| Fixture | `DC-01,SKU-01146,DC-01-Z03-B017` 205/205/202 — **same in SQLite** |
| Retain? | **Yes** (I3). Forbidden to set wms_qty = vision_qty. |

### WES / fleet task conflicts

| | |
|---|---|
| Method | `wes_status != fleet_status` |
| Count | **7,351 / 8,732 (84.2%)** |
| WES | EXECUTING 1764, ASSIGNED 1761, BLOCKED 1754, COMPLETE 1732, QUEUED 1721 |
| Fleet | FAILED 1788, COMPLETE 1750, QUEUED 1740, ASSIGNED 1738, EXECUTING 1716 |
| Retain? | **Yes** (I4). |

### OMS / WMS order conflicts

| | |
|---|---|
| Method | `oms_status != wms_status` |
| Count | **1,283 / 3,500 (36.7%)** |
| WMS EXCEPTION | 976 (27.9%) |
| Retain? | **Yes**. |

### Maintenance vs fleet availability

| | |
|---|---|
| Method | cmms_status ∈ {OPEN, IN_PROGRESS} ∧ fleet_availability=AVAILABLE |
| Count | **176 / 520** WOs (249 open/in progress total) |
| Unique robots in union with expired-connected | **203 / 712** false-available (03) |
| Fixture | `WO-000380` RBT-0001 |
| Retain? | **Yes** (I5). |

### Safety cert / calibration / connectivity

| Metric | Count / 712 |
|---|---|
| EXPIRED | 38 |
| EXPIRED and not OFFLINE | **35** (`diagnostics.py`) |
| EXPIRING | 50 |
| Calibration OVERDUE | 45 |
| Calibration DUE | 102 |
| OFFLINE | 42 |
| INTERMITTENT | 73 |
| health MAINTENANCE | 67 |
| Retain? | **Yes** (I1, I2). |

### Duplicate telemetry

| | |
|---|---|
| Method | Extra occurrences of (robot_id, event_time, zone, battery_soc, speed_mps) |
| Count | **80 / 12,896 (0.62%)**; 12,816 unique keys |
| Example | `RBT-0194` 2026-08-12T07:24:00 |
| Drop? | **Yes, extras only** — see `specs/02_data_contracts.md`. Do not drop first observation. |

### Temporal skew (events)

| | |
|---|---|
| Method | event_time ≠ recorded_time |
| Count | **7,448 / 7,474** (03) |
| recorded_time before event_time | 2,132 |
| Event types | ORDER_RELEASED 1600, ORDER_ALLOCATED 1600, TASK_DISPATCHED 2500, TASK_STATUS 1774 |
| Sources | OMS 1600, WMS 1600, WES 2500, FLEET 1774 |
| Retain both timestamps? | **Yes** (I8). Do not rewrite recorded_time. |

### Site mismatch (task vs robot warehouse)

| | |
|---|---|
| Method | robots.warehouse_id ≠ tasks.warehouse_id for assigned_robot |
| Count | **8,247 / 8,732 (94.4%)** (03) |
| Operational meaning | UNKNOWN (possible generator artifact) |
| Retain? | **Yes** as Conflict SITE_MISMATCH. Do not move robots in CSV. |

### Plant / charging

| Metric | Count |
|---|---|
| Assets DOWN | 50 / 918 |
| Assets DEGRADED | 131 / 918 |
| Preferred charger is DOWN | **42** charging rows |
| charging_eligible=N | 43 / 712 |

### Vision

| Metric | Count |
|---|---|
| Observations | 214; all classification ROBOT |
| confidence < 0.7 | **73** |
| `DC-01-CAM-18` rows | **2** (including RBT-0001 conf 0.566) |

### Shadow

| Metric | Count |
|---|---|
| FINAL_v7 rows | 216; all order_id exist in orders |
| Reasons | manager_override 66, carrier_cutoff 59, inventory_risk 54, vip_customer 37 |
| Emails | 4 unstructured directives |
| Rewrite into WMS? | **Forbidden** |

### Shipments completeness

| Metric | Count |
|---|---|
| actual_departure empty | **1,933 / 3,500** |
| DELAYED | 586 |
| DEPARTED with both timestamps | 248 (03 on-time 64 / late 184) |

---

## 3. Quality vs “release blockers”

V2 treats **packaging** defects as blockers and **domain contradictions** as the system-under-study (`docs/07`). This profile agrees: keys/hashes/SQLite integrity PASS; semantic conflicts MUST remain.

---

## 4. Profiling method note

Prompt 06 helper computed PKs, orphans, SQLite parity, charger-DOWN join, vision CAM-18. Conflict rates use the same definitions as `warehouse_control.diagnostics.run()` and `discovery/03_PROBLEM_FRAME_AND_BASELINE.md`. Helper script is not part of the product.
