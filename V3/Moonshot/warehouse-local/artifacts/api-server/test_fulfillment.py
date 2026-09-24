"""V2 operational API regressions; every test uses an isolated SQLite file."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import fulfillment_api as fulfillment  # noqa: E402


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    original = fulfillment._raw_source_rows

    def rows(dataset):
        source = original(dataset)
        if dataset == "inventory":
            return tuple({**row, "weight_kg": "1"} for row in source)
        return source

    rows.cache_clear = original.cache_clear
    monkeypatch.setattr(fulfillment, "_raw_source_rows", rows)
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "fulfillment.sqlite")
    clock = {"now": datetime(2030, 1, 1, tzinfo=timezone.utc)}
    monkeypatch.setattr(fulfillment, "utc_now", lambda: clock["now"])
    fulfillment._init_db()
    return clock


def make_order(quantity=1, request_id=None, sku="SKU-01146"):
    return fulfillment.OrderInput(
        warehouse_id="DC-01",
        priority="standard",
        ship_by="2030-01-01T04:00:00Z",
        lines=[fulfillment.OrderLineInput(sku=sku, quantity=quantity)],
        request_id=request_id or str(uuid.uuid4()),
    )


def order_tasks(order):
    return [
        task
        for sub_order in order["sub_orders"]
        for task in sub_order["tasks"]
    ]


def test_catalog_uses_isolated_fixture_and_reports_complete_sources(isolated_db):
    result = fulfillment.catalog()
    assert len(result["warehouses"]) == 18
    assert result["counts"]["inventory"] == 9360
    assert result["fulfillment_policies"]["default"] == 2


def test_explicit_draft_is_v2_auto_queued_and_start_is_compatible(isolated_db):
    created = fulfillment.create_order(make_order())
    assert created["policy_version"] == 2
    assert created["status"] == "active"
    assert created["warehouse_id"] == "DC-01"
    assert fulfillment.command_order(created["id"], "start")["id"] == created["id"]
    assert {sub["status"] for sub in created["sub_orders"]} == {"queued"}


def test_v2_executor_pick_is_exactly_once_without_legacy_effects(isolated_db):
    clock = isolated_db
    created = fulfillment.create_order(make_order(quantity=2))
    fulfillment.run_executor_once(clock["now"])
    clock["now"] += timedelta(seconds=45)
    assert fulfillment.run_executor_once(clock["now"]) == 1
    assert fulfillment.run_executor_once(clock["now"]) == 0
    with fulfillment._read_db() as db:
        allocation = db.execute(
            "SELECT reserved_qty,picked_qty FROM sub_order_allocations "
            "WHERE sub_order_id IN (SELECT id FROM sub_orders WHERE order_id=?)",
            (created["id"],),
        ).fetchone()
        assert tuple(allocation) == (0, 2)
        assert db.execute("SELECT COUNT(*) FROM stock_effects").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0


def test_v2_idempotency_oversell_and_cancel_restore_only_unpicked(isolated_db):
    request_id = str(uuid.uuid4())
    first = fulfillment.create_order(make_order(quantity=180, request_id=request_id))
    assert fulfillment.create_order(
        make_order(quantity=180, request_id=request_id)
    )["id"] == first["id"]
    held = fulfillment.create_order(make_order(quantity=20))
    assert held["status"] == "held"
    fulfillment.command_order(first["id"], "cancel")
    assert fulfillment.command_order(held["id"], "retry")["status"] == "active"


def test_inventory_resource_metrics_are_current_location_free(isolated_db):
    envelope = fulfillment.resources("inventory", warehouse_id="DC-01")
    row = next(item for item in envelope["rows"] if item["sku"] == "SKU-01146")
    with fulfillment._read_db() as db:
        current = next(
            item for item in fulfillment.inventory_rows(db, "DC-01", "SKU-01146")
            if item["source_row_index"] == row["_scenario_row_id"]
        )
    assert row["available_to_promise"] == current["allocatable_qty"]
    assert row["poc_reserved"] == current["reserved_qty"]


def test_v2_resource_readiness_and_capacity_have_no_manual_bypass(isolated_db):
    with fulfillment._read_db() as db:
        robot = next(
            row for row in fulfillment.source_rows("robots")
            if fulfillment.v2_robot_eligibility(db, row, "DC-01", "pick", 1)[0]
        )
        source_ready = {
            **robot, "calibration_status": "INVALID",
            "safety_cert_status": "INVALID",
        }
        assert fulfillment.v2_robot_eligibility(
            db, source_ready, "DC-01", "pick", 1
        )[0]
        too_heavy = float(robot["payload_kg"]) + 1
        assert not fulfillment.v2_robot_eligibility(
            db, robot, "DC-01", "pick", too_heavy
        )[0]
    asset = next(
        row for row in fulfillment.source_rows("control_assets")
        if row["warehouse_id"] == "DC-01" and row["state"] == "AVAILABLE"
    )
    wrong_stage = "stage" if asset["asset_type"] not in {"DOCK_DOOR", "VISION_GATE", "CONVEYOR"} else "pack_feed"
    assert not fulfillment.v2_asset_eligibility(asset, "OTHER", wrong_stage)[0]


def test_scenario_edits_are_blocked_by_active_v2_work(isolated_db):
    robot = fulfillment.resources("robots")["rows"][0]
    order = fulfillment.create_order(make_order())
    with pytest.raises(Exception, match="Cancel the order or let it finish"):
        fulfillment.patch_scenario_resource(
            "robots", robot["_scenario_row_id"], {"health_status": "DEGRADED"}, 0
        )
    fulfillment.command_order(order["id"], "cancel")
    changed = fulfillment.patch_scenario_resource(
        "robots", robot["_scenario_row_id"], {"health_status": "DEGRADED"}, 0
    )
    assert changed["scenario_modified_count"] == 1


def test_retry_trigger_is_order_scoped_immediate_and_idempotent(isolated_db):
    clock = isolated_db
    stock_owner = fulfillment.create_order(make_order(quantity=180))
    held = fulfillment.create_order(make_order(quantity=20))
    unrelated = fulfillment.create_order(make_order(sku="SKU-00035"))
    assert held["status"] == "held"
    fulfillment.command_order(stock_owner["id"], "cancel")

    with fulfillment._read_db() as db:
        scheduler_before = tuple(db.execute(
            "SELECT last_assignment_at,next_assignment_at,last_observed_at "
            "FROM lifecycle_scheduler WHERE id=1"
        ).fetchone())
    planned = fulfillment.command_order(held["id"], "retry")
    running = next(task for task in order_tasks(planned) if task["status"] == "running")
    assert all(
        task["status"] == "queued"
        for task in order_tasks(fulfillment.get_order(unrelated["id"]))
        if task["stage"] == "pick"
    )

    retried = fulfillment.command_order(held["id"], "retry")
    same = next(task for task in order_tasks(retried) if task["id"] == running["id"])
    assert (same["resource_id"], same["assignment_version"], same["started_at"]) == (
        running["resource_id"], running["assignment_version"], running["started_at"]
    )
    with fulfillment._read_db() as db:
        scheduler_after = tuple(db.execute(
            "SELECT last_assignment_at,next_assignment_at,last_observed_at "
            "FROM lifecycle_scheduler WHERE id=1"
        ).fetchone())
        duplicate_claims = db.execute(
            """SELECT resource_id,count(*) FROM tasks
               WHERE resource_id IS NOT NULL AND status IN ('running','paused')
               GROUP BY resource_id HAVING count(*)>1"""
        ).fetchall()
    assert scheduler_after == scheduler_before
    assert duplicate_claims == []
    assert clock["now"].tzinfo is timezone.utc


def test_retry_rechecks_queued_work_when_resources_later_appear(isolated_db, monkeypatch):
    original = fulfillment.source_rows
    resources_available = {"value": False}

    def rows(dataset):
        if dataset == "robots" and not resources_available["value"]:
            return ()
        return original(dataset)

    monkeypatch.setattr(fulfillment, "source_rows", rows)
    created = fulfillment.create_order(make_order())
    waiting = fulfillment.command_order(created["id"], "retry")
    pick = next(task for task in order_tasks(waiting) if task["stage"] == "pick")
    assert pick["status"] == "queued"
    assert pick["wait_reason"].startswith("WAITING_FOR_RESOURCE:")

    resources_available["value"] = True
    assigned = fulfillment.command_order(created["id"], "retry")
    pick = next(task for task in order_tasks(assigned) if task["id"] == pick["id"])
    assert pick["status"] == "running"
    assert pick["resource_id"]


def test_retry_never_bypasses_manual_pause_and_preserves_completed_work(isolated_db):
    clock = isolated_db
    created = fulfillment.command_order(
        fulfillment.create_order(make_order())["id"], "retry"
    )
    pick = next(task for task in order_tasks(created) if task["status"] == "running")
    clock["now"] += timedelta(seconds=45)
    assert fulfillment.run_executor_once(clock["now"]) == 1
    completed = next(
        task for task in order_tasks(fulfillment.get_order(created["id"]))
        if task["id"] == pick["id"]
    )
    assert completed["status"] == "completed"

    # The next staged task is queued after Pick. Mark it as a persona-owned
    # pause; the generic trigger must not convert it back to queued/running.
    with fulfillment.db_transaction() as db:
        next_task = db.execute(
            """SELECT * FROM tasks WHERE order_id=? AND stage!='pick'
               AND status IN ('queued','running') ORDER BY rowid LIMIT 1""",
            (created["id"],),
        ).fetchone()
        db.execute(
            """UPDATE tasks SET status='paused',wait_reason='MANUAL_RECOVERY'
               WHERE id=?""",
            (next_task["id"],),
        )
        db.execute(
            """INSERT INTO persona_task_pauses(
                 task_id,remaining_seconds,resource_id,reason,intervention_id,paused_at)
               VALUES (?,?,?,?,?,?)""",
            (
                next_task["id"], 45, next_task["resource_id"], "manual recovery",
                "INT-MANUAL",
                fulfillment.iso(clock["now"]),
            ),
        )
    result = fulfillment.command_order(created["id"], "retry")
    by_id = {task["id"]: task for task in order_tasks(result)}
    assert by_id[pick["id"]]["status"] == "completed"
    assert by_id[next_task["id"]]["status"] == "paused"


def test_retry_trigger_rolls_back_inventory_and_tasks_together(
    isolated_db, monkeypatch
):
    stock_owner = fulfillment.create_order(make_order(quantity=180))
    held = fulfillment.create_order(make_order(quantity=20))
    fulfillment.command_order(stock_owner["id"], "cancel")
    with fulfillment._read_db() as db:
        inventory_before = [
            tuple(row)
            for row in db.execute(
                """SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,revision
                   FROM inventory_snapshot WHERE warehouse_id='DC-01'
                     AND sku='SKU-01146' ORDER BY id"""
            )
        ]

    def fail_event(*_args, **_kwargs):
        raise RuntimeError("injected planner failure")

    monkeypatch.setattr(fulfillment, "_append_event", fail_event)
    with pytest.raises(RuntimeError, match="injected planner failure"):
        fulfillment.command_order(held["id"], "retry")

    with fulfillment._read_db() as db:
        inventory_after = [
            tuple(row)
            for row in db.execute(
                """SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,revision
                   FROM inventory_snapshot WHERE warehouse_id='DC-01'
                     AND sku='SKU-01146' ORDER BY id"""
            )
        ]
        sub = db.execute(
            "SELECT status FROM sub_orders WHERE order_id=?", (held["id"],)
        ).fetchone()
        assert db.execute(
            "SELECT count(*) FROM tasks WHERE order_id=?", (held["id"],)
        ).fetchone()[0] == 0
        assert db.execute(
            """SELECT count(*) FROM sub_order_allocations
               WHERE sub_order_id IN (
                 SELECT id FROM sub_orders WHERE order_id=?
               )""",
            (held["id"],),
        ).fetchone()[0] == 0
    assert inventory_after == inventory_before
    assert sub["status"] == "held"