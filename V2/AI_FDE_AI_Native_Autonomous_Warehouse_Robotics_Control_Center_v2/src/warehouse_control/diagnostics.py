import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel):
    with (ROOT / rel).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run():
    robots = read("data/raw/robots.csv")
    aliases = read("data/raw/robot_aliases.csv")
    inv = read("data/raw/inventory_snapshot.csv")
    tasks = read("data/raw/tasks.csv")
    maint = read("data/raw/maintenance.csv")
    tele = read("data/telemetry/robot_telemetry.csv")
    orders = read("data/raw/orders.csv")
    shipments = read("data/raw/shipments.csv")

    alias_counts = Counter(a["alias"] for a in aliases)
    collisions = sum(1 for _, n in alias_counts.items() if n > 1)
    inv_conflicts = sum(
        1 for r in inv if len({r["wms_qty"], r["erp_qty"], r["vision_qty"]}) > 1
    )
    task_conflicts = sum(1 for r in tasks if r["wes_status"] != r["fleet_status"])
    maint_conflicts = sum(
        1
        for r in maint
        if r["cmms_status"] in {"OPEN", "IN_PROGRESS"}
        and r["fleet_availability"] == "AVAILABLE"
    )
    unsafe_available = sum(
        1
        for r in robots
        if r["safety_cert_status"] == "EXPIRED" and r["connectivity"] != "OFFLINE"
    )
    seen = set()
    dup = 0
    for r in tele:
        k = (r["robot_id"], r["event_time"], r["zone"], r["battery_soc"], r["speed_mps"])
        if k in seen:
            dup += 1
        seen.add(k)

    expired_cert = sum(1 for r in robots if r["safety_cert_status"] == "EXPIRED")
    open_cmms_robots = {
        r["robot_id"]
        for r in maint
        if r["cmms_status"] in {"OPEN", "IN_PROGRESS"}
    }
    oms_wms = sum(1 for r in orders if r["oms_status"] != r["wms_status"])
    delayed = sum(1 for r in shipments if r["tms_status"] == "DELAYED")

    return {
        "robots": len(robots),
        "alias_collisions": collisions,
        "inventory_truth_conflicts": inv_conflicts,
        "wes_fleet_task_conflicts": task_conflicts,
        "maintenance_availability_conflicts": maint_conflicts,
        "expired_safety_cert_but_connected": unsafe_available,
        "duplicate_telemetry_packets": dup,
        "identity_collisions_detail_count": collisions,
        "eligibility_ineligible_expired_cert": expired_cert,
        "eligibility_ineligible_open_cmms": len(open_cmms_robots),
        "inventory_uncertain_rows": inv_conflicts,
        "orders_oms_wms_status_conflicts": oms_wms,
        "cutoff_delayed_shipments": delayed,
        "abstain_preview_supported": True,
    }
