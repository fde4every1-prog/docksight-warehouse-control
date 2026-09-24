"""Lifecycle regressions use isolated SQLite fixtures and a controlled clock."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import sqlite3
import uuid

import pytest
from fastapi import HTTPException

from test_fulfillment_v2 import v2db, order
import fulfillment_api as host
import lifecycle_api as api
import robot_lifecycle as lifecycle
import persona_api as persona
from test_persona_api import action, internal_intervention


def resource(rid="R1"):
    return next(r for r in api.lifecycle("fleet")["resources"] if r["resource_id"] == rid)


def test_battery_rates_restart_clock_replay_clamps_and_source_not_reset(v2db):
    start = v2db["now"]
    assert resource()["battery_pct"] == 90
    v2db["now"] += timedelta(hours=1)
    assert resource()["battery_pct"] == 85
    host._init_db()
    assert resource()["battery_pct"] == 85
    v2db["now"] = start
    assert resource()["battery_pct"] == 85
    v2db["now"] = start + timedelta(hours=2)
    row = resource()
    assert row["battery_pct"] == 80
    host.source_rows("robots")[0]["battery_soc"] = "5"
    charged = api.charging("R1", api.ChargingInput(charging=True, revision=row["revision"]), "fleet")
    assert charged["charging"] == "Y"
    v2db["now"] += timedelta(minutes=1)
    assert resource()["battery_pct"] == 85
    v2db["now"] += timedelta(hours=1)
    row = resource()
    assert row["battery_pct"] == 100
    assert row["charging"] == "N"
    assert row["Docked_for_charging"] == "N"
    v2db["now"] += timedelta(hours=2)
    assert resource()["battery_pct"] == 90
    v2db["now"] += timedelta(hours=18)
    row = resource()
    assert row["battery_pct"] == 0
    assert row["fitness_status"] == "Y"
    assert any("10%" in x for x in row["assignment_blockers"])


@pytest.mark.parametrize(
    "battery, expected",
    [("9.99", "Y"), ("10", "N")],
)
def test_automatic_docking_is_strictly_below_ten(v2db, battery, expected):
    host.source_rows("robots")[0]["battery_soc"] = battery
    row = resource()
    assert row["charging"] == expected
    assert row["Docked_for_charging"] == expected
    assert row["task_assigned"] == "N"


def test_unhealthy_unclaimed_low_robot_still_docks(v2db):
    host.source_rows("robots")[0]["battery_soc"] = "9"
    host.source_rows("robots")[0]["health_status"] = "DEGRADED"
    row = resource()
    assert row["fitness_status"] == "N"
    assert row["charging"] == row["Docked_for_charging"] == "Y"


def test_busy_low_robot_completes_stage_then_docks_before_reassignment(v2db):
    created = host.create_order(order([("A", 1)]))
    api.assign_tasks()
    with host.db_transaction() as db:
        db.execute(
            """UPDATE resource_lifecycle
               SET battery_pct=9,battery_at=?,charging='N' WHERE resource_id='R1'""",
            (host.iso(v2db["now"]),),
        )
    assert resource()["charging"] == "N"
    v2db["now"] += timedelta(seconds=45)
    assert host.run_executor_once(v2db["now"]) == 1
    row = resource()
    assert row["task_assigned"] == "N"
    assert row["charging"] == row["Docked_for_charging"] == "Y"
    detail = host.get_order(created["id"])
    assert detail["tasks"][0]["status"] == "completed"
    assert detail["tasks"][1]["status"] == "queued"


def test_paused_and_legacy_multi_resource_claims_prevent_docking(v2db):
    created = host.create_order(order([("A", 1)]))
    task_id = created["sub_orders"][0]["tasks"][0]["id"]
    resource()
    with host.db_transaction() as db:
        db.execute(
            """UPDATE tasks SET status='paused',resource_id='R1',
               resource_type='robot' WHERE id=?""",
            (task_id,),
        )
        db.execute(
            """UPDATE resource_lifecycle
               SET battery_pct=9,battery_at=?,charging='N' WHERE resource_id='R1'""",
            (host.iso(v2db["now"]),),
        )
    assert resource()["charging"] == "N"
    with host.db_transaction() as db:
        db.execute(
            """UPDATE tasks SET status='pending',resource_id=NULL,
               resource_type=NULL WHERE id=?""",
            (task_id,),
        )
        db.execute(
            """INSERT INTO task_resources(task_id,resource_id,resource_type)
               VALUES (?,'R1','robot')""",
            (task_id,),
        )
    assert resource()["charging"] == "N"
    with host.db_transaction() as db:
        db.execute("DELETE FROM task_resources WHERE task_id=?", (task_id,))
        db.execute("UPDATE tasks SET status='cancelled' WHERE id=?", (task_id,))
    assert resource()["charging"] == "Y"


def test_full_charge_transition_releases_eligibility_and_is_replay_stable(v2db):
    resource()
    with host.db_transaction() as db:
        db.execute(
            """UPDATE resource_lifecycle SET battery_pct=99,battery_at=?,
               charging='Y' WHERE resource_id='R1'""",
            (host.iso(v2db["now"]),),
        )
    before_revision = resource()["revision"]
    v2db["now"] += timedelta(minutes=1)
    row = resource()
    assert row["battery_pct"] == 100
    assert row["charging"] == row["Docked_for_charging"] == "N"
    assert row["revision"] == before_revision + 1
    assert "Resource is charging" not in row["assignment_blockers"]
    host.source_rows("robots")[0]["battery_soc"] = "1"
    host._init_db()
    replay = resource()
    assert replay["battery_pct"] == 100
    assert replay["charging"] == replay["Docked_for_charging"] == "N"
    assert replay["revision"] == row["revision"]


@pytest.mark.parametrize("battery,admitted", [("10", False), ("10.01", True), ("0", False), ("", False)])
def test_strict_new_admission_not_inflight(v2db, battery, admitted):
    host.source_rows("robots")[0]["battery_soc"] = battery
    created = host.create_order(order([("A", 1)]))
    host.run_executor_once(v2db["now"])
    assert resource()["task_assigned"] == ("Y" if admitted else "N")
    v2db["now"] += timedelta(seconds=45)
    assert host.run_executor_once(v2db["now"]) == int(admitted)
    row = resource()
    assert row["fitness_status"] == "Y"
    if admitted:
        assert row["battery_pct"] < 10
        detail = host.get_order(created["id"])
        assert detail["tasks"][0]["status"] == "completed"


def test_charging_permissions_busy_unknown_assets_and_stale(v2db):
    row = resource()
    for persona in ("supervisor", "admin", None):
        with pytest.raises(HTTPException) as error:
            api.charging("R1", api.ChargingInput(charging=True, revision=row["revision"]), persona)
        assert error.value.status_code == 403
    api.charging("R1", api.ChargingInput(charging=True, revision=row["revision"]), "fleet")
    with pytest.raises(HTTPException) as error:
        api.charging("R1", api.ChargingInput(charging=False, revision=row["revision"]), "fleet")
    assert error.value.status_code == 409
    row = resource()
    api.charging("R1", api.ChargingInput(charging=False, revision=row["revision"]), "fleet")
    host.create_order(order([("A", 1)]))
    api.assign_tasks()
    row = resource()
    with pytest.raises(HTTPException) as error:
        api.charging("R1", api.ChargingInput(charging=True, revision=row["revision"]), "fleet")
    assert error.value.status_code == 409
    asset = next(r for r in api.lifecycle("admin")["resources"] if r["resource_kind"] == "control_asset")
    with pytest.raises(HTTPException) as error:
        api.charging(asset["resource_id"], api.ChargingInput(charging=True, revision=asset["revision"]), "fleet")
    assert error.value.status_code == 422


def test_closest_payload_ties_concurrency_cadence_and_four_stages(v2db, monkeypatch):
    original = host.source_rows
    robots = tuple({**original("robots")[0], "robot_id": rid, "payload_kg": capacity}
                   for rid, capacity in (("R9", "3"), ("R3", "2"), ("R0", "500"), ("R2", "2")))
    maintenance = tuple({**original("maintenance")[0], "robot_id": r["robot_id"]} for r in robots)
    monkeypatch.setattr(host, "source_rows", lambda name: robots if name == "robots" else maintenance if name == "maintenance" else original(name))
    created = host.create_order(order([("A", 2)]))
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: api.assign_tasks(), range(2)))
    assert sum(r["assigned"] for r in results) == 1
    assert resource("R2")["task_assigned"] == "Y"
    assert set(results[0]) == {"assigned", "resumed", "rechecked", "still_waiting", "ran_at", "next_assignment_at"}
    v2db["now"] += timedelta(seconds=45)
    assert host.run_executor_once(v2db["now"]) == 1
    assert not any(r["task_assigned"] == "Y" for r in api.lifecycle("fleet")["resources"])
    # Restart does not reset the persisted 60-second assignment gate.
    host._init_db()
    host.run_executor_once(v2db["now"])
    assert host.get_order(created["id"])["tasks"][1]["status"] == "queued"
    for _ in range(3):
        v2db["now"] += timedelta(seconds=15)
        host.run_executor_once(v2db["now"])
        v2db["now"] += timedelta(seconds=45)
        assert host.run_executor_once(v2db["now"]) == 1
    detail = host.get_order(created["id"])
    assert detail["status"] == "completed"
    assert all(t["status"] == "completed" for t in detail["tasks"])
    assert (host.DB_PATH.parent / "exports" / "orders.csv").is_file()
    assert len({e["id"] for e in api.lifecycle("fleet")["events"]}) > 4


def test_unknown_battery_stays_unknown_and_fitness_refreshes(v2db):
    host.source_rows("robots")[0]["battery_soc"] = ""
    assert resource()["battery_pct"] is None
    host.source_rows("robots")[0]["battery_soc"] = "90"
    assert resource()["battery_pct"] is None
    host.source_rows("maintenance")[0]["cmms_status"] = "OPEN"
    assert resource()["fitness_status"] == "N"
    host.source_rows("maintenance")[0]["cmms_status"] = "CLOSED"
    assert resource()["fitness_status"] == "Y"
    with pytest.raises(HTTPException) as error:
        api.charging("R1", api.ChargingInput(charging=True, revision=resource()["revision"]), "fleet")
    assert error.value.status_code == 422


def test_routes_mounted_and_csv_precedes_order_id(v2db):
    routes = [r.path for r in host.router.routes]
    assert "/api/fulfillment/lifecycle" in routes
    assert "/api/fulfillment/lifecycle/tasks/{task_id}/kill" in routes
    assert "/api/fulfillment/lifecycle/resources/{resource_id}/recover" in routes
    assert "/api/fulfillment/assign-tasks" in routes
    assert routes.index("/api/fulfillment/orders.csv") < routes.index("/api/fulfillment/orders/{order_id}")


def test_manual_rechecks_stock_holds_without_replaying_reservations(v2db):
    created = host.create_order(
        order(
            [("C", 3)],
            warehouse_id=None,
            order_source="legacy_automatic",
        )
    )
    assert created["status"] == "held"
    with host.db_transaction() as db:
        db.execute("UPDATE inventory_snapshot SET wms_qty=5,erp_qty=5,vision_qty=5 WHERE sku='C'")
    result = api.assign_tasks()
    assert result["assigned"] == 1
    assert result["rechecked"] >= 1
    assert result["still_waiting"] == 0
    again = api.assign_tasks()
    assert again["assigned"] == 0
    with host._read_db() as db:
        stock = db.execute("SELECT wms_qty,erp_qty,vision_qty,reserved_qty FROM inventory_snapshot WHERE sku='C'").fetchone()
        assert tuple(stock) == (2, 2, 2, 3)
        assert db.execute("SELECT count(*) FROM tasks WHERE status='running'").fetchone()[0] == 1


def test_export_failure_does_not_rollback_order_and_next_tick_repairs(v2db, monkeypatch):
    import order_progress
    export = order_progress.export_orders
    def fail(*args):
        raise OSError("isolated export failure")
    monkeypatch.setattr(order_progress, "export_orders", fail)
    created = host.create_order(order([("A", 1)]))
    assert host.get_order(created["id"])["id"] == created["id"]
    monkeypatch.setattr(order_progress, "export_orders", export)
    host.run_executor_once(v2db["now"])
    assert created["id"] in (host.DB_PATH.parent / "exports" / "orders.csv").read_text()


def test_executor_clock_replay_does_not_advance_claims_or_battery(v2db):
    start = v2db["now"]
    host.create_order(order([("A", 1)]))
    api.assign_tasks()
    v2db["now"] += timedelta(seconds=45)
    host.run_executor_once(v2db["now"])
    assert resource()["battery_pct"] == pytest.approx(89.9375)
    v2db["now"] = start
    host.run_executor_once(v2db["now"])
    assert resource()["battery_pct"] == pytest.approx(89.9375)
    assert api.assign_tasks()["assigned"] == 0
    with host._read_db() as db:
        assert db.execute("SELECT count(*) FROM tasks WHERE status='completed'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM inventory_movements WHERE movement_type='pick_complete'").fetchone()[0] == 1


@pytest.mark.parametrize("obstacle", [None, "claimed", "unfit"])
def test_approved_recovery_preference_survives_until_atomic_minute_assignment(v2db, monkeypatch, obstacle):
    original = host.source_rows
    robots = tuple({**original("robots")[0], "robot_id": rid, "payload_kg": capacity}
                   for rid, capacity in (("R1", "1"), ("R3", "2"), ("R9", "3")))
    maintenance = tuple({**original("maintenance")[0], "robot_id": r["robot_id"]} for r in robots)
    monkeypatch.setattr(host, "source_rows", lambda name: robots if name == "robots" else maintenance if name == "maintenance" else original(name))
    persona._ensure_schema()
    created = host.create_order(order([("A", 1)]))
    host.run_executor_once(v2db["now"])
    pick_id = resource("R1")["current_task_id"]
    assert pick_id is not None
    incident = internal_intervention("resource_failure", "W1", "R1")
    action(incident, "investigate", "fleet")
    action(incident, "propose", "fleet", assigned_to="R9",
           evidence={"finding": "failed robot requires replacement", "source": "isolated test"})
    action(incident, "handoff", "fleet")
    action(incident, "approve", "supervisor")
    with host._read_db() as db:
        preferred = db.execute("SELECT * FROM task_recovery_preferences WHERE task_id=?", (pick_id,)).fetchone()
        assert preferred["resource_id"] == "R9"
        task = db.execute("SELECT * FROM tasks WHERE id=?", (pick_id,)).fetchone()
        assert task["status"] == "paused" and task["resource_id"] is None
    assert resource("R9")["task_assigned"] == "N"
    host.run_executor_once(v2db["now"])
    assert host.get_order(created["id"])["tasks"][0]["status"] == "paused"
    action(incident, "verify", "supervisor", evidence={"resume": True, "finding": "replacement approved"})
    host.run_executor_once(v2db["now"])
    assert host.get_order(created["id"])["tasks"][0]["status"] == "queued"

    if obstacle == "unfit":
        robots[2]["health_status"] = "DEGRADED"
    elif obstacle == "claimed":
        # Another real task legitimately acquires the preferred robot before
        # this task's next assignment tick; preferences are not reservations.
        other = host.create_order(order([("A", 3)]))
        other_pick = other["sub_orders"][0]["tasks"][0]["id"]
        with host.db_transaction() as db:
            db.execute("""UPDATE tasks SET status='running',resource_id='R9',
                       resource_type='robot',started_at=?,due_at=? WHERE id=?""",
                       (host.iso(v2db["now"]), host.iso(v2db["now"] + timedelta(seconds=120)), other_pick))
    v2db["now"] += timedelta(seconds=60)
    host._init_db()  # Preference survives schema initialization/restart.
    host.run_executor_once(v2db["now"])
    detail = host.get_order(created["id"])
    pick = next(t for t in detail["tasks"] if t["id"] == pick_id)
    if obstacle:
        assert pick["status"] == "queued"
        assert pick["resource_id"] is None
        assert "Preferred recovery resource R9" in pick["wait_reason"]
        assert ("already claimed" if obstacle == "claimed" else "HEALTHY") in pick["wait_reason"]
        assert resource("R3")["task_assigned"] == "N"  # No silent normal-sort fallback.
        with host._read_db() as db:
            assert db.execute("SELECT resource_id FROM task_recovery_preferences WHERE task_id=?", (pick_id,)).fetchone()[0] == "R9"
        if obstacle == "unfit":
            robots[2]["health_status"] = "HEALTHY"
        else:
            host.command_order(other["id"], "cancel")
        v2db["now"] += timedelta(seconds=60)
        host.run_executor_once(v2db["now"])
        pick = next(t for t in host.get_order(created["id"])["tasks"] if t["id"] == pick_id)
    assert pick["status"] == "running"
    assert pick["resource_id"] == "R9"  # R3 is the normal closest adequate winner.
    with host._read_db() as db:
        assert db.execute("SELECT 1 FROM task_recovery_preferences WHERE task_id=?", (pick_id,)).fetchone() is None
        assert db.execute("SELECT count(*) FROM tasks WHERE resource_id='R9' AND status IN ('running','paused')").fetchone()[0] == 1
        assert db.execute("SELECT 1 FROM events WHERE order_id=? AND message LIKE '%Recovery preference%R9%'", (created["id"],)).fetchone()


def failure_payload(task, request_id=None, reason="Fork obstruction demo"):
    return api.TaskFailureInput(
        request_id=request_id or uuid.uuid4(),
        assignment_token=task["assignment_token"],
        reason=reason,
    )


def test_running_robot_task_projection_and_demo_failure_is_atomic_and_idempotent(v2db):
    created = host.create_order(order([("A", 2)]))
    api.assign_tasks()
    response = api.tasks("supervisor")
    assert set(response) == {"tasks", "server_time"}
    assert len(response["tasks"]) == 1
    task = response["tasks"][0]
    assert {
        "task_id", "order_id", "sub_order_id", "sku", "robot_id", "warehouse_id",
        "resource_id", "resource_kind",
        "stage", "status", "display_status", "started_at", "due_at",
        "assignment_token", "failure_reason", "failed_at", "intervention_id",
        "recovery_url",
    } == set(task)
    assert task["order_id"] == created["id"]
    assert task["robot_id"] == "R1"
    assert task["status"] == "running"

    before_sources = tuple(dict(row) for row in host.source_rows("robots"))
    request_id = uuid.uuid4()
    failed = api.fail_task(task["task_id"], failure_payload(task, request_id), "fleet")
    assert failed["status"] == "paused"
    assert failed["display_status"] == "Failed (demo) / Recovery required"
    assert failed["failure_reason"] == "Fork obstruction demo"
    assert failed["recovery_url"] == (
        f"/workspace/interventions/{failed['intervention_id']}"
    )
    assert tuple(dict(row) for row in host.source_rows("robots")) == before_sources

    retry = api.fail_task(task["task_id"], failure_payload(task, request_id), "fleet")
    assert retry == failed
    with host._read_db() as db:
        assert db.execute(
            "SELECT count(*) FROM lifecycle_demo_failures"
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT count(*) FROM persona_interventions WHERE kind='resource_failure'"
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT count(*) FROM inventory_movements"
        ).fetchone()[0] == 1  # intake reservation only
        assert db.execute(
            "SELECT status FROM sub_orders WHERE id=?", (task["sub_order_id"],)
        ).fetchone()[0] == "recovery_required"

    with pytest.raises(HTTPException) as conflict:
        api.fail_task(
            task["task_id"],
            failure_payload(task, request_id, reason="Different payload"),
            "fleet",
        )
    assert conflict.value.status_code == 409


@pytest.mark.parametrize("persona_name", [None, "supervisor", "admin"])
def test_demo_failure_requires_explicit_fleet_header(v2db, persona_name):
    host.create_order(order([("A", 1)]))
    api.assign_tasks()
    task = api.tasks("fleet")["tasks"][0]
    with pytest.raises(HTTPException) as error:
        api.fail_task(task["task_id"], failure_payload(task), persona_name)
    assert error.value.status_code == 403
    assert api.tasks("admin")["tasks"][0]["status"] == "running"


def test_stale_asset_and_paused_failures_rejected_and_ticks_cannot_autoheal(v2db):
    host.create_order(order([("A", 1)]))
    api.assign_tasks()
    task = api.tasks("fleet")["tasks"][0]
    stale = {**task, "assignment_token": "stale"}
    with pytest.raises(HTTPException) as error:
        api.fail_task(task["task_id"], failure_payload(stale), "fleet")
    assert error.value.status_code == 409
    failed = api.fail_task(task["task_id"], failure_payload(task), "fleet")
    v2db["now"] += timedelta(minutes=5)
    for _ in range(2):
        host.run_executor_once(v2db["now"])
        api.assign_tasks()
        host._init_db()
    # The simulator projection now contains ongoing assigned functions only;
    # historical manual incidents remain durable in Core but do not appear.
    visible = api.tasks("fleet")["tasks"]
    assert visible == []
    host.command_order(task["order_id"], "cancel")
    assert api.tasks("fleet")["tasks"] == []
    with host._read_db() as db:
        allocation = db.execute(
            "SELECT reserved_qty,picked_qty,completed_qty FROM sub_order_allocations"
        ).fetchone()
        assert tuple(allocation) == (1, 0, 0)
        assert db.execute(
            "SELECT status FROM orders WHERE id=?", (task["order_id"],)
        ).fetchone()[0] == "recovery_required"
    with pytest.raises(HTTPException) as error:
        api.fail_task(task["task_id"], failure_payload(failed), "fleet")
    assert error.value.status_code == 409

    # A control-asset stage can never enter the robot-only projection/action.
    with host.db_transaction() as db:
        db.execute(
            """UPDATE tasks SET status='running',resource_id='W1-CONVEYOR',
               resource_type='control_asset',started_at=?,due_at=? WHERE stage='move'""",
            (host.iso(v2db["now"]), host.iso(v2db["now"] + timedelta(seconds=45))),
        )
        asset = db.execute("SELECT * FROM tasks WHERE stage='move'").fetchone()
        token = lifecycle.assignment_token(asset)
    with pytest.raises(HTTPException) as error:
        api.fail_task(
            asset["id"],
            api.TaskFailureInput(
                request_id=uuid.uuid4(), assignment_token=token, reason="not a robot"
            ),
            "fleet",
        )
    assert error.value.status_code == 409


def test_demo_failure_uses_explicit_recovery_and_preserves_preferred_replacement(
    v2db, monkeypatch
):
    original = host.source_rows
    robots = tuple(
        {
            **original("robots")[0],
            "robot_id": rid,
            "payload_kg": capacity,
        }
        for rid, capacity in (("R1", "1"), ("R3", "2"), ("R9", "3"))
    )
    maintenance = tuple(
        {**original("maintenance")[0], "robot_id": robot["robot_id"]}
        for robot in robots
    )
    monkeypatch.setattr(
        host,
        "source_rows",
        lambda name: (
            robots
            if name == "robots"
            else maintenance
            if name == "maintenance"
            else original(name)
        ),
    )
    created = host.create_order(order([("A", 1)]))
    api.assign_tasks()
    task = api.tasks("fleet")["tasks"][0]
    first_request = uuid.uuid4()
    first_payload = failure_payload(task, first_request)
    failed = api.fail_task(task["task_id"], first_payload, "fleet")

    incident = persona.get_intervention(failed["intervention_id"], "fleet")
    assert incident["status"] == "investigating"
    assert incident["proposed_action"] is None
    assert "propose" in incident["allowed_actions"]
    proposed = action(
        incident,
        "propose",
        "fleet",
        assigned_to="R9",
        evidence={
            "source": "modeled_control_tower",
            "notes": "replacement selected in existing recovery UI",
        },
    )
    assert proposed["status"] == "awaiting_approval"
    approved = action(proposed, "approve", "supervisor")
    assert approved["proposed_action"]["approved"] is True
    assert "verify" in approved["allowed_actions"]
    action(
        approved,
        "verify",
        "supervisor",
        evidence={"resume": True, "finding": "approved replacement verified"},
    )
    assert api.tasks("fleet")["tasks"] == []
    with host._read_db() as db:
        recovered = db.execute(
            "SELECT * FROM tasks WHERE id=?", (task["task_id"],)
        ).fetchone()
        assert recovered["status"] == "queued"
        assert recovered["resource_id"] is None
        assert db.execute(
            "SELECT resource_id FROM task_recovery_preferences WHERE task_id=?",
            (task["task_id"],),
        ).fetchone()[0] == "R9"
        assert db.execute(
            "SELECT count(*) FROM inventory_movements WHERE order_id=?",
            (created["id"],),
        ).fetchone()[0] == 1

    v2db["now"] += timedelta(seconds=60)
    host.run_executor_once(v2db["now"])
    recovered = host.get_order(created["id"])["tasks"][0]
    assert recovered["status"] == "running"
    assert recovered["resource_id"] == "R9"
    assert recovered["completed_at"] is None
    current = api.tasks("fleet")["tasks"][0]
    assert current["status"] == "running"
    assert current["display_status"] == "Running"
    assert current["assignment_token"] != task["assignment_token"]
    assert current["failure_reason"] is None
    assert current["intervention_id"] is None
    assert current["recovery_url"] is None

    second = api.fail_task(
        current["task_id"], failure_payload(current, reason="Second assignment failure"), "fleet"
    )
    assert second["intervention_id"] != failed["intervention_id"]
    assert second["assignment_token"] == current["assignment_token"]
    # A delayed retry of the historical command remains idempotent and cannot
    # affect the new assignment/failure.
    assert api.fail_task(task["task_id"], first_payload, "fleet") == failed
    with host._read_db() as db:
        history = db.execute(
            """SELECT request_id,resolved_at FROM lifecycle_demo_failures
               WHERE task_id=? ORDER BY failed_at""",
            (task["task_id"],),
        ).fetchall()
        assert len(history) == 2
        assert str(first_request) == history[0]["request_id"]
        assert history[0]["resolved_at"] is not None
        assert history[1]["resolved_at"] is None


def test_old_task_keyed_failure_schema_migrates_without_losing_history():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE tasks(
             id TEXT PRIMARY KEY,order_id TEXT,stage TEXT,status TEXT,
             resource_id TEXT,resource_type TEXT,started_at TEXT,due_at TEXT,
             completed_at TEXT,sub_order_id TEXT)"""
    )
    db.execute("INSERT INTO tasks(id) VALUES ('TS-OLD')")
    db.execute(
        """CREATE TABLE lifecycle_demo_failures(
             task_id TEXT PRIMARY KEY,request_id TEXT NOT NULL UNIQUE,
             request_fingerprint TEXT NOT NULL,assignment_token TEXT NOT NULL,
             failed_resource_id TEXT NOT NULL,failure_reason TEXT NOT NULL,
             failed_at TEXT NOT NULL,intervention_id TEXT NOT NULL UNIQUE,
             response_json TEXT,resolved_at TEXT)"""
    )
    db.execute(
        """INSERT INTO lifecycle_demo_failures VALUES
           ('TS-OLD','00000000-0000-0000-0000-000000000001','fp','token',
            'R1','old failure','2030-01-01T00:00:00Z','INT-OLD','{}',
            '2030-01-01T00:01:00Z')"""
    )
    lifecycle.ensure_schema(db)
    columns = {
        row["name"]: row["pk"]
        for row in db.execute("PRAGMA table_info(lifecycle_demo_failures)")
    }
    assert columns["request_id"] == 1
    assert columns["task_id"] == 0
    assert tuple(db.execute(
        "SELECT task_id,intervention_id,resolved_at FROM lifecycle_demo_failures"
    ).fetchone()) == (
        "TS-OLD", "INT-OLD", "2030-01-01T00:01:00Z"
    )
    indexes = {
        row["name"]
        for row in db.execute("PRAGMA index_list(lifecycle_demo_failures)")
    }
    assert "lifecycle_one_active_failure_per_task" in indexes


def test_unresolved_demo_marker_blocks_generic_queued_path_only(v2db):
    failed_order = host.create_order(order([("A", 1)]))
    api.assign_tasks()
    failed_task = api.tasks("fleet")["tasks"][0]
    api.fail_task(failed_task["task_id"], failure_payload(failed_task), "fleet")
    independent_order = host.create_order(
        order(
            [("B", 1)],
            warehouse_id=None,
            order_source="legacy_automatic",
        )
    )

    # Simulate an unrelated generic recovery command attempting to queue work
    # without resolving the linked incident. The executor must honor the
    # explicit marker rather than trusting status alone.
    with host.db_transaction() as db:
        db.execute(
            """UPDATE tasks SET status='queued',resource_id=NULL,
               resource_type=NULL,started_at=NULL,due_at=NULL
               WHERE id=?""",
            (failed_task["task_id"],),
        )
    v2db["now"] += timedelta(seconds=60)
    host.run_executor_once(v2db["now"])
    failed_detail = host.get_order(failed_order["id"])
    assert failed_detail["tasks"][0]["status"] == "queued"
    assert failed_detail["tasks"][0]["resource_id"] is None
    independent_detail = host.get_order(independent_order["id"])
    assert independent_detail["tasks"][0]["status"] == "running"
    assert independent_detail["tasks"][0]["resource_id"] == "R2"


def kill_payload(task, request_id=None, reason="Simulator operator kill"):
    return api.TaskKillInput(
        request_id=request_id or uuid.uuid4(),
        assignment_token=task["assignment_token"],
        reason=reason,
    )


def test_simulator_kill_promptly_replaces_robot_without_touching_cadence_or_stock(
    v2db, monkeypatch
):
    original = host.source_rows
    robots = tuple(
        {**original("robots")[0], "robot_id": rid, "payload_kg": "500"}
        for rid in ("R1", "R9")
    )
    maintenance = tuple(
        {**original("maintenance")[0], "robot_id": robot["robot_id"]}
        for robot in robots
    )
    monkeypatch.setattr(
        host, "source_rows",
        lambda name: robots if name == "robots" else maintenance if name == "maintenance" else original(name),
    )
    created = host.create_order(order([("A", 2)]))
    api.assign_tasks()
    task = api.tasks("fleet")["tasks"][0]
    assert task["resource_id"] == "R1"
    with host._read_db() as db:
        next_assignment = db.execute(
            "SELECT next_assignment_at FROM lifecycle_scheduler WHERE id=1"
        ).fetchone()[0]
        movements = db.execute(
            "SELECT count(*) FROM inventory_movements WHERE order_id=?", (created["id"],)
        ).fetchone()[0]
    request_id = uuid.uuid4()
    payload = kill_payload(task, request_id)
    result = api.kill_task(task["task_id"], payload, "fleet")
    assert result["replacement_status"] == "replaced"
    assert result["resource_id"] == "R9"
    assert result["resource_kind"] == "robot"
    assert result["started_at"] == host.iso(v2db["now"])
    assert result["due_at"] == host.iso(v2db["now"] + timedelta(seconds=45))
    assert result["assignment_token"] != task["assignment_token"]
    assert api.kill_task(task["task_id"], payload, "fleet") == result
    with host._read_db() as db:
        assert db.execute(
            "SELECT next_assignment_at FROM lifecycle_scheduler WHERE id=1"
        ).fetchone()[0] == next_assignment
        assert db.execute(
            "SELECT count(*) FROM inventory_movements WHERE order_id=?", (created["id"],)
        ).fetchone()[0] == movements
        assert db.execute(
            """SELECT 1 FROM lifecycle_failed_resources
               WHERE resource_id='R1' AND recovered_at IS NULL"""
        ).fetchone()
        assert db.execute(
            "SELECT count(*) FROM lifecycle_simulator_failures"
        ).fetchone()[0] == 1
    with pytest.raises(HTTPException) as stale:
        api.kill_task(task["task_id"], kill_payload(task), "fleet")
    assert stale.value.status_code == 409
    recovered = api.recover_resource("R1", "fleet")
    assert recovered == {
        "resource_id": "R1", "resource_kind": "robot", "status": "recovered"
    }
    assert api.recover_resource("R1", "fleet") == recovered
    current = api.tasks("fleet")["tasks"][0]
    second = api.kill_task(current["task_id"], kill_payload(current), "fleet")
    assert second["replacement_status"] == "replaced"
    assert second["resource_id"] == "R1"
    with host._read_db() as db:
        assert db.execute(
            "SELECT count(*) FROM lifecycle_simulator_failures"
        ).fetchone()[0] == 2
        assert db.execute(
            "SELECT count(*) FROM inventory_movements WHERE order_id=?", (created["id"],)
        ).fetchone()[0] == movements


def test_simulator_kill_replaces_control_asset_and_projection_is_resource_neutral(
    v2db
):
    host.create_order(order([("A", 1)]))
    api.assign_tasks()
    with host.db_transaction() as db:
        task = db.execute(
            "SELECT * FROM tasks WHERE status='running' ORDER BY id LIMIT 1"
        ).fetchone()
        db.execute(
            """UPDATE tasks SET stage='pack_feed',resource_id='W1-CONVEYOR',
               resource_type='control_asset',assignment_version=assignment_version+1
               WHERE id=?""",
            (task["id"],),
        )
    projected = api.tasks("fleet")["tasks"][0]
    assert projected["resource_id"] == "W1-CONVEYOR"
    assert projected["resource_kind"] == "control_asset"
    result = api.kill_task(projected["task_id"], kill_payload(projected), "fleet")
    assert result["replacement_status"] == "replaced"
    assert result["resource_id"] == "W1-PACK_STATION"
    assert result["resource_kind"] == "control_asset"


@pytest.mark.parametrize("persona_name", [None, "supervisor", "admin"])
def test_simulator_kill_requires_fleet_and_completion_race_is_rejected(
    v2db, persona_name
):
    host.create_order(order([("A", 1)]))
    api.assign_tasks()
    task = api.tasks("fleet")["tasks"][0]
    with pytest.raises(HTTPException) as forbidden:
        api.kill_task(task["task_id"], kill_payload(task), persona_name)
    assert forbidden.value.status_code == 403
    with host.db_transaction() as db:
        db.execute(
            "UPDATE tasks SET status='completed',completed_at=? WHERE id=?",
            (host.iso(v2db["now"]), task["task_id"]),
        )
    with pytest.raises(HTTPException) as race:
        api.kill_task(task["task_id"], kill_payload(task), "fleet")
    assert race.value.status_code == 409


def test_simulator_kill_waits_then_scheduler_retries_when_candidate_appears(
    v2db, monkeypatch
):
    original = host.source_rows
    robots = [dict(original("robots")[0])]
    maintenance = [dict(original("maintenance")[0])]
    monkeypatch.setattr(
        host, "source_rows",
        lambda name: tuple(robots) if name == "robots" else tuple(maintenance) if name == "maintenance" else original(name),
    )
    created = host.create_order(order([("A", 1)]))
    api.assign_tasks()
    task = api.tasks("fleet")["tasks"][0]
    result = api.kill_task(task["task_id"], kill_payload(task), "fleet")
    assert result["replacement_status"] == "waiting"
    assert result["resource_id"] is None
    assert api.tasks("fleet")["tasks"] == []
    robots.append({**robots[0], "robot_id": "R9"})
    maintenance.append({**maintenance[0], "robot_id": "R9"})
    v2db["now"] += timedelta(seconds=60)
    host.run_executor_once(v2db["now"])
    current = next(
        item for item in host.get_order(created["id"])["tasks"]
        if item["id"] == task["task_id"]
    )
    assert current["status"] == "running"
    assert current["resource_id"] == "R9"
    assert current["due_at"] == host.iso(v2db["now"] + timedelta(seconds=45))


def test_policy_v1_running_assignment_is_hidden_and_kill_is_non_mutating(v2db):
    created = host.create_order(order([("A", 1)]))
    api.assign_tasks()
    task = api.tasks("fleet")["tasks"][0]
    with host.db_transaction() as db:
        db.execute(
            "UPDATE orders SET policy_version=1 WHERE id=?", (created["id"],)
        )
    with host._read_db() as db:
        task_before = dict(db.execute(
            "SELECT * FROM tasks WHERE id=?", (task["task_id"],)
        ).fetchone())
        resource_before = dict(db.execute(
            "SELECT * FROM resource_lifecycle WHERE resource_id=?",
            (task["resource_id"],),
        ).fetchone())
        stock_before = [
            tuple(row)
            for row in db.execute(
                """SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,
                          picked_qty,completed_qty,revision
                   FROM inventory_snapshot ORDER BY id"""
            )
        ]
    assert api.tasks("fleet")["tasks"] == []
    with pytest.raises(HTTPException) as unsupported:
        api.kill_task(task["task_id"], kill_payload(task), "fleet")
    assert unsupported.value.status_code == 409
    assert "policy-v2" in unsupported.value.detail
    with host._read_db() as db:
        assert dict(db.execute(
            "SELECT * FROM tasks WHERE id=?", (task["task_id"],)
        ).fetchone()) == task_before
        assert dict(db.execute(
            "SELECT * FROM resource_lifecycle WHERE resource_id=?",
            (task["resource_id"],),
        ).fetchone()) == resource_before
        assert [
            tuple(row)
            for row in db.execute(
                """SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,
                          picked_qty,completed_qty,revision
                   FROM inventory_snapshot ORDER BY id"""
            )
        ] == stock_before
        assert db.execute(
            "SELECT count(*) FROM lifecycle_simulator_failures"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT count(*) FROM lifecycle_failed_resources"
        ).fetchone()[0] == 0