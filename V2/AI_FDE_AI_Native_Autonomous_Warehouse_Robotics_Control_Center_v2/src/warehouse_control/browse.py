"""Featured order browse. Observe-only. Orders join to robots via tasks, not to SKUs."""

from warehouse_control.eligibility.policy import evaluate_eligibility
from warehouse_control.fulfillment.cutoff import assess_cutoff
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.repository import csv_rows
from warehouse_control.tasks.reconcile import reconcile_order, reconcile_task

# Curated for v1. Do not dump all 3,500 orders into a <select>.
FEATURED_ORDERS = [
    {
        "order_id": "ORD-009999",
        "label": "ORD-009999 — agreed complete (green)",
        "why": "Happy path. OMS=WMS SHIPPED, tasks COMPLETE both sides.",
    },
    {
        "order_id": "ORD-000004",
        "label": "ORD-000004 — cutoff / DELAYED",
        "why": "Not on-time. TMS DELAYED. Do not release a zone.",
    },
    {
        "order_id": "ORD-000968",
        "label": "ORD-000968 — looks shipped, task still running",
        "why": "OMS SHIPPED is not E2E complete.",
    },
    {
        "order_id": "ORD-000001",
        "label": "ORD-000001 — picking, wrong-site robot on a task",
        "why": "assigned_robot is not Eligibility.",
    },
    {
        "order_id": "ORD-000072",
        "label": "ORD-000072 — in progress, WES and fleet agree on one task",
        "why": "Dual EXECUTING is agreement, not a split. Order still not complete.",
    },
    {
        "order_id": "ORD-000019",
        "label": "ORD-000019 — task into RESTRICTED zone",
        "why": "Dest DC-01-Z05. G4 refuse path.",
    },
]

# SKUs are warehouse+bin, not order lines. There is no order_id on inventory_snapshot.
FEATURED_SKUS = [
    {
        "sku": "SKU-09999",
        "location": "DC-01-Z02-B099",
        "warehouse_id": "DC-01",
        "label": "SKU-09999 @ DC-01-Z02-B099 — 40/40/40 (green)",
    },
    {
        "sku": "SKU-01146",
        "location": "DC-01-Z03-B017",
        "warehouse_id": "DC-01",
        "label": "SKU-01146 @ DC-01-Z03-B017 — 205/205/202 (uncertain)",
    },
]


def featured_catalog() -> dict:
    return {
        "hint": (
            "After an order, list robots next. Tasks carry assigned_robot. "
            "There is no SKU on the order file — SKUs are a warehouse bin check."
        ),
        "list_next": "robot_id",
        "sku_join": "none — inventory_snapshot has warehouse_id + sku + location only",
        "orders": FEATURED_ORDERS,
        "skus": FEATURED_SKUS,
        "physical_control": "disabled",
    }


def _order_row(order_id: str) -> dict | None:
    return next((o for o in csv_rows("orders.csv") if o.get("order_id") == order_id), None)


def _shipment(order_id: str) -> dict | None:
    return next((s for s in csv_rows("shipments.csv") if s.get("order_id") == order_id), None)


def _robot_row(robot_id: str) -> dict | None:
    return next((r for r in csv_rows("robots.csv") if r.get("robot_id") == robot_id), None)


def _maint(robot_id: str) -> list[dict]:
    rows = []
    for row in csv_rows("maintenance.csv"):
        if row.get("robot_id") == robot_id:
            item = dict(row)
            item["wo_id"] = row.get("work_order_id")
            rows.append(item)
    return rows


def _inv(warehouse_id: str, sku: str, location: str) -> dict | None:
    for row in csv_rows("inventory_snapshot.csv"):
        if (
            row.get("warehouse_id") == warehouse_id
            and row.get("sku") == sku
            and row.get("location") == location
        ):
            return row
    return None


def order_browse(order_id: str) -> dict:
    order = _order_row(order_id)
    if order is None:
        return {"error": "not_found", "order_id": order_id}

    tasks = [t for t in csv_rows("tasks.csv") if t.get("order_id") == order_id]
    robots_by_id: dict[str, dict] = {}
    for task in tasks:
        rid = task.get("assigned_robot") or ""
        if not rid:
            continue
        rec = reconcile_task(task)
        if rid not in robots_by_id:
            rob = _robot_row(rid) or {}
            robots_by_id[rid] = {
                "robot_id": rid,
                "robot_warehouse_id": rob.get("warehouse_id"),
                "safety_cert_status": rob.get("safety_cert_status"),
                "connectivity": rob.get("connectivity"),
                "tasks": [],
            }
        robots_by_id[rid]["tasks"].append(
            {
                "task_id": task.get("task_id"),
                "task_type": task.get("task_type"),
                "warehouse_id": task.get("warehouse_id"),
                "dest_zone": task.get("dest_zone"),
                "wes_status": task.get("wes_status"),
                "fleet_status": task.get("fleet_status"),
                "conflict": rec.get("conflict"),
            }
        )
    robots = list(robots_by_id.values())

    warehouse_id = order.get("warehouse_id")
    sku_options = [s for s in FEATURED_SKUS if s.get("warehouse_id") == warehouse_id]
    cutoff = assess_cutoff(order_id)
    rec = reconcile_order(order_id, tasks)
    return {
        "order": order,
        "shipment": _shipment(order_id) or {},
        "cutoff": cutoff,
        "reconcile": rec,
        "tasks": [
            {
                "task_id": t.get("task_id"),
                "assigned_robot": t.get("assigned_robot"),
                "wes_status": t.get("wes_status"),
                "fleet_status": t.get("fleet_status"),
                "dest_zone": t.get("dest_zone"),
                "task_type": t.get("task_type"),
            }
            for t in tasks
        ],
        "robots": robots,
        "sku_options": sku_options,
        "list_next": "robot_id",
        "sku_note": (
            "SKUs are not on the order. These are demo bins at this warehouse only."
            if sku_options
            else "No demo SKU for this warehouse. Use the robot list (joined via tasks)."
        ),
        "physical_control": "disabled",
        "assign_supported": False,
    }


def robot_on_order(order_id: str, robot_id: str) -> dict:
    browse = order_browse(order_id)
    if browse.get("error"):
        return browse
    task = next(
        (t for t in csv_rows("tasks.csv") if t.get("order_id") == order_id and t.get("assigned_robot") == robot_id),
        None,
    )
    if task is None:
        task = next((t for t in csv_rows("tasks.csv") if t.get("order_id") == order_id), None)
    robot = _robot_row(robot_id)
    if robot is None or task is None:
        return {"error": "not_found", "order_id": order_id, "robot_id": robot_id}
    from warehouse_control.contention import zone_for_task

    elig = evaluate_eligibility(
        robot,
        task,
        context={"maintenance_rows": _maint(robot_id), "zone": zone_for_task(task)},
    )
    return {
        "order_id": order_id,
        "robot_id": robot_id,
        "task_id": task.get("task_id"),
        "robot_warehouse_id": robot.get("warehouse_id"),
        "task_warehouse_id": task.get("warehouse_id"),
        "eligibility": elig.get("eligibility"),
        "gates_failed": elig.get("gates_failed"),
        "conflicts": elig.get("conflicts"),
        "physical_control": "disabled",
        "assign_supported": False,
    }


def sku_at_warehouse(warehouse_id: str, sku: str, location: str) -> dict:
    row = _inv(warehouse_id, sku, location)
    if row is None:
        return {"error": "not_found"}
    obs = observe_inventory(row)
    obs["physical_control"] = "disabled"
    obs["pick_as_known"] = "blocked"
    return obs
