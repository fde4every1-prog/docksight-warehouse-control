import csv
import json
import sqlite3
from datetime import datetime, timezone

import order_progress
import fulfillment_status


NOW = datetime(2030, 1, 1, 1, tzinfo=timezone.utc)


def test_rejected_has_reason_without_accepted_history(tmp_path):
    db = fixture_db()
    db.execute("UPDATE orders SET status='rejected'")
    db.execute("UPDATE sub_orders SET status='rejected',hold_reason='CAPACITY_EXCEEDED'")
    db.execute("DELETE FROM tasks")
    order_progress.sync(db, NOW)
    assert {row[0] for row in db.execute(
        "SELECT fulfillment_status FROM order_fulfillment_history"
    )} == {"Rejected"}
    path = tmp_path / "orders.csv"
    order_progress.export_orders(db, path)
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["fulfillment_status"] == "Rejected" for row in rows)
    assert all(row["hold_reason"] == "CAPACITY_EXCEEDED" for row in rows)


def test_sync_only_reprojects_dirty_orders(monkeypatch):
    db = fixture_db()
    order_progress.sync(db, NOW)
    before = list(map(tuple, db.execute("SELECT * FROM order_fulfillment_progress")))
    calls = []
    original = order_progress._sub_projection

    def record(*args):
        calls.append(args[0]["id"])
        return original(*args)

    monkeypatch.setattr(order_progress, "_sub_projection", record)
    order_progress.sync(db, NOW)
    assert calls == []
    assert list(map(tuple, db.execute("SELECT * FROM order_fulfillment_progress"))) == before
    db.execute("UPDATE tasks SET status='running',started_at='2030-01-01T00:03:00Z' WHERE id='m1'")
    order_progress.sync(db, NOW)
    assert calls == ["s1", "s2"]
    assert db.execute("SELECT count(*) FROM order_progress_dirty").fetchone()[0] == 0


def fixture_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE orders (
          id TEXT PRIMARY KEY, source_order_id TEXT, status TEXT, created_at TEXT,
          order_created_at TEXT, cutoff_at TEXT, ship_by TEXT
        );
        CREATE TABLE sub_orders (
          id TEXT PRIMARY KEY, order_id TEXT, sku TEXT, quantity INTEGER,
          warehouse_id TEXT, status TEXT, hold_reason TEXT, created_at TEXT
        );
        CREATE TABLE tasks (
          id TEXT PRIMARY KEY,order_id TEXT,sub_order_id TEXT,stage TEXT,status TEXT,
          started_at TEXT,completed_at TEXT
        );
        CREATE TABLE inventory_snapshot (
          id INTEGER PRIMARY KEY,warehouse_id TEXT,location TEXT,zone TEXT
        );
        CREATE TABLE sub_order_allocations (
          id TEXT PRIMARY KEY,sub_order_id TEXT,inventory_row_id INTEGER,
          reserved_qty INTEGER,picked_qty INTEGER,completed_qty INTEGER,quantity INTEGER
        );
        INSERT INTO orders VALUES
          ('o1','=source','active','2030-01-01T00:00:00Z',
           '2030-01-01T00:00:00Z','2030-01-02T00:00:00Z','2030-01-02T00:00:00Z');
        INSERT INTO sub_orders VALUES
          ('s1','o1','SKU-1',5,'W1','queued',NULL,'2030-01-01T00:00:00Z'),
          ('s2','o1','SKU-2',2,NULL,'held','INVENTORY_SHORTAGE: SKU-2','2030-01-01T00:00:00Z');
        INSERT INTO inventory_snapshot VALUES
          (1,'W1','L1','Z1'),(2,'W1','L2','Z2');
        INSERT INTO sub_order_allocations VALUES
          ('a1','s1',1,0,3,0,3),('a2','s1',2,0,2,0,2);
        INSERT INTO tasks VALUES
          ('p1','o1','s1','pick','completed','2030-01-01T00:01:00Z','2030-01-01T00:01:45Z'),
          ('p2','o1','s1','pick','completed','2030-01-01T00:02:00Z','2030-01-01T00:02:45Z'),
          ('m1','o1','s1','move','queued',NULL,NULL),
          ('f1','o1','s1','pack_feed','pending',NULL,NULL),
          ('g1','o1','s1','stage','pending',NULL,NULL);
        """
    )
    return db


def test_sync_preserves_fleeting_completion_and_is_idempotent():
    db = fixture_db()
    order_progress.sync(db, NOW)
    order_progress.sync(db, NOW)
    history = list(
        db.execute(
            "SELECT fulfillment_status,at FROM order_fulfillment_history "
            "WHERE sub_order_id='s1' ORDER BY at,id"
        )
    )
    assert ("Pickup Completed", "2030-01-01T00:02:45Z") in map(tuple, history)
    assert ("Awaiting Transfer Task", "2030-01-01T00:02:45Z") in map(tuple, history)
    assert sum(row["fulfillment_status"] == "Pickup Completed" for row in history) == 1
    assert db.execute(
        "SELECT fulfillment_status FROM order_fulfillment_progress "
        "WHERE entity_type='sub_order' AND entity_id='s1'"
    ).fetchone()[0] == "Awaiting Transfer Task"
    # The blocked second SKU keeps the parent conservative.
    assert db.execute(
        "SELECT fulfillment_status FROM order_fulfillment_progress "
        "WHERE entity_type='order' AND entity_id='o1'"
    ).fetchone()[0] == "Order Accepted"


def test_multilocation_pick_not_completed_until_every_pick_finishes():
    db = fixture_db()
    db.execute("UPDATE tasks SET status='running',completed_at=NULL WHERE id='p2'")
    order_progress.sync(db, NOW)
    status = db.execute(
        "SELECT fulfillment_status FROM order_fulfillment_progress "
        "WHERE entity_type='sub_order' AND entity_id='s1'"
    ).fetchone()[0]
    assert status == "Pickup Assigned"
    assert not db.execute(
        "SELECT 1 FROM order_fulfillment_history WHERE sub_order_id='s1' "
        "AND fulfillment_status='Pickup Completed'"
    ).fetchone()


def test_enrich_and_atomic_csv_include_actual_locations_and_held_line(tmp_path):
    db = fixture_db()
    order_progress.sync(db, NOW)
    result = order_progress.enrich_order(
        db,
        {
            "id": "o1",
            "status": "active",
            "sub_orders": [
                {"id": "s1", "warehouse_id": "W1"},
                {"id": "s2", "warehouse_id": None},
            ],
        },
    )
    assert result["warehouses"] == ["W1"]
    assert result["zones"] == ["Z1", "Z2"]
    assert result["sub_orders"][0]["warehouses"] == ["W1"]
    assert result["sub_orders"][0]["zones"] == ["Z1", "Z2"]
    assert any(item["status"] == "Pickup Completed" for item in result["fulfillment_history"])

    target = tmp_path / "exports" / "orders.csv"
    assert order_progress.export_orders(db, target) == 3
    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source_order_id"] == "'=source"
    assert [int(row["quantity"]) for row in rows[:2]] == [3, 2]
    assert {(row["warehouse"], row["zone"]) for row in rows[:2]} == {
        ("W1", "Z1"),
        ("W1", "Z2"),
    }
    held = next(row for row in rows if row["sub_order_id"] == "s2")
    assert held["hold_reason"] == "INVENTORY_SHORTAGE: SKU-2"
    assert held["allocation_id"] == ""


def test_staged_label_in_projection_history_and_export(tmp_path):
    db = fixture_db()
    db.execute(
        "UPDATE tasks SET status='completed',started_at='2030-01-01T00:03:00Z',"
        "completed_at='2030-01-01T00:03:45Z' WHERE completed_at IS NULL"
    )
    order_progress.sync(db, NOW)
    # A held line still prevents the whole order from appearing staged.
    assert db.execute(
        "SELECT fulfillment_status FROM order_fulfillment_progress WHERE entity_id='o1'"
    ).fetchone()[0] == "Order Accepted"
    db.execute("DELETE FROM sub_orders WHERE id='s2'")
    order_progress.sync(db, NOW)
    count = db.execute("SELECT count(*) FROM order_fulfillment_history").fetchone()[0]
    order_progress.sync(db, NOW)
    assert db.execute("SELECT count(*) FROM order_fulfillment_history").fetchone()[0] == count
    result = order_progress.enrich_order(db, {
        "id": "o1", "sub_orders": [{"id": "s1"}],
    })
    assert result["fulfillment_status"] == "Staged - Ready to Ship"
    assert result["sub_orders"][0]["fulfillment_status"] == "Staged - Ready to Ship"
    statuses = {entry["status"] for entry in result["fulfillment_history"]}
    assert {"Pickup Completed", "Transfer Completed", "Packing Completed",
            "Staged - Ready to Ship"} <= statuses
    assert "Staging Completed" not in statuses
    target = tmp_path / "orders.csv"
    order_progress.export_orders(db, target)
    with target.open() as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["fulfillment_status"] == "Staged - Ready to Ship" for row in rows)
    assert all(row["order_fulfillment_status"] == "Staged - Ready to Ship" for row in rows)


def test_historical_migration_is_transactional_and_preserves_metadata():
    db = fixture_db()
    order_progress.ensure_schema(db)
    db.execute("DELETE FROM status_label_migrations")
    db.execute(
        "INSERT INTO order_fulfillment_progress VALUES "
        "('order','o1','o1','Staging Completed','original-update')"
    )
    db.execute(
        "INSERT INTO order_fulfillment_history VALUES "
        "(42,'sub:s1:staging:completed','o1','s1','Staging Completed','original-event')"
    )
    db.commit()
    db.execute("BEGIN")
    order_progress.ensure_schema(db)
    assert db.in_transaction
    db.rollback()
    assert db.execute("SELECT fulfillment_status FROM order_fulfillment_history").fetchone()[0] == "Staging Completed"
    with db:
        order_progress.ensure_schema(db)
    changes = db.total_changes
    order_progress.ensure_schema(db)
    assert db.total_changes == changes
    assert tuple(db.execute("SELECT * FROM order_fulfillment_history").fetchone()) == (
        42, "sub:s1:staging:completed", "o1", "s1", "Staged - Ready to Ship", "original-event",
    )
    assert tuple(db.execute("SELECT * FROM order_fulfillment_progress").fetchone()) == (
        "order", "o1", "o1", "Staged - Ready to Ship", "original-update",
    )


def test_bazaar_snapshot_migration_preserves_narrative_and_timestamps():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE orders (id TEXT,control_tower_sub_orders_json TEXT,updated_at TEXT)")
    snapshot = [{
        "status": "completed", "fulfillment_status": "Staging Completed",
        "note": "Staging Completed",
        "fulfillment_history": [{"status": "Staging Completed", "at": "original-event"}],
    }]
    db.execute("INSERT INTO orders VALUES (?,?,?)", ("o1", json.dumps(snapshot), "original-update"))
    db.commit()
    with db:
        fulfillment_status.migrate_bazaar(db)
    changes = db.total_changes
    fulfillment_status.migrate_bazaar(db)
    assert db.total_changes == changes
    raw, updated = db.execute("SELECT control_tower_sub_orders_json,updated_at FROM orders").fetchone()
    result = json.loads(raw)[0]
    assert result["status"] == "completed"
    assert result["fulfillment_status"] == "Staged - Ready to Ship"
    assert result["note"] == "Staging Completed"
    assert result["fulfillment_history"] == [{"status": "Staged - Ready to Ship", "at": "original-event"}]
    assert updated == "original-update"