from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from warehouse_control.allocator.filter_score import allocate_for_task, rejection_reasons
from warehouse_control.browse import featured_catalog, order_browse, robot_on_order
from warehouse_control.contention import snapshot as contention_snapshot
from warehouse_control.contention import zone_for_task
from warehouse_control.decision.engine import decide
from warehouse_control.diagnostics import run
from warehouse_control.eligibility.policy import evaluate_eligibility
from warehouse_control.execution.executor import execute
from warehouse_control.fulfillment.cutoff import assess_cutoff
from warehouse_control.identity.resolver import resolve_alias, resolve_robot
from warehouse_control.injects.replay import replay_inject
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.repository import csv_rows, query
from warehouse_control.tasks.reconcile import reconcile_order, reconcile_task
from warehouse_control.workflow import workflow_snapshot

UI_FILE = Path(__file__).resolve().parent / "static" / "dashboard.html"
CONTENTION_UI_FILE = Path(__file__).resolve().parent / "static" / "contention.html"
BROWSE_UI_FILE = Path(__file__).resolve().parent / "static" / "browse.html"
WORKFLOW_UI_FILE = Path(__file__).resolve().parent / "static" / "workflow.html"

app = FastAPI(
    title="Synthetic Warehouse Control Center Brownfield API", version="2.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _not_found():
    return JSONResponse({"error": "not_found"}, status_code=404)


def _robot_csv(robot_id: str) -> dict | None:
    for row in csv_rows("robots.csv"):
        if row.get("robot_id") == robot_id:
            return row
    return None


def _task_csv(task_id: str) -> dict | None:
    for row in csv_rows("tasks.csv"):
        if row.get("task_id") == task_id:
            return row
    return None


def _inventory_row(warehouse_id: str, sku: str, location: str) -> dict | None:
    for row in csv_rows("inventory_snapshot.csv"):
        if (
            row.get("warehouse_id") == warehouse_id
            and row.get("sku") == sku
            and row.get("location") == location
        ):
            return row
    return None


def _maintenance_for(robot_id: str) -> list[dict]:
    rows = []
    for row in csv_rows("maintenance.csv"):
        if row.get("robot_id") == robot_id:
            item = dict(row)
            item["wo_id"] = row.get("work_order_id")
            rows.append(item)
    return rows


@app.get("/")
@app.get("/ui")
def dashboard():
    """Read-only exception wall. GET only. Does not enable OT."""
    return FileResponse(UI_FILE, media_type="text/html")


@app.get("/contention")
def contention_ui():
    """Observe-only contention demo. GET only. Does not lock resources or enable OT."""
    return FileResponse(CONTENTION_UI_FILE, media_type="text/html")


@app.get("/contention/snapshot")
def contention_snapshot_route():
    """Location / dock / inventory refuse-or-abstain. No reservation."""
    return contention_snapshot()


@app.get("/workflow")
def workflow_ui():
    """Supervisor order-to-truck view. GET only."""
    return FileResponse(WORKFLOW_UI_FILE, media_type="text/html")


@app.get("/workflow/snapshot")
def workflow_snapshot_route():
    return workflow_snapshot()


@app.get("/browse")
def browse_ui():
    """Order-first lookup. GET only. Does not enable OT."""
    return FileResponse(BROWSE_UI_FILE, media_type="text/html")


@app.get("/lookup/featured")
def lookup_featured():
    return featured_catalog()


@app.get("/orders/{order_id}/browse")
def order_browse_route(order_id: str):
    result = order_browse(order_id)
    if result.get("error") == "not_found":
        return _not_found()
    return result


@app.get("/orders/{order_id}/robots/{robot_id}")
def order_robot_route(order_id: str, robot_id: str):
    result = robot_on_order(order_id, robot_id)
    if result.get("error") == "not_found":
        return _not_found()
    return result


@app.get("/dashboard/snapshot")
def dashboard_snapshot():
    """One payload for the UI first paint. Observe-only."""
    return {
        "health": health(),
        "safety_preview": {
            **decide({"intent": "release_zone"}),
            "physical_control": "disabled",
        },
        "order_968": reconcile_order("ORD-000968"),
        "physical_control": "disabled",
        "assign_supported": False,
    }


@app.get("/health")
def health():
    return {"status": "ok", "physical_control": "disabled"}


@app.get("/diagnostics")
def diagnostics():
    return run()


@app.get("/robots/{robot_id}/rejection-reasons")
def robot_rejection_reasons(
    robot_id: str,
    task_id: str = Query(...),
    inject_id: str | None = Query(None),
):
    result = rejection_reasons(robot_id, task_id, inject_id=inject_id)
    if result.get("error") == "not_found":
        return _not_found()
    return result


@app.get("/robots/{robot_id}")
def robot(robot_id: str):
    rows = query("select * from robots where robot_id=?", (robot_id,))
    return rows[0] if rows else {"error": "not_found"}


@app.get("/identity/alias/{alias}")
def identity_by_alias(alias: str):
    return resolve_alias(alias)


@app.get("/identity/{robot_id}")
def identity_by_robot(robot_id: str):
    if _robot_csv(robot_id) is None:
        return _not_found()
    return resolve_robot(robot_id)


@app.get("/eligibility")
def eligibility(
    robot_id: str = Query(...),
    task_id: str = Query(...),
):
    robot_row = _robot_csv(robot_id)
    task_row = _task_csv(task_id)
    if robot_row is None or task_row is None:
        return _not_found()
    zone = zone_for_task(task_row)
    result = evaluate_eligibility(
        robot_row,
        task_row,
        context={"maintenance_rows": _maintenance_for(robot_id), "zone": zone},
    )
    return {
        "robot_id": robot_id,
        "task_id": task_id,
        "dest_zone": task_row.get("dest_zone"),
        "zone": {
            "zone_id": zone.get("zone_id"),
            "robot_access": zone.get("robot_access"),
        },
        **result,
    }


@app.get("/inventory")
def inventory(
    warehouse_id: str = Query(...),
    sku: str = Query(...),
    location: str = Query(...),
):
    row = _inventory_row(warehouse_id, sku, location)
    if row is None:
        return _not_found()
    return observe_inventory(row)


@app.get("/tasks/{task_id}/reconcile")
def task_reconcile(task_id: str):
    task_row = _task_csv(task_id)
    if task_row is None:
        return _not_found()
    return reconcile_task(task_row)


@app.get("/orders/{order_id}/cutoff")
def order_cutoff(order_id: str):
    result = assess_cutoff(order_id)
    if result.get("error") == "not_found":
        return _not_found()
    return result


@app.get("/preview/allocate")
def preview_allocate(
    task_id: str = Query(...),
    inject_id: str | None = Query(None),
):
    result = allocate_for_task(task_id, inject_id=inject_id)
    if result.get("error") == "not_found":
        return _not_found()
    return result


@app.get("/injects/{inject_id}/replay")
def inject_replay(inject_id: str, task_id: str = Query(...)):
    try:
        return replay_inject(inject_id, task_id)
    except KeyError:
        return _not_found()


@app.get("/execution/status")
def execution_status():
    stub = execute()
    return {
        "physical_control": stub["physical_control"],
        "ot_apply_supported": False,
    }


@app.get("/preview/decide")
def preview_decide(
    intent: str = Query(...),
    uncertain: bool = Query(False),
):
    """Observe-only preview. Does not apply OT."""
    proposal = {"intent": intent}
    if intent == "allocate_as_known":
        proposal["inventory"] = {"uncertain": uncertain}
    return {**decide(proposal), "physical_control": "disabled"}
