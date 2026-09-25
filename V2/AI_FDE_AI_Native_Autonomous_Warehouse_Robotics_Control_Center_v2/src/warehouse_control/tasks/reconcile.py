"""WES vs fleet: do not close a task/order when statuses disagree (I4)."""


def reconcile_task(task: dict) -> dict:
    wes = task.get("wes_status")
    fleet = task.get("fleet_status")
    conflict = wes != fleet
    rec = {
        "task_id": task.get("task_id"),
        "order_id": task.get("order_id"),
        "wes_status": wes,
        "fleet_status": fleet,
        "conflict": conflict,
        "completable": not conflict,
    }
    if conflict:
        rec["kind"] = "TASK_STATUS"
    return rec


def reconcile_order(order_id: str, tasks: list[dict] | None = None) -> dict:
    """Order is not E2E complete unless every task is completable and COMPLETE on both SoRs."""
    from warehouse_control.repository import csv_rows

    rows = tasks if tasks is not None else csv_rows("tasks.csv")
    mine = [t for t in rows if t.get("order_id") == order_id]
    recs = [reconcile_task(t) for t in mine]
    e2e = bool(recs) and all(
        r.get("completable")
        and r.get("wes_status") == "COMPLETE"
        and r.get("fleet_status") == "COMPLETE"
        for r in recs
    )
    return {
        "order_id": order_id,
        "completable": e2e,
        "task_count": len(recs),
        "conflicts": [r for r in recs if r.get("conflict")],
        "open_or_executing": [
            r["task_id"]
            for r in recs
            if r.get("wes_status") != "COMPLETE" or r.get("fleet_status") != "COMPLETE"
        ],
    }
