# Happy-path inject — ORD-009999 (additive, do not delete brownfield rows)

**Purpose:** One end-to-end **green** slice for the audience / Replit UI.  
**Does not** rewrite `ORD-000004` or `SKU-01146`.  
**Does not** add a new robot (keeps Prompt 15 denominator 712). Reuses **`RBT-0012`**.

Physical control stays disabled. Preview/observe only.

---

## Bare minimum the UI must show (pass)

| Screen | Lookup | Must show |
|---|---|---|
| Order | `ORD-009999` | OMS **SHIPPED** and WMS **SHIPPED** (same). Complete **yes**. |
| Shipment | `SHP-009999` | TMS **DEPARTED**, Carrier-B, **actual_departure filled**. Not DELAYED. |
| Task / fleet assign | `TSK-009999-1` | WES **COMPLETE** and fleet **COMPLETE**. Assigned **`RBT-0012`**. Same DC-01. |
| Robot | `RBT-0012` | DC-01, VALID cert, VALID cal, ONLINE, HEALTHY. No OPEN/IN_PROGRESS WO. |
| Inventory / pick | `SKU-09999` @ `DC-01-Z02-B099` | WMS=ERP=vision **40**. `uncertain=false`. AVAILABLE. |
| Zone | dest `DC-01-Z02` | `robot_access=YES` (already in `zones.csv`). |
| Identity | aliases of `RBT-0012` | `BOT0012` / `DC-01-PALLET_MOVER-012` / `ASSET-100012` — one robot, no collision. |

**Must still fail** on the old IDs: `ORD-000004` not on-time; `SKU-01146` 205/205/202 uncertain.

---

## File 1 — `data/reference/skus.csv`

Add this line:

```text
SKU-09999,Happy-path demo case,CASE,AMBIENT,N,N,N
```

---

## File 2 — `data/raw/inventory_snapshot.csv`

Add this line:

```text
DC-01,SKU-09999,DC-01-Z02-B099,40,40,40,0,AVAILABLE,1
```

---

## File 3 — `data/raw/orders.csv`

Add this line:

```text
ORD-009999,DC-01,STANDARD,2026-09-18T08:00:00,2026-09-18T16:00:00,SHIPPED,SHIPPED,NA,STANDARD
```

---

## File 4 — `data/raw/shipments.csv`

Add this line:

```text
SHP-009999,ORD-009999,DC-01,DEPARTED,Carrier-B,2026-09-18T16:00:00,2026-09-18T15:48:00
```

---

## File 5 — `data/raw/tasks.csv`

Add this line:

```text
TSK-009999-1,ORD-009999,DC-01,PICK,RBT-0012,COMPLETE,COMPLETE,DC-01-Z02,DC-01-Z02,2026-09-18T09:00:00
```

---

## File 6 — `data/raw/events.jsonl` (optional timeline)

Add these lines (one JSON object per line):

```text
{"event_id": "EVT-HAPPY-001", "source": "OMS", "entity_type": "ORDER", "entity_id": "ORD-009999", "event_type": "ORDER_RELEASED", "event_time": "2026-09-18T08:00:00", "recorded_time": "2026-09-18T08:00:00", "payload_json": "{\"priority\":\"STANDARD\"}"}
{"event_id": "EVT-HAPPY-002", "source": "WES", "entity_type": "TASK", "entity_id": "TSK-009999-1", "event_type": "TASK_DISPATCHED", "event_time": "2026-09-18T09:00:00", "recorded_time": "2026-09-18T09:00:00", "payload_json": "{\"robot\":\"RBT-0012\"}"}
{"event_id": "EVT-HAPPY-003", "source": "WES", "entity_type": "TASK", "entity_id": "TSK-009999-1", "event_type": "TASK_STATUS", "event_time": "2026-09-18T14:00:00", "recorded_time": "2026-09-18T14:00:00", "payload_json": "{\"status\":\"COMPLETE\"}"}
{"event_id": "EVT-HAPPY-004", "source": "FLEET", "entity_type": "TASK", "entity_id": "TSK-009999-1", "event_type": "TASK_STATUS", "event_time": "2026-09-18T14:00:00", "recorded_time": "2026-09-18T14:00:00", "payload_json": "{\"status\":\"COMPLETE\"}"}
{"event_id": "EVT-HAPPY-005", "source": "OMS", "entity_type": "ORDER", "entity_id": "ORD-009999", "event_type": "ORDER_SHIPPED", "event_time": "2026-09-18T15:48:00", "recorded_time": "2026-09-18T15:48:00", "payload_json": "{\"tms\":\"DEPARTED\"}"}
```

---

## Do **not** add rows to

| File | Why |
|---|---|
| `robots.csv` | Reuse `RBT-0012` so estate KPI denominator stays 712 |
| `maintenance.csv` | `WO-000156` is **PLANNED** only — not a G2 fail |
| `robot_aliases.csv` | Already unique for `RBT-0012` |
| `zones.csv` | `DC-01-Z02` already PICK / YES |
| `ops_emails.txt` | Must stay so `ORD-000004` still fails |
| `wave_priority_FINAL_v7.csv` | No override for this order |

---

## Already in the repo (no new line)

`robots.csv` `RBT-0012`:

```text
RBT-0012,DC-01,PALLET_MOVER,RoboFlow,DC-01-F2,4.5.4,77,94,HEALTHY,1500,VALID,VALID,ONLINE
```

---

## UI click script (audience)

1. Open order **ORD-009999** → both statuses SHIPPED; complete **yes**.  
2. Open shipment → DEPARTED, actual 15:48.  
3. Open task **TSK-009999-1** → both COMPLETE; robot **RBT-0012**.  
4. Open robot **RBT-0012** → not G1/G2/I2.  
5. Open inventory **SKU-09999** / **DC-01-Z02-B099** → 40/40/40, not uncertain.  
6. Contrast: **ORD-000004** and **SKU-01146** still red.

If the UI copies Repo 2 `assess_cutoff` (global email text), it may still flag `CUTOFF_STALE` on every order. For the demo, treat **TMS DEPARTED + not DELAYED** as the happy shipment signal. Prefer applying stale-SLA only when **this** order’s carrier is Carrier-A.

Assign/dispatch must still be preview-only (`applied=false`).
