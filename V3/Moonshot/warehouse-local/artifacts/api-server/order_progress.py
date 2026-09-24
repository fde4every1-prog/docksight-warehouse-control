"""Durable order progress projection and application-owned CSV export.

This module is intentionally independent of the HTTP application.  Callers own
the SQLite transaction used by ``ensure_schema`` and ``sync`` and should run an
export only after that transaction commits.
"""

from __future__ import annotations

import csv
import portable_lock as fcntl
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fulfillment_status import STAGED_READY, migrate_progress


PHASES = (
    ("pick", "Pickup"),
    ("transfer", "Transfer"),
    ("packing", "Packing"),
    ("staging", "Staging"),
)
STAGE_PHASE = {
    "pick": "pick",
    "pickup": "pick",
    "move": "transfer",
    "transfer": "transfer",
    "pack": "packing",
    "pack_feed": "packing",
    "packing": "packing",
    "stage": "staging",
    "staging": "staging",
    "dispatch": "staging",
}
STATUS_RANK = {
    "Order Accepted": 0,
    **{
        status: rank
        for rank, status in enumerate(
            (
                "Awaiting Pickup Task",
                "Pickup Assigned",
                "Pickup Completed",
                "Awaiting Transfer Task",
                "Transfer Assigned",
                "Transfer Completed",
                "Awaiting Packing Task",
                "Packing Assigned",
                "Packing Completed",
                "Awaiting Staging Task",
                "Staging Assigned",
                STAGED_READY,
            ),
            1,
        )
    },
}
CSV_FIELDS = (
    "order_id",
    "source_order_id",
    "sub_order_id",
    "allocation_id",
    "sku",
    "quantity",
    "warehouse",
    "zone",
    "public_order_status",
    "public_sub_order_status",
    "fulfillment_status",
    "order_fulfillment_status",
    "order_created_at",
    "deadline",
    "hold_reason",
    "reserved_quantity",
    "picked_quantity",
    "completed_quantity",
)


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}


def _has_table(db: sqlite3.Connection, table: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_schema(db: sqlite3.Connection) -> None:
    """Create the additive progress projection without committing the caller."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS order_fulfillment_progress (
             entity_type TEXT NOT NULL CHECK(entity_type IN ('order','sub_order')),
             entity_id TEXT NOT NULL,
             order_id TEXT NOT NULL,
             fulfillment_status TEXT NOT NULL,
             updated_at TEXT NOT NULL,
             PRIMARY KEY(entity_type,entity_id)
           )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS order_fulfillment_history (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             transition_key TEXT NOT NULL UNIQUE,
             order_id TEXT NOT NULL,
             sub_order_id TEXT,
             fulfillment_status TEXT NOT NULL,
             at TEXT NOT NULL
           )"""
    )
    db.execute(
        """CREATE INDEX IF NOT EXISTS order_fulfillment_history_order
           ON order_fulfillment_history(order_id,at,id)"""
    )
    migrate_progress(db)
    # Durable invalidation avoids rereading immutable completed task history on
    # every executor tick. Triggers also cover imports and external writers.
    first_install = not _has_table(db, "order_progress_dirty")
    db.execute("CREATE TABLE IF NOT EXISTS order_progress_dirty (order_id TEXT PRIMARY KEY)")
    db.execute("CREATE TABLE IF NOT EXISTS order_export_dirty (id INTEGER PRIMARY KEY CHECK(id=1))")
    db.execute("""CREATE TRIGGER IF NOT EXISTS progress_export_dirty
                  AFTER INSERT ON order_progress_dirty BEGIN
                  INSERT OR IGNORE INTO order_export_dirty VALUES (1); END""")
    if first_install and _has_table(db, "orders"):
        db.execute("INSERT OR IGNORE INTO order_progress_dirty SELECT id FROM orders")
    for table in ("orders", "sub_orders", "tasks"):
        if not _has_table(db, table):
            continue
        key = "id" if table == "orders" else "order_id"
        for action in ("INSERT", "UPDATE", "DELETE"):
            refs = ("OLD", "NEW") if action == "UPDATE" else (("OLD",) if action == "DELETE" else ("NEW",))
            statements = " ".join(
                f"INSERT OR IGNORE INTO order_progress_dirty VALUES ({ref}.{key});"
                for ref in refs
            )
            db.execute(
                f"CREATE TRIGGER IF NOT EXISTS progress_dirty_{table}_{action.lower()} "
                f"AFTER {action} ON {table} BEGIN {statements} END"
            )
        if table != "orders":
            db.execute(f"CREATE INDEX IF NOT EXISTS progress_{table}_order ON {table}(order_id)")


def _insert_history(
    db: sqlite3.Connection,
    key: str,
    order_id: str,
    sub_order_id: str | None,
    status: str,
    at: str,
) -> None:
    db.execute(
        """INSERT OR IGNORE INTO order_fulfillment_history
           (transition_key,order_id,sub_order_id,fulfillment_status,at)
           VALUES (?,?,?,?,?)""",
        (key, order_id, sub_order_id, status, at),
    )


def _task_phase(task: sqlite3.Row) -> str | None:
    return STAGE_PHASE.get(str(task["stage"] or "").strip().lower())


def _sub_projection(
    sub: sqlite3.Row, tasks: list[sqlite3.Row], now_stamp: str
) -> tuple[str, list[tuple[str, str, str]]]:
    sub_id = str(sub["id"])
    created = str(sub["created_at"] or now_stamp)
    if str(sub["status"]).lower() == "rejected":
        return "Rejected", [(f"sub:{sub_id}:rejected", "Rejected", created)]
    events: list[tuple[str, str, str]] = [
        (f"sub:{sub_id}:accepted", "Order Accepted", created)
    ]
    if not tasks:
        return "Order Accepted", events

    grouped: dict[str, list[sqlite3.Row]] = {phase: [] for phase, _ in PHASES}
    for task in tasks:
        phase = _task_phase(task)
        if phase:
            grouped[phase].append(task)

    waiting_at = created
    current = "Order Accepted"
    for phase, label in PHASES:
        phase_tasks = grouped[phase]
        if not phase_tasks:
            # A created task chain can be observed early, before downstream
            # tasks are materialized. Do not claim a later phase completed.
            if any(grouped[p] for p, _ in PHASES[PHASES.index((phase, label)) + 1 :]):
                continue
            return current, events

        awaiting = f"Awaiting {label} Task"
        events.append((f"sub:{sub_id}:{phase}:awaiting:{waiting_at}", awaiting, waiting_at))
        current = awaiting

        for task in phase_tasks:
            if task["started_at"]:
                assigned = f"{label} Assigned"
                started = str(task["started_at"])
                events.append(
                    (f"task:{task['id']}:assigned:{started}", assigned, started)
                )

        unfinished = [task for task in phase_tasks if task["status"] != "completed"]
        if unfinished:
            running = [task for task in unfinished if task["status"] == "running"]
            if running:
                current = f"{label} Assigned"
            return current, events

        completion_times = [str(task["completed_at"]) for task in phase_tasks if task["completed_at"]]
        # A completed durable task without its completion time is malformed
        # evidence; retain the preceding state rather than inventing a time.
        if len(completion_times) != len(phase_tasks):
            return current, events
        completed_at = max(completion_times)
        completed = STAGED_READY if phase == "staging" else f"{label} Completed"
        events.append((f"sub:{sub_id}:{phase}:completed", completed, completed_at))
        current = completed
        waiting_at = completed_at

    return current, events


def sync(db: sqlite3.Connection, now: datetime) -> None:
    """Synchronize current progress and idempotent history from durable tasks."""
    ensure_schema(db)
    stamp = _iso(now)
    if not _has_table(db, "orders"):
        return
    order_cols = _columns(db, "orders")
    created_expr = "COALESCE(order_created_at,created_at)" if "order_created_at" in order_cols else "created_at"
    orders = list(db.execute(
        f"SELECT id,status,{created_expr} AS progress_created FROM orders "
        "WHERE id IN (SELECT order_id FROM order_progress_dirty)"
    ))
    has_subs = _has_table(db, "sub_orders") and _has_table(db, "tasks")
    subs_by_order: dict[str, list[sqlite3.Row]] = {}
    tasks_by_sub: dict[str, list[sqlite3.Row]] = {}
    if has_subs:
        for sub in db.execute("SELECT * FROM sub_orders WHERE order_id IN (SELECT order_id FROM order_progress_dirty) ORDER BY rowid"):
            subs_by_order.setdefault(str(sub["order_id"]), []).append(sub)
        for task in db.execute("SELECT * FROM tasks WHERE order_id IN (SELECT order_id FROM order_progress_dirty) ORDER BY rowid"):
            sub_id = task["sub_order_id"]
            if sub_id is not None:
                tasks_by_sub.setdefault(str(sub_id), []).append(task)

    for order in orders:
        order_id = str(order["id"])
        created = str(order["progress_created"] or stamp)
        rejected = str(order["status"]).lower() == "rejected"
        initial = "Rejected" if rejected else "Order Accepted"
        _insert_history(db, f"order:{order_id}:{'rejected' if rejected else 'accepted'}", order_id, None, initial, created)
        sub_statuses: list[str] = []
        if has_subs:
            for sub in subs_by_order.get(order_id, ()):
                sub_id = str(sub["id"])
                status, events = _sub_projection(
                    sub, tasks_by_sub.get(sub_id, []), stamp
                )
                for key, event_status, at in events:
                    _insert_history(db, key, order_id, sub_id, event_status, at)
                db.execute(
                    """INSERT INTO order_fulfillment_progress
                       (entity_type,entity_id,order_id,fulfillment_status,updated_at)
                       VALUES ('sub_order',?,?,?,?)
                       ON CONFLICT(entity_type,entity_id) DO UPDATE SET
                         order_id=excluded.order_id,
                         fulfillment_status=excluded.fulfillment_status,
                         updated_at=excluded.updated_at""",
                    (sub_id, order_id, status, stamp),
                )
                sub_statuses.append(status)

        # The parent is deliberately the least advanced required line. This
        # keeps partial/held multi-SKU orders from appearing complete.
        parent_status = (
            min(sub_statuses, key=lambda value: STATUS_RANK.get(value, -1))
            if sub_statuses
            else "Order Accepted"
        )
        if rejected:
            parent_status = "Rejected"
        db.execute(
            """INSERT INTO order_fulfillment_progress
               (entity_type,entity_id,order_id,fulfillment_status,updated_at)
               VALUES ('order',?,?,?,?)
               ON CONFLICT(entity_type,entity_id) DO UPDATE SET
                 fulfillment_status=excluded.fulfillment_status,
                 updated_at=excluded.updated_at""",
            (order_id, order_id, parent_status, stamp),
        )
    db.execute("DELETE FROM order_progress_dirty")


def enrich_order(db: sqlite3.Connection, result: dict[str, Any]) -> dict[str, Any]:
    """Add persisted progress and actual allocation locations to an order JSON."""
    enriched = dict(result)
    order_id = str(enriched["id"])
    progress = db.execute(
        """SELECT fulfillment_status FROM order_fulfillment_progress
           WHERE entity_type='order' AND entity_id=?""",
        (order_id,),
    ).fetchone()
    enriched["fulfillment_status"] = (
        "Rejected" if enriched.get("status") == "rejected"
        else progress["fulfillment_status"] if progress else "Order Accepted"
    )
    enriched["hold_reason"] = "; ".join(dict.fromkeys(
        sub["hold_reason"] for sub in enriched.get("sub_orders", [])
        if sub.get("hold_reason")
    )) or None
    enriched["fulfillment_history"] = [
        {
            "status": row["fulfillment_status"],
            "at": row["at"],
            **({"sub_order_id": row["sub_order_id"]} if row["sub_order_id"] else {}),
        }
        for row in db.execute(
            """SELECT fulfillment_status,at,sub_order_id
               FROM order_fulfillment_history
               WHERE order_id=? ORDER BY at,id""",
            (order_id,),
        )
    ]

    warehouses: set[str] = set()
    zones: set[str] = set()
    subs_out: list[dict[str, Any]] = []
    for supplied in enriched.get("sub_orders") or []:
        sub = dict(supplied)
        sub_id = str(sub["id"])
        row = db.execute(
            """SELECT fulfillment_status FROM order_fulfillment_progress
               WHERE entity_type='sub_order' AND entity_id=?""",
            (sub_id,),
        ).fetchone()
        sub["fulfillment_status"] = (
            "Rejected" if sub.get("status") == "rejected"
            else row["fulfillment_status"] if row else "Order Accepted"
        )
        allocations = [
            dict(item)
            for item in db.execute(
                """SELECT a.*,i.warehouse_id,i.location,i.zone
                   FROM sub_order_allocations a
                   JOIN inventory_snapshot i ON i.id=a.inventory_row_id
                   WHERE a.sub_order_id=? ORDER BY i.warehouse_id,i.location,a.id""",
                (sub_id,),
            )
        ]
        if allocations:
            sub["allocations"] = allocations
        sub_warehouses = sorted(
            {str(item["warehouse_id"]) for item in allocations if item["warehouse_id"]}
            or ({str(sub["warehouse_id"])} if sub.get("warehouse_id") else set())
        )
        sub_zones = sorted({str(item["zone"]) for item in allocations if item["zone"]})
        sub["warehouses"] = sub_warehouses
        sub["zones"] = sub_zones
        warehouses.update(sub_warehouses)
        zones.update(sub_zones)
        subs_out.append(sub)
    if "sub_orders" in enriched:
        enriched["sub_orders"] = subs_out
    enriched["warehouses"] = sorted(warehouses)
    enriched["zones"] = sorted(zones)
    return enriched


def _safe_csv(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def export_orders(db: sqlite3.Connection, path: Path) -> int:
    """Serialize snapshot-and-replace across workers, including downloads."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".csv.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return _export_orders_locked(db, path)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _export_orders_locked(db: sqlite3.Connection, path: Path) -> int:
    """Atomically regenerate an application-owned CSV from authoritative SQLite."""
    ensure_schema(db)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    order_cols = _columns(db, "orders")
    source_expr = "o.source_order_id" if "source_order_id" in order_cols else "NULL"
    created_expr = (
        "COALESCE(o.order_created_at,o.created_at)"
        if "order_created_at" in order_cols
        else "o.created_at"
    )
    deadline_expr = (
        "COALESCE(o.cutoff_at,o.ship_by)" if "cutoff_at" in order_cols else "o.ship_by"
    )
    rows = list(
        db.execute(
            f"""SELECT o.id AS order_id,{source_expr} AS source_order_id,
                       o.status AS public_order_status,{created_expr} AS order_created_at,
                       {deadline_expr} AS deadline,
                       s.id AS sub_order_id,s.sku,COALESCE(a.quantity,s.quantity) AS quantity,s.warehouse_id,
                       s.status AS public_sub_order_status,s.hold_reason,
                       a.id AS allocation_id,a.reserved_qty,a.picked_qty,a.completed_qty,
                       i.warehouse_id AS allocation_warehouse,i.zone,
                       sp.fulfillment_status,
                       op.fulfillment_status AS order_fulfillment_status
                FROM orders o
                LEFT JOIN sub_orders s ON s.order_id=o.id
                LEFT JOIN sub_order_allocations a ON a.sub_order_id=s.id
                LEFT JOIN inventory_snapshot i ON i.id=a.inventory_row_id
                LEFT JOIN order_fulfillment_progress sp
                  ON sp.entity_type='sub_order' AND sp.entity_id=s.id
                LEFT JOIN order_fulfillment_progress op
                  ON op.entity_type='order' AND op.entity_id=o.id
                ORDER BY o.created_at,o.id,s.rowid,i.warehouse_id,i.location,a.id"""
        )
    )
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: _safe_csv(value)
                        for key, value in {
                            "order_id": row["order_id"],
                            "source_order_id": row["source_order_id"],
                            "sub_order_id": row["sub_order_id"],
                            "allocation_id": row["allocation_id"],
                            "sku": row["sku"],
                            "quantity": row["quantity"],
                            "warehouse": row["allocation_warehouse"] or row["warehouse_id"],
                            "zone": row["zone"],
                            "public_order_status": row["public_order_status"],
                            "public_sub_order_status": row["public_sub_order_status"],
                            "fulfillment_status": "Rejected" if row["public_sub_order_status"] == "rejected" else row["fulfillment_status"] or "Order Accepted",
                            "order_fulfillment_status": "Rejected" if row["public_order_status"] == "rejected" else row["order_fulfillment_status"] or "Order Accepted",
                            "order_created_at": row["order_created_at"],
                            "deadline": row["deadline"],
                            "hold_reason": row["hold_reason"],
                            "reserved_quantity": row["reserved_qty"],
                            "picked_quantity": row["picked_qty"],
                            "completed_quantity": row["completed_qty"],
                        }.items()
                    }
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return len(rows)