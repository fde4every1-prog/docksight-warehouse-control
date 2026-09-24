"""Public status labels and transaction-owned historical label migrations."""

import json
import sqlite3


STAGED_READY = "Staged - Ready to Ship"
LEGACY_STAGED = "Staging Completed"


def _pending(db: sqlite3.Connection, name: str) -> bool:
    db.execute(
        "CREATE TABLE IF NOT EXISTS status_label_migrations (name TEXT PRIMARY KEY)"
    )
    return db.execute(
        "SELECT 1 FROM status_label_migrations WHERE name=?", (name,)
    ).fetchone() is None


def migrate_progress(db: sqlite3.Connection) -> None:
    """Rename only labels, preserving event identity and all timestamps."""
    name = "staged_ready_progress"
    if not _pending(db, name):
        return
    for table in ("order_fulfillment_progress", "order_fulfillment_history"):
        db.execute(
            f"UPDATE {table} SET fulfillment_status=? WHERE fulfillment_status=?",
            (STAGED_READY, LEGACY_STAGED),
        )
    db.execute("INSERT INTO status_label_migrations VALUES (?)", (name,))


def _rename_snapshot(value):
    if isinstance(value, list):
        return [_rename_snapshot(item) for item in value]
    if isinstance(value, dict):
        return {
            key: STAGED_READY
            if key in {"status", "fulfillment_status"} and item == LEGACY_STAGED
            else _rename_snapshot(item)
            for key, item in value.items()
        }
    return value


def migrate_bazaar(db: sqlite3.Connection) -> None:
    """Update cached sub-order statuses, not arbitrary snapshot narrative."""
    name = "staged_ready_bazaar"
    if not _pending(db, name):
        return
    rows = db.execute(
        "SELECT id,control_tower_sub_orders_json FROM orders "
        "WHERE instr(control_tower_sub_orders_json,?)>0", (LEGACY_STAGED,)
    ).fetchall()
    for order_id, raw in rows:
        before = json.loads(raw)
        after = _rename_snapshot(before)
        if after != before:
            db.execute(
                "UPDATE orders SET control_tower_sub_orders_json=? WHERE id=?",
                (json.dumps(after), order_id),
            )
    db.execute("INSERT INTO status_label_migrations VALUES (?)", (name,))