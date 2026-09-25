"""Integration coverage uses real evidence and disposable SQLite backup copies only."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from replay_merge import DEFAULT_SOURCE, ROOT, connect, merge_replay, rows


@pytest.fixture
def destination(tmp_path):
    path = tmp_path / "fulfillment.sqlite"
    fixture_path = ROOT / ".local/fulfillment.sqlite"
    # After the approved workspace import, its atomic receipt identifies the
    # authentic pre-merge fixture. Never remove imported rows from the live DB
    # or derive an opening fixture by trying to reverse execution.
    with closing(connect(fixture_path)) as live:
        if live.execute("SELECT 1 FROM sqlite_master WHERE name='maintenance_replay_merges'").fetchone():
            receipts = live.execute(
                "SELECT audit_json FROM maintenance_replay_merges ORDER BY applied_at").fetchall()
            if receipts:
                audit = json.loads(receipts[0]["audit_json"])
                fixture_path = Path(audit["backup"])
                assert fixture_path.is_file(), f"Required pre-merge evidence backup is missing: {fixture_path}"
                with closing(connect(fixture_path)) as evidence:
                    assert evidence.execute("SELECT count(*) FROM orders").fetchone()[0] == audit["before_orders"]
    with closing(connect(fixture_path)) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
    return path


def snapshot(path):
    with closing(connect(path)) as db:
        return {r[0]: rows(db, r[0]) for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def test_real_merge_counters_idempotency_and_pending_continuation(destination):
    before = snapshot(destination)
    plan = merge_replay(DEFAULT_SOURCE, destination)
    assert not plan["applied"]
    assert snapshot(destination) == before
    result = merge_replay(DEFAULT_SOURCE, destination, apply=True)
    assert result["after_orders"] == len(before["orders"]) + 7000
    after = snapshot(destination)
    for name in ("config", "resource_lifecycle", "lifecycle_scheduler", "persona_interventions"):
        assert after[name] == before[name]
    assert len(after["tasks"]) == len(before["tasks"]) + 23376
    rejected = {r["id"] for r in after["orders"] if r["status"] == "rejected"}
    assert len(rejected) == 1156
    assert not any(r["order_id"] in rejected for r in after["tasks"])
    pending = [r for r in after["tasks"] if r["status"] == "queued" and r["stage"] == "move"
               and r["order_id"] not in {o["id"] for o in before["orders"]}]
    assert len(pending) == 109
    for task in pending:
        siblings = [t for t in after["tasks"] if t["order_id"] == task["order_id"]]
        assert {t["stage"]: t["status"] for t in siblings} == {
            "pick": "completed", "move": "queued", "pack_feed": "pending", "stage": "pending"}
        assert task["resource_id"] is None
        assert task["wait_reason"] and "Payload capacity" in task["wait_reason"]
    assert merge_replay(DEFAULT_SOURCE, destination, apply=True)["already_applied"]
    assert snapshot(destination) == after
    # Immutable corruption must not be falsely accepted as an idempotent retry.
    with closing(connect(destination, False)) as db:
        db.execute("UPDATE tasks SET payload_kg=payload_kg+1 WHERE id=?", (pending[0]["id"],))
    with pytest.raises(RuntimeError, match="graph differs"):
        merge_replay(DEFAULT_SOURCE, destination, apply=True)


@pytest.mark.parametrize("point", ["after_graph", "before_commit"])
def test_atomic_rollback(destination, point):
    before = snapshot(destination)

    def fail(stage):
        if stage == point:
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        merge_replay(DEFAULT_SOURCE, destination, apply=True, failpoint=fail)
    assert snapshot(destination) == before


def test_bad_stock_fails_without_writes(destination):
    with closing(connect(destination, False)) as db:
        db.execute("UPDATE inventory_snapshot SET wms_qty=wms_qty+1 WHERE id=30")
    before = snapshot(destination)
    with pytest.raises(RuntimeError, match="does not reconcile"):
        merge_replay(DEFAULT_SOURCE, destination, apply=True)
    assert snapshot(destination) == before


def test_exclusive_guard(destination):
    from maintenance_lock import runtime_lock
    with runtime_lock(destination.parent):
        with pytest.raises(RuntimeError, match="in use"):
            merge_replay(DEFAULT_SOURCE, destination, apply=True)


def test_real_executor_continuation_and_capacity_safety(destination, tmp_path):
    import fulfillment_api
    import fulfillment_v2
    import order_progress

    merge_replay(DEFAULT_SOURCE, destination, apply=True)
    evidence = json.loads((DEFAULT_SOURCE.parent / "effective-sources.json").read_text())["effective"]
    now = datetime.now(timezone.utc)
    with closing(connect(destination, False)) as db:
        picks = [dict(r) for r in db.execute(
            "SELECT * FROM tasks WHERE stage='pick' AND status='completed'")]
        queued = {r["id"] for r in db.execute(
            "SELECT * FROM tasks WHERE stage='move' AND status='queued' AND order_id IN "
            "(SELECT id FROM orders WHERE warehouse_id='DC-14')")}
        assert len(queued) == 109
        duration = fulfillment_v2.task_duration_seconds(db)
        fulfillment_v2.executor_once(db, now, lambda name: tuple(evidence.get(name, ())),
                                    fulfillment_api._append_event, force_assignment=True)
        for task in db.execute("SELECT * FROM tasks WHERE stage='move'"):
            if task["id"] in queued:
                assert task["status"] == "queued"
                assert "Payload capacity is insufficient" in task["wait_reason"]
        # Test-only fixture: add genuine evidence with compatible capacity; no
        # safety predicates or production fleet rows are changed.
        robot = dict(robot_id="TEST-CAPABLE-MOVER", warehouse_id="DC-14", robot_type="AMR",
                     battery_soc="100", health_status="HEALTHY", payload_kg="100000",
                     safety_cert_status="VALID", calibration_status="VALID", connectivity="ONLINE")
        supplied = {key: list(value) for key, value in evidence.items()}
        supplied["robots"].append(robot)
        supplied["maintenance"].append(dict(robot_id=robot["robot_id"], warehouse_id="DC-14",
                                             cmms_status="CLOSED", fleet_availability="AVAILABLE"))
        fulfillment_v2.executor_once(db, now + timedelta(seconds=1),
                                    lambda name: tuple(supplied.get(name, ())),
                                    fulfillment_api._append_event, force_assignment=True)
        running = db.execute("SELECT * FROM tasks WHERE resource_id=? AND status='running'",
                             (robot["robot_id"],)).fetchone()
        assert running and running["id"] in queued and running["stage"] == "move"
        assert running["duration_seconds"] == duration
        assert running["started_at"] == fulfillment_api.iso(now + timedelta(seconds=1))
        fulfillment_v2.executor_once(db, now + timedelta(seconds=duration + 2),
                                    lambda name: tuple(supplied.get(name, ())),
                                    fulfillment_api._append_event, force_assignment=True)
        assert db.execute("SELECT status FROM tasks WHERE id=?", (running["id"],)).fetchone()[0] == "completed"
        assert [dict(r) for r in db.execute(
            "SELECT * FROM tasks WHERE stage='pick' AND status='completed'")] == picks
        order_progress.sync(db, now + timedelta(seconds=duration + 2))
        assert order_progress.export_orders(db, tmp_path / "unified.csv") >= 7000
    assert merge_replay(DEFAULT_SOURCE, destination, apply=True)["already_applied"]