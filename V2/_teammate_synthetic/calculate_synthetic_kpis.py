#!/usr/bin/env python3
"""Compute baseline KPI values from the repo's current warehouse data.

This script intentionally reports only metrics that are directly supported by the
CSV files in this repo. For metrics that have no reliable source fields (for
example cost, queue time, route distance, or outage recovery), it reports
"not_measurable" instead of guessing.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = SCRIPT_DIR / "synthetic_kpis_summary.md"


def read_csv(path: str):
    candidates = [ROOT / path, SCRIPT_DIR / path]
    for candidate in candidates:
        if candidate.exists():
            with candidate.open(newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
    raise FileNotFoundError(f"Could not locate data file: {path}")


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def main():
    orders = read_csv("synthetic_orders_7000.csv")
    tasks = read_csv("data/raw/tasks.csv")
    shipments = read_csv("synthetic_shipments_7000.csv")
    inventory = read_csv("data/raw/inventory_snapshot.csv")
    robots = read_csv("data/raw/robots.csv")
    telemetry = read_csv("data/telemetry/robot_telemetry.csv")
    maintenance = read_csv("data/raw/maintenance.csv")
    safety_events = read_csv("data/raw/safety_events.csv")
    shadow_priority = read_csv("data/shadow/wave_priority_FINAL_v7.csv")

    # Order cycle time: created_at -> actual_departure from the shipment record.
    cycle_hours = []
    order_by_id = {o["order_id"]: o for o in orders if o.get("order_id")}
    for shipment in shipments:
        order_id = shipment.get("order_id")
        created_at = order_by_id.get(order_id, {}).get("created_at")
        actual_departure = shipment.get("actual_departure")
        if created_at and actual_departure:
            try:
                created = datetime.fromisoformat(created_at)
                actual = datetime.fromisoformat(actual_departure)
                cycle_hours.append((actual - created).total_seconds() / 3600)
            except ValueError:
                pass

    # On-time carrier departures.
    shipped_with_departure = 0
    on_time_departures = 0
    for shipment in shipments:
        actual = shipment.get("actual_departure")
        planned = shipment.get("planned_departure")
        if not actual or not planned:
            continue
        shipped_with_departure += 1
        try:
            if datetime.fromisoformat(actual) <= datetime.fromisoformat(planned):
                on_time_departures += 1
        except ValueError:
            pass

    # Pick/pack exception rate.
    pick_pack_types = {"PICK", "PACK", "PICK_FEED", "PACK_FEED"}
    pick_pack_tasks = [t for t in tasks if t.get("task_type") in pick_pack_types]
    terminal_states = {"COMPLETE", "EXECUTING", "ASSIGNED"}
    pick_pack_exceptions = [
        t
        for t in pick_pack_tasks
        if t.get("wes_status") not in terminal_states or t.get("fleet_status") not in terminal_states
    ]

    # Inventory accuracy exact-match rate.
    exact_inventory_matches = sum(
        1
        for row in inventory
        if row.get("wms_qty") == row.get("erp_qty") == row.get("vision_qty")
    )

    # Productive utilization = telemetry rows with speed above 0.5 and confidence >= 0.7.
    productive_rows = 0
    for row in telemetry:
        speed = safe_float(row.get("speed_mps"))
        confidence = safe_float(row.get("localization_confidence"))
        if speed > 0.5 and confidence >= 0.7:
            productive_rows += 1

    # Deadlock rate = tasks with BLOCKED status (either WES or fleet)
    deadlocked_tasks = sum(
        1
        for t in tasks
        if t.get("wes_status") == "BLOCKED" or t.get("fleet_status") == "BLOCKED"
    )

    # Maintenance-induced downtime = CMMS indicates open/in progress while fleet says AVAILABLE.
    maintenance_false_availability = sum(
        1
        for m in maintenance
        if m.get("cmms_status") in {"OPEN", "IN_PROGRESS"} and m.get("fleet_availability") == "AVAILABLE"
    )

    # Safety event rate per 1,000 tasks.
    safety_event_rate_per_1000 = (len(safety_events) / len(tasks)) * 1000 if tasks else 0.0

    # False availability = expired safety cert but robot still connected.
    false_availability_count = sum(
        1
        for r in robots
        if r.get("safety_cert_status") == "EXPIRED" and r.get("connectivity") != "OFFLINE"
    )
    false_availability_rate = pct(false_availability_count, len(robots))

    # Manual override rate per 1,000 tasks.
    manual_override_rate_per_1000 = (len(shadow_priority) / len(tasks)) * 1000 if tasks else 0.0

    # Human interventions per 1,000 tasks (proxy using blocked/failed task states).
    intervention_proxy_count = sum(
        1
        for t in tasks
        if t.get("wes_status") in {"BLOCKED", "FAILED"} or t.get("fleet_status") in {"BLOCKED", "FAILED"}
    )
    interventions_per_1000 = (intervention_proxy_count / len(tasks)) * 1000 if tasks else 0.0

    # KPI output payload.
    metrics = {
        "order_cycle_hours_avg": sum(cycle_hours) / len(cycle_hours) if cycle_hours else 0.0,
        "on_time_carrier_departure_rate": pct(on_time_departures, shipped_with_departure)*100,
        "pick_pack_exception_rate": pct(len(pick_pack_exceptions), len(pick_pack_tasks))*100,
        "inventory_accuracy_exact_match_rate": pct(exact_inventory_matches, len(inventory)),
        "robot_productive_utilization_rate": pct(productive_rows, len(telemetry)),
        "robot_deadlock_rate": pct(deadlocked_tasks, len(tasks)),
        "maintenance_induced_downtime_rate": pct(maintenance_false_availability, len(maintenance)),
        "safety_event_rate_per_1000_tasks": safety_event_rate_per_1000,
        "false_availability_rate": false_availability_rate,
        "manual_overrides_per_1000_tasks": manual_override_rate_per_1000,
        "human_interventions_per_1000_tasks_proxy": interventions_per_1000,
        "maintenance_false_availability_count": maintenance_false_availability,
        "pick_pack_tasks": len(pick_pack_tasks),
        "pick_pack_exception_tasks": len(pick_pack_exceptions),
        "inventory_rows": len(inventory),
        "telemetry_rows": len(telemetry),
        "tasks_total": len(tasks),
        "shipments_with_actual_departure": shipped_with_departure,
        "orders_total": len(orders),
        "robots_total": len(robots),
        "maintenance_records_total": len(maintenance),
        "safety_events_total": len(safety_events),
        "shadow_override_records_total": len(shadow_priority),
        "not_measurable": {
            "charging_queue_time": "Not available in current schema",
            "travel_distance_per_completed_task": "No distance or route table in source files",
            "congestion_minutes": "No congestion-duration field in source files",
            "recovery_time_after_control_system_outage": "No outage start/end records in source files",
            "cost_per_fulfilled_order": "No cost or labor-cost model in source files",
        },
    }

    return metrics


def render_markdown(metrics: dict) -> str:
    metric_rows = [
        (
            "order cycle time",
            metrics["order_cycle_hours_avg"],
            "Difference between order created_at and shipment actual_departure for matched orders and shipments",
            "hours average",
        ),
        (
            "on-time carrier departure",
            metrics["on_time_carrier_departure_rate"],
            "Shipments with actual_departure <= planned_departure, among shipments with actual departure timestamps",
            "%",
        ),
        (
            "pick/pack exception rate",
            metrics["pick_pack_exception_rate"],
            "Pick/pack tasks where either WES status or fleet status is not in the terminal/active states",
            "%",
        ),
        (
            "inventory accuracy",
            metrics["inventory_accuracy_exact_match_rate"],
            "Inventory rows where WMS qty = ERP qty = VISION qty",
            "exact match",
        ),
        (
            "robot productive utilization",
            metrics["robot_productive_utilization_rate"],
            "Telemetry rows with speed > 0.5 m/s and localization confidence >= 0.7",
            "%",
        ),
        (
            "robot deadlock rate",
            metrics["robot_deadlock_rate"],
            "Tasks with WES or fleet status = BLOCKED",
            "%",
        ),
        (
            "maintenance-induced downtime",
            metrics["maintenance_induced_downtime_rate"],
            "Work orders with CMMS status OPEN/IN_PROGRESS while fleet availability is AVAILABLE",
            "% of maintenance records",
        ),
        (
            "safety event rate",
            metrics["safety_event_rate_per_1000_tasks"],
            f"{metrics['safety_events_total']} safety events across {metrics['tasks_total']} tasks",
            "per 1,000 tasks",
        ),
        (
            "false availability rate",
            metrics["false_availability_rate"],
            "Robots with expired safety cert status but still connected",
            "% of robots",
        ),
        (
            "manual overrides per 1,000 tasks",
            metrics["manual_overrides_per_1000_tasks"],
            f"{metrics['shadow_override_records_total']} override records across {metrics['tasks_total']} tasks",
            "",
        ),
        (
            "human interventions per 1,000 robot tasks",
            metrics["human_interventions_per_1000_tasks_proxy"],
            "Proxy using tasks with WES or fleet status BLOCKED/FAILED",
            "",
        ),
    ]

    lines = [
        "# KPI summary",
        "",
        "This summary is based only on the current files in the repository and does not assume any undocumented management numbers. Where a KPI cannot be computed from the repo's raw data, it is marked as not measurable.",
        "",
        "## Computed KPI values",
        "",
        "| KPI | Value | Basis |",
        "|---|---:|---|",
    ]

    for name, value, basis, suffix in metric_rows:
        if suffix:
            value_display = f"{value:.2f} {suffix}" if suffix in {"hours average", "%", "exact match", "per 1,000 tasks", "% of maintenance records", "% of robots"} else f"{value:.2f} {suffix}"
            if "per 1,000 tasks" in suffix:
                value_display = f"{value:.2f} {suffix}"
            if suffix == "exact match":
                value_display = f"{value:.2f}% exact match"
            elif suffix == "%":
                value_display = f"{value:.2f}%"
            elif suffix == "hours average":
                value_display = f"{value:.2f} hours average"
            elif suffix == "% of maintenance records":
                value_display = f"{value:.2f}% of maintenance records"
            elif suffix == "% of robots":
                value_display = f"{value:.2f}% of robots"
            elif suffix == "per 1,000 tasks":
                value_display = f"{value:.2f} per 1,000 tasks"
        else:
            value_display = f"{value:.2f}"
        lines.append(f"| {name} | {value_display} | {basis} |")

    lines.extend([
        "",
        "## Not directly measurable from the current repo data",
        "",
        "These KPI candidates are not supported by the checked-in source files and therefore were not calculated as numeric values:",
        "",
    ])
    for name in metrics["not_measurable"]:
        lines.append(f"- {name}")

    lines.extend([
        "",
        "## Evidence used",
        "",
        "- [data/raw/synthetic_orders_7000.csv](data/raw/synthetic_orders_7000.csv)",
        "- [data/raw/synthetic_shipments_7000.csv](data/raw/synthetic_shipments_7000.csv)",
        "- [data/raw/tasks.csv](data/raw/tasks.csv)",
        "- [data/raw/inventory_snapshot.csv](data/raw/inventory_snapshot.csv)",
        "- [data/telemetry/robot_telemetry.csv](data/telemetry/robot_telemetry.csv)",
        "- [data/raw/maintenance.csv](data/raw/maintenance.csv)",
        "- [data/raw/safety_events.csv](data/raw/safety_events.csv)",
        "- [data/raw/robots.csv](data/raw/robots.csv)",
        "- [data/shadow/wave_priority_FINAL_v7.csv](data/shadow/wave_priority_FINAL_v7.csv)",
        "",
        "## Notes",
        "",
        "- The repo intentionally contains multiple local truths and shadow/override sources, so the KPI calculations reflect the current dataset exactly as recorded rather than a normalized canonical truth.",
        "- This is a baseline measurement for current operations, not a target or forecast.",
    ])

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    metrics = main()
    output = render_markdown(metrics)

    OUTPUT_PATH.write_text(output, encoding="utf-8")

    print("KPI summary from current repo data")
    print("=" * 50)
    print(output)
    print(f"Summary written to {OUTPUT_PATH}")
