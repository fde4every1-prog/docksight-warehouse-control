import sqlite3
from datetime import datetime, timezone

import order_progress


NOW = datetime(2030, 1, 2, tzinfo=timezone.utc)


def _database(order_count):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE orders (
          id TEXT PRIMARY KEY, created_at TEXT, order_created_at TEXT
        );
        CREATE TABLE sub_orders (
          id TEXT PRIMARY KEY, order_id TEXT, created_at TEXT
        );
        CREATE TABLE tasks (
          id TEXT PRIMARY KEY, order_id TEXT, sub_order_id TEXT, stage TEXT,
          status TEXT, started_at TEXT, completed_at TEXT
        );
        """
    )
    for number in range(order_count):
        order_id = f"o{number:03d}"
        active_id = f"{order_id}-active"
        held_id = f"{order_id}-held"
        created = f"2030-01-01T00:{number % 60:02d}:00Z"
        db.execute("INSERT INTO orders VALUES (?,?,?)", (order_id, created, created))
        db.execute(
            "INSERT INTO sub_orders VALUES (?,?,?)", (active_id, order_id, created)
        )
        db.execute(
            "INSERT INTO sub_orders VALUES (?,?,?)", (held_id, order_id, created)
        )
        for phase, stage, minute in (
            ("pick", "pick", 1),
            ("transfer", "move", 2),
            ("packing", "pack_feed", 3),
            ("staging", "stage", 4),
        ):
            db.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?)",
                (
                    f"{active_id}-{phase}",
                    order_id,
                    active_id,
                    stage,
                    "completed",
                    f"2030-01-01T01:{minute:02d}:00Z",
                    f"2030-01-01T01:{minute:02d}:45Z",
                ),
            )
    db.commit()
    return db


def _legacy_sync(db, now):
    """The former per-entity read shape, retained only as a test oracle."""
    order_progress.ensure_schema(db)
    stamp = order_progress._iso(now)
    order_cols = order_progress._columns(db, "orders")
    created_expr = (
        "COALESCE(order_created_at,created_at)"
        if "order_created_at" in order_cols
        else "created_at"
    )
    orders = list(
        db.execute(f"SELECT id,{created_expr} AS progress_created FROM orders")
    )
    for order in orders:
        order_id = str(order["id"])
        created = str(order["progress_created"] or stamp)
        order_progress._insert_history(
            db,
            f"order:{order_id}:accepted",
            order_id,
            None,
            "Order Accepted",
            created,
        )
        statuses = []
        subs = list(
            db.execute(
                "SELECT * FROM sub_orders WHERE order_id=? ORDER BY rowid",
                (order_id,),
            )
        )
        for sub in subs:
            sub_id = str(sub["id"])
            tasks = list(
                db.execute(
                    "SELECT * FROM tasks WHERE sub_order_id=? ORDER BY rowid",
                    (sub_id,),
                )
            )
            status, events = order_progress._sub_projection(sub, tasks, stamp)
            for key, event_status, at in events:
                order_progress._insert_history(
                    db, key, order_id, sub_id, event_status, at
                )
            db.execute(
                """INSERT INTO order_fulfillment_progress
                   (entity_type,entity_id,order_id,fulfillment_status,updated_at)
                   VALUES ('sub_order',?,?,?,?)""",
                (sub_id, order_id, status, stamp),
            )
            statuses.append(status)
        parent = min(statuses, key=lambda value: order_progress.STATUS_RANK[value])
        db.execute(
            """INSERT INTO order_fulfillment_progress
               (entity_type,entity_id,order_id,fulfillment_status,updated_at)
               VALUES ('order',?,?,?,?)""",
            (order_id, order_id, parent, stamp),
        )


def _source_reads(db, operation):
    statements = []
    db.set_trace_callback(statements.append)
    try:
        operation()
    finally:
        db.set_trace_callback(None)
    normalized = [" ".join(statement.lower().split()) for statement in statements]
    return (
        sum("select * from sub_orders" in statement for statement in normalized),
        sum("select * from tasks" in statement for statement in normalized),
    )


def _projection_snapshot(db):
    progress = [
        tuple(row)
        for row in db.execute(
            "SELECT * FROM order_fulfillment_progress "
            "ORDER BY entity_type,entity_id"
        )
    ]
    history = [
        tuple(row)
        for row in db.execute(
            "SELECT transition_key,order_id,sub_order_id,fulfillment_status,at "
            "FROM order_fulfillment_history ORDER BY id"
        )
    ]
    return progress, history


def test_sync_batches_source_reads_and_matches_prior_semantics():
    single = _database(1)
    many = _database(24)
    reference = _database(24)

    assert _source_reads(single, lambda: order_progress.sync(single, NOW)) == (1, 1)
    assert _source_reads(many, lambda: order_progress.sync(many, NOW)) == (1, 1)
    assert _source_reads(reference, lambda: _legacy_sync(reference, NOW)) == (24, 48)
    assert _projection_snapshot(many) == _projection_snapshot(reference)

    before = _projection_snapshot(many)
    assert _source_reads(many, lambda: order_progress.sync(many, NOW)) == (1, 1)
    assert _projection_snapshot(many) == before

    statuses = {
        row["fulfillment_status"]
        for row in many.execute(
            "SELECT fulfillment_status FROM order_fulfillment_history"
        )
    }
    assert "Staged - Ready to Ship" in statuses
    assert "Staging Completed" not in statuses
    assert many.execute(
        "SELECT fulfillment_status FROM order_fulfillment_progress "
        "WHERE entity_type='order' AND entity_id='o000'"
    ).fetchone()[0] == "Order Accepted"
    assert many.execute(
        "SELECT at FROM order_fulfillment_history "
        "WHERE transition_key='sub:o000-active:staging:completed'"
    ).fetchone()[0] == "2030-01-01T01:04:45Z"


def test_sync_leaves_commit_and_rollback_to_caller():
    db = _database(2)
    order_progress.ensure_schema(db)
    db.commit()

    db.execute("BEGIN")
    order_progress.sync(db, NOW)
    assert db.in_transaction
    db.rollback()

    assert db.execute("SELECT count(*) FROM order_fulfillment_progress").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM order_fulfillment_history").fetchone()[0] == 0