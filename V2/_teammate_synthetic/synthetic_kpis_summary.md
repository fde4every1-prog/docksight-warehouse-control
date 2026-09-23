# KPI summary

This summary is based only on the current files in the repository and does not assume any undocumented management numbers. Where a KPI cannot be computed from the repo's raw data, it is marked as not measurable.

## Computed KPI values

| KPI | Value | Basis |
|---|---:|---|
| order cycle time | 8.00 hours average | Difference between order created_at and shipment actual_departure for matched orders and shipments |
| on-time carrier departure | 62.20% | Shipments with actual_departure <= planned_departure, among shipments with actual departure timestamps |
| pick/pack exception rate | 64.10% | Pick/pack tasks where either WES status or fleet status is not in the terminal/active states |
| inventory accuracy | 0.21% exact match | Inventory rows where WMS qty = ERP qty = VISION qty |
| robot productive utilization | 0.88% | Telemetry rows with speed > 0.5 m/s and localization confidence >= 0.7 |
| robot deadlock rate | 0.20% | Tasks with WES or fleet status = BLOCKED |
| maintenance-induced downtime | 0.34% of maintenance records | Work orders with CMMS status OPEN/IN_PROGRESS while fleet availability is AVAILABLE |
| safety event rate | 133.99 per 1,000 tasks | 1170 safety events across 8732 tasks |
| false availability rate | 0.05% of robots | Robots with expired safety cert status but still connected |
| manual overrides per 1,000 tasks | 24.74 | 216 override records across 8732 tasks |
| human interventions per 1,000 robot tasks | 363.15 | Proxy using tasks with WES or fleet status BLOCKED/FAILED |

## Not directly measurable from the current repo data

These KPI candidates are not supported by the checked-in source files and therefore were not calculated as numeric values:

- charging_queue_time
- travel_distance_per_completed_task
- congestion_minutes
- recovery_time_after_control_system_outage
- cost_per_fulfilled_order

## Evidence used

- [data/raw/synthetic_orders_7000.csv](data/raw/synthetic_orders_7000.csv)
- [data/raw/synthetic_shipments_7000.csv](data/raw/synthetic_shipments_7000.csv)
- [data/raw/tasks.csv](data/raw/tasks.csv)
- [data/raw/inventory_snapshot.csv](data/raw/inventory_snapshot.csv)
- [data/telemetry/robot_telemetry.csv](data/telemetry/robot_telemetry.csv)
- [data/raw/maintenance.csv](data/raw/maintenance.csv)
- [data/raw/safety_events.csv](data/raw/safety_events.csv)
- [data/raw/robots.csv](data/raw/robots.csv)
- [data/shadow/wave_priority_FINAL_v7.csv](data/shadow/wave_priority_FINAL_v7.csv)

## Notes

- The repo intentionally contains multiple local truths and shadow/override sources, so the KPI calculations reflect the current dataset exactly as recorded rather than a normalized canonical truth.
- This is a baseline measurement for current operations, not a target or forecast.
