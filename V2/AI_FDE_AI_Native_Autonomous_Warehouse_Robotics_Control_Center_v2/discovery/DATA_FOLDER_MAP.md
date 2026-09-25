# Data folder map — headers, joins, walkthroughs

Counts: `data/manifest.json`. Join only on the shared kernel: `warehouse_id`, `robot_id`, `order_id`, `task_id`, `sku`+`location`.

Companion canvas: open **Data folder mind map** beside chat.

---

## How files connect (mind map)

```text
warehouses.csv ──warehouse_id──► orders.csv ──order_id──► tasks.csv
                                      │                      │
                                      └──order_id──► shipments.csv
                                                         │
tasks.assigned_robot ──robot_id──► robots.csv
tasks.source_zone / dest_zone ──zone_id──► zones.csv
orders/tasks/robots ──entity_id──► events.jsonl

robots.csv ──robot_id──► robot_aliases.csv
                    ├──► maintenance.csv
                    ├──► charging_state.csv ──preferred_charger──► control_assets.asset_id
                    └──► robot_telemetry.csv

skus.csv ──sku──► inventory_snapshot.csv  (grain: warehouse_id + sku + location)

UNTRUSTED (do not join as truth):
  ops_emails.txt
  wave_priority_FINAL_v7.csv  (order_id only as overlay)
  vision_observations.csv     (observed_entity is evidence, not robot_id authority)
```

`robots.vendor` is a **name** (RoboFlow, MoveIQ…). `vendors.csv` uses `vendor_id` (RV-01…). Do not inner-join those two without a name map.

---

## Headers

| File | Headers |
|---|---|
| `reference/warehouses.csv` | warehouse_id, region, country, warehouse_type, timezone, wms_vendor, fleet_vendor, go_live_year |
| `reference/skus.csv` | sku, description, uom, temperature_class, lot_controlled, serial_controlled, hazmat |
| `reference/vendors.csv` | vendor_id, name, type, support_sla_hours, remote_access |
| `raw/orders.csv` | order_id, warehouse_id, priority, created_at, carrier_cutoff, **oms_status**, **wms_status**, customer_region, service_level |
| `raw/tasks.csv` | task_id, order_id, warehouse_id, task_type, assigned_robot, **wes_status**, **fleet_status**, source_zone, dest_zone, created_at |
| `raw/shipments.csv` | shipment_id, order_id, warehouse_id, tms_status, carrier, planned_departure, actual_departure |
| `raw/robots.csv` | robot_id, warehouse_id, robot_type, vendor, fleet_id, firmware, battery_soc, battery_soh, health_status, payload_kg, safety_cert_status, calibration_status, connectivity |
| `raw/robot_aliases.csv` | robot_id, source, alias |
| `raw/maintenance.csv` | work_order_id, robot_id, warehouse_id, cmms_status, fleet_availability, issue, opened_at, safety_release_recorded |
| `raw/inventory_snapshot.csv` | warehouse_id, sku, location, wms_qty, erp_qty, vision_qty, reserved_qty, inventory_status, last_cycle_count_days |
| `raw/zones.csv` | warehouse_id, zone_id, zone_type, robot_access, human_density_profile, map_version, physical_change_pending |
| `raw/charging_state.csv` | robot_id, warehouse_id, soc_pct, soh_pct, preferred_charger, charging_eligible, next_pm_days |
| `raw/control_assets.csv` | asset_id, warehouse_id, asset_type, state, maintenance_state, controller_version |
| `raw/safety_events.csv` | warehouse_id, event_id, event_time, event_type, zone, severity, resolved, source |
| `raw/labor_capacity.csv` | warehouse_id, shift, planned_workers, actual_workers, certified_robot_operators, pack_staff, exception_handlers |
| `raw/events.jsonl` | event_id, source, entity_type, entity_id, event_type, event_time, recorded_time, payload_json |
| `telemetry/robot_telemetry.csv` | robot_id, warehouse_id, event_time, ingest_time, zone, battery_soc, speed_mps, localization_confidence, telemetry_quality |
| `telemetry/vision_observations.csv` | warehouse_id, camera_id, observed_entity, observed_zone, event_time, confidence, classification |
| `shadow/wave_priority_FINAL_v7.csv` | warehouse_id, order_id, manual_priority, reason |
| `shadow/ops_emails.txt` | unstructured text |

---

## SKU example (inventory is bad) — `SKU-01146`

1. `skus.csv` — CASE, AMBIENT, serial_controlled=Y.  
2. `inventory_snapshot.csv` — `DC-01` `DC-01-Z03-B017` **205 / 205 / 202**, reserved 16, AVAILABLE.  
3. `zones.csv` — `DC-01-Z03` STAGING, access YES, **physical_change_pending=YES**.  
4. `ops_emails.txt` — do not trust CAM-18.

**Why bad:** WMS and ERP agree at 205; vision is 202. That is Uncertainty (I3). Do not emit one available qty. Do not pick as known.

---

## Order example (fulfillment is bad) — `ORD-000004`

1. `orders.csv` — DC-16, CRITICAL, SAME_DAY, OMS **STAGED**, WMS **EXCEPTION**.  
2. `shipments.csv` `SHP-000004` — TMS **DELAYED**, Carrier-A, **empty actual_departure**.  
3. `tasks.csv` `TSK-000004-1` — MOVE, assigned `RBT-0644`, WES **EXECUTING**, fleet **FAILED**.  
4. `robots.csv` `RBT-0644` — warehouse **DC-17** (not DC-16), cal **OVERDUE**.  
5. `maintenance.csv` `WO-000010` — IN_PROGRESS.  
6. `ops_emails.txt` — Carrier-A −35 min; “supervisor approved” is not Approval.

**Why bad:** not on-time, not complete, assignee INELIGIBLE (site + overdue + open WO). Cutoff must not force a new fleet assign.

---

## Happy path start to finish — **injected slice `ORD-009999`**

Additive rows (do not rewrite brownfield). Recipe: `discovery/HAPPY_PATH_INJECT.md`.

There is still **no** green path in the original 3500 orders. The demo slice is extra.

### Synthetic slice to add (new IDs, same headers, do not rewrite existing rows)

| Step | Build | Must be true |
|---|---|---|
| 1 | `ORD-HAPPY-001` | oms_status = wms_status at each stage |
| 2 | `SKU-HAPPY-001` @ `DC-01-Z02-B001` | wms_qty = erp_qty = vision_qty, AVAILABLE |
| 3 | `TSK-HAPPY-1` PICK | wes_status = fleet_status; dest `robot_access=YES` |
| 4 | `RBT-HAPPY-01` | same `warehouse_id`; VALID cert; VALID cal; ONLINE; no OPEN/IN_PROGRESS WO |
| 5 | aliases | one alias per source; no collision across robots |
| 6 | `SHP-HAPPY-001` | not DELAYED; `actual_departure` filled when DEPARTED |
| 7 | events.jsonl | event_time ≈ recorded_time |
| 8 | shadow | none, or unused |

Keep `ORD-000004` and `SKU-01146` as the named FAIL baseline for negative tests.
