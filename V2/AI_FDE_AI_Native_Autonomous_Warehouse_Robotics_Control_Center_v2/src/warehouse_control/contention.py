"""Observe-only snapshot for the multi-robot contention question.

Not a physical mutex. Not a reservation. GET evidence only.
"""

from warehouse_control.allocator.filter_score import allocate_for_task
from warehouse_control.decision.engine import decide
from warehouse_control.eligibility.policy import evaluate_eligibility
from warehouse_control.injects.replay import replay_inject
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.repository import csv_rows

LOCATION_TASK_ID = "TSK-000019-2"
LOCATION_ZONE_ID = "DC-01-Z05"
PROBE_ROBOT_ID = "RBT-0012"
DOCK_TASK_ID = "TSK-000004-1"
DOCK_INJECT_ID = "inject_03"
INV_WAREHOUSE = "DC-01"
INV_SKU = "SKU-01146"
INV_LOCATION = "DC-01-Z03-B017"


def zone_for_task(task: dict | None) -> dict:
    if not task:
        return {}
    dest = task.get("dest_zone") or task.get("target_zone")
    if not dest:
        return {}
    for row in csv_rows("zones.csv"):
        if row.get("zone_id") == dest:
            return dict(row)
    return {"zone_id": dest}


def _claimants(zone_id: str, limit: int = 6) -> list[dict]:
    out = []
    for row in csv_rows("tasks.csv"):
        if row.get("dest_zone") != zone_id:
            continue
        out.append(
            {
                "task_id": row.get("task_id"),
                "order_id": row.get("order_id"),
                "warehouse_id": row.get("warehouse_id"),
                "assigned_robot": row.get("assigned_robot"),
                "wes_status": row.get("wes_status"),
                "fleet_status": row.get("fleet_status"),
                "source_zone": row.get("source_zone"),
                "dest_zone": row.get("dest_zone"),
            }
        )
        if len(out) >= limit:
            break
    return out


def _inventory_row() -> dict:
    for row in csv_rows("inventory_snapshot.csv"):
        if (
            row.get("warehouse_id") == INV_WAREHOUSE
            and row.get("sku") == INV_SKU
            and row.get("location") == INV_LOCATION
        ):
            return row
    return {}


def _robot(robot_id: str) -> dict:
    return next(r for r in csv_rows("robots.csv") if r.get("robot_id") == robot_id)


def _task(task_id: str) -> dict:
    return next(t for t in csv_rows("tasks.csv") if t.get("task_id") == task_id)


def _maint(robot_id: str) -> list[dict]:
    rows = []
    for row in csv_rows("maintenance.csv"):
        if row.get("robot_id") == robot_id:
            item = dict(row)
            item["wo_id"] = row.get("work_order_id")
            rows.append(item)
    return rows


def snapshot() -> dict:
    """Bundle location / dock / inventory contention. Execution never applied."""
    loc_task = _task(LOCATION_TASK_ID)
    zone = zone_for_task(loc_task)
    probe_robot = _robot(PROBE_ROBOT_ID)
    probe = evaluate_eligibility(
        probe_robot,
        loc_task,
        context={"maintenance_rows": _maint(PROBE_ROBOT_ID), "zone": zone},
    )
    alloc = allocate_for_task(LOCATION_TASK_ID)
    g4 = [
        row
        for row in (alloc.get("eligibility_summary") or {}).get("ineligible") or []
        if "G4" in (row.get("gates_failed") or [])
    ]
    dock = replay_inject(DOCK_INJECT_ID, DOCK_TASK_ID)
    inv_row = _inventory_row()
    inv = observe_inventory(inv_row) if inv_row else {"error": "not_found"}
    release = decide({"intent": "release_zone", "cutoff_pressure": True})
    pick = decide({"intent": "allocate_as_known", "inventory": {"uncertain": True}})
    return {
        "question": (
            "What happens when multiple robots need the same location, "
            "resource, dock, or inventory at the same time?"
        ),
        "answer": (
            "This is not a physical store. We do not lock the aisle, dock, or bin. "
            "UC-1 refuses or abstains. Mutex stays with WES/fleet/plant."
        ),
        "physical_control": "disabled",
        "assign_supported": False,
        "reservation_supported": False,
        "location": {
            "zone": {
                "zone_id": zone.get("zone_id"),
                "warehouse_id": zone.get("warehouse_id"),
                "zone_type": zone.get("zone_type"),
                "robot_access": zone.get("robot_access"),
            },
            "task_id": LOCATION_TASK_ID,
            "claimants": _claimants(LOCATION_ZONE_ID),
            "probe_robot_id": PROBE_ROBOT_ID,
            "probe": {
                "eligibility": probe.get("eligibility"),
                "gates_failed": probe.get("gates_failed"),
            },
            "allocation": {
                "chosen_robot_id": alloc.get("chosen_robot_id"),
                "decision_hint": alloc.get("decision_hint"),
                "g4_ineligible_count": len(g4),
                "physical_control": alloc.get("physical_control"),
                "execution_applied": alloc.get("execution_applied"),
            },
        },
        "dock": {
            "inject_id": DOCK_INJECT_ID,
            "task_id": DOCK_TASK_ID,
            "title": dock.get("title"),
            "chosen_robot_id": dock.get("chosen_robot_id"),
            "decision_hint": dock.get("decision_hint"),
            "outbound_blocked": (dock.get("allocation") or {}).get("outbound_blocked"),
            "safety_bypass": (dock.get("safety_bypass") or {}).get("decision"),
            "execution_applied": dock.get("execution_applied"),
            "physical_control": dock.get("physical_control"),
            "csv_rewritten": False,
        },
        "inventory": inv,
        "blocked": {
            "assign": "blocked",
            "pick_as_known": pick.get("decision"),
            "release_zone": release.get("decision"),
        },
    }
