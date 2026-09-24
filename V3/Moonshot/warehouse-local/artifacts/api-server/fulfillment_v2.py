"""Additive policy-v2 fulfillment domain.

The module is deliberately host-agnostic: ``fulfillment_api`` supplies source
rows and clock helpers.  All mutations use the caller's SQLite transaction.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from fleet_readiness import asset_readiness, robot_readiness
import robot_lifecycle

SERVICES = {"Same_Day": 6, "Next_Day": 12, "Standard": 24}
STAGES = ("pick", "move", "pack_feed", "stage")
ROBOT_TYPES = {
    "pick": {"AGV", "AMR", "CASE_PICKER", "FORK_AMR"},
    "move": {"AGV", "AMR", "FORK_AMR", "PALLET_MOVER", "TUGGER"},
}
ASSET_TYPES = {
    "pack_feed": {"CONVEYOR", "SORTER", "PACK_STATION"},
    "stage": {"CONVEYOR", "DOCK_DOOR", "VISION_GATE"},
}
DEFAULT_TASK_DURATION_SECONDS = 45


def task_duration_seconds(db: sqlite3.Connection) -> int:
    """Return the persisted shared duration, tolerating pre-setting databases."""

    try:
        row = db.execute(
            "SELECT value FROM config WHERE key='task_duration_seconds'"
        ).fetchone()
        value = int(row[0]) if row is not None else DEFAULT_TASK_DURATION_SECONDS
    except (sqlite3.OperationalError, TypeError, ValueError):
        return DEFAULT_TASK_DURATION_SECONDS
    return value if 1 <= value <= 86_400 else DEFAULT_TASK_DURATION_SECONDS


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _i(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _f(value: Any) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _execute_ddl(db: sqlite3.Connection, script: str) -> None:
    """Execute schema statements without SQLite's implicit-commit executescript."""
    for statement in script.split(";"):
        if statement.strip():
            db.execute(statement)


def ensure_schema(
    db: sqlite3.Connection,
    source_inventory: tuple[dict[str, Any], ...],
    now: datetime,
) -> None:
    """Create v2 structures and convert the immutable opening snapshot once."""
    db.execute("""CREATE TABLE IF NOT EXISTS task_recovery_preferences (
        task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
        resource_id TEXT NOT NULL, resource_type TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    # Avoid executescript (which commits implicitly) when called through the
    # public helper from an already active transaction.
    existing = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('inventory_snapshot','sub_orders','inventory_movements','legacy_inventory_allocations')"
        )
    }
    schema_tables_ready = existing == {
        "inventory_snapshot", "sub_orders", "inventory_movements",
        "legacy_inventory_allocations",
    }
    order_columns = _columns(db, "orders")
    task_columns = _columns(db, "tasks")
    movement_columns = _columns(db, "inventory_movements")
    if (
        schema_tables_ready
        and {"policy_version", "cutoff_at", "order_created_at"} <= order_columns
        and {"sub_order_id", "allocation_id", "duration_seconds", "payload_kg", "wait_reason"} <= task_columns
        and {"before_json", "after_json"} <= movement_columns
    ):
        return
    _execute_ddl(
        db,
        """
        CREATE TABLE IF NOT EXISTS inventory_snapshot (
          id INTEGER PRIMARY KEY,
          source_row_index INTEGER NOT NULL UNIQUE,
          warehouse_id TEXT NOT NULL, sku TEXT NOT NULL, location TEXT NOT NULL,
          zone TEXT NOT NULL, inventory_status TEXT NOT NULL,
          wms_qty INTEGER NOT NULL CHECK(wms_qty>=0),
          erp_qty INTEGER NOT NULL CHECK(erp_qty>=0),
          vision_qty INTEGER NOT NULL CHECK(vision_qty>=0),
          reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK(reserved_qty>=0),
          external_reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK(external_reserved_qty>=0),
          picked_qty INTEGER NOT NULL DEFAULT 0 CHECK(picked_qty>=0),
          completed_qty INTEGER NOT NULL DEFAULT 0 CHECK(completed_qty>=0),
          weight_kg REAL,
          revision INTEGER NOT NULL DEFAULT 0,
          opening_discrepancy TEXT,
          blocked_allocation INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS inventory_v2_stock
          ON inventory_snapshot(warehouse_id,sku,inventory_status);
        CREATE TABLE IF NOT EXISTS sub_orders (
          id TEXT PRIMARY KEY, order_id TEXT NOT NULL, sku TEXT NOT NULL,
          quantity INTEGER NOT NULL CHECK(quantity>0), warehouse_id TEXT,
          status TEXT NOT NULL, hold_reason TEXT, cutoff_at TEXT NOT NULL,
          created_at TEXT NOT NULL, completed_at TEXT, cancelled_at TEXT,
          UNIQUE(order_id,sku), FOREIGN KEY(order_id) REFERENCES orders(id)
        );
        CREATE INDEX IF NOT EXISTS sub_order_queue
          ON sub_orders(status,cutoff_at,id);
        CREATE TABLE IF NOT EXISTS sub_order_allocations (
          id TEXT PRIMARY KEY, sub_order_id TEXT NOT NULL,
          inventory_row_id INTEGER NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0),
          reserved_qty INTEGER NOT NULL CHECK(reserved_qty>=0),
          picked_qty INTEGER NOT NULL DEFAULT 0 CHECK(picked_qty>=0),
          completed_qty INTEGER NOT NULL DEFAULT 0 CHECK(completed_qty>=0),
          wip_stage TEXT, UNIQUE(sub_order_id,inventory_row_id),
          FOREIGN KEY(sub_order_id) REFERENCES sub_orders(id),
          FOREIGN KEY(inventory_row_id) REFERENCES inventory_snapshot(id)
        );
        CREATE TABLE IF NOT EXISTS inventory_movements (
          id TEXT PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
          order_id TEXT NOT NULL, sub_order_id TEXT,
          inventory_row_id INTEGER NOT NULL, movement_type TEXT NOT NULL,
          quantity INTEGER NOT NULL CHECK(quantity>0),
          wms_delta INTEGER NOT NULL DEFAULT 0,
          erp_delta INTEGER NOT NULL DEFAULT 0,
          vision_delta INTEGER NOT NULL DEFAULT 0,
          reserved_delta INTEGER NOT NULL DEFAULT 0,
          picked_delta INTEGER NOT NULL DEFAULT 0,
          completed_delta INTEGER NOT NULL DEFAULT 0,
          wip_stage TEXT, at TEXT NOT NULL, reason TEXT, actor TEXT NOT NULL,
          before_json TEXT, after_json TEXT
        );
        CREATE TABLE IF NOT EXISTS inventory_corrections (
          id TEXT PRIMARY KEY, inventory_row_id INTEGER NOT NULL,
          before_json TEXT NOT NULL, after_json TEXT NOT NULL,
          basis TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL,
          at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS legacy_inventory_allocations (
          reservation_id TEXT NOT NULL, inventory_row_id INTEGER NOT NULL,
          quantity INTEGER NOT NULL CHECK(quantity>0),
          reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK(reserved_qty>=0),
          picked_qty INTEGER NOT NULL DEFAULT 0 CHECK(picked_qty>=0),
          completed_qty INTEGER NOT NULL DEFAULT 0 CHECK(completed_qty>=0),
          PRIMARY KEY(reservation_id,inventory_row_id)
        );
        """,
    )
    order_cols = _columns(db, "orders")
    additions = {
        "policy_version": "INTEGER NOT NULL DEFAULT 1",
        "cutoff_at": "TEXT",
        "order_created_at": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in order_cols:
            db.execute(f"ALTER TABLE orders ADD COLUMN {name} {ddl}")
    task_cols = _columns(db, "tasks")
    for name, ddl in {
        "sub_order_id": "TEXT",
        "allocation_id": "TEXT",
        "duration_seconds": "INTEGER NOT NULL DEFAULT 45",
        "payload_kg": "REAL",
        "wait_reason": "TEXT",
    }.items():
        if name not in task_cols:
            db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}")
    movement_cols = _columns(db, "inventory_movements")
    for name in ("before_json", "after_json"):
        if name not in movement_cols:
            db.execute(f"ALTER TABLE inventory_movements ADD COLUMN {name} TEXT")

    if db.execute("SELECT 1 FROM inventory_snapshot LIMIT 1").fetchone():
        return
    stamp = _iso(now)
    for index, row in enumerate(source_inventory):
        external = max(0, _i(row.get("reserved_qty")))
        source = [_i(row.get(name)) for name in ("wms_qty", "erp_qty", "vision_qty")]
        free = [max(0, value - external) for value in source]
        discrepancy = None
        blocked = 0
        if external > min(source):
            discrepancy = (
                f"Opening external reservation {external} exceeds at least one "
                f"source observation ({source[0]}/{source[1]}/{source[2]})"
            )
            blocked = 1
        location = str(row.get("location") or f"ROW-{index}")
        zone = location.rsplit("-", 1)[0] if "-" in location else ""
        weight = _f(row.get("weight_kg"))
        db.execute(
            """INSERT INTO inventory_snapshot(
              source_row_index,warehouse_id,sku,location,zone,inventory_status,
              wms_qty,erp_qty,vision_qty,reserved_qty,external_reserved_qty,
              weight_kg,opening_discrepancy,blocked_allocation,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                index, str(row.get("warehouse_id") or ""), str(row.get("sku") or ""),
                location, zone, str(row.get("inventory_status") or ""),
                free[0], free[1], free[2], external, external,
                weight if math.isfinite(weight) and weight > 0 else None,
                discrepancy, blocked, stamp, stamp,
            ),
        )


def inventory_rows(
    db: sqlite3.Connection,
    warehouse_id: str | None = None,
    sku: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if warehouse_id:
        clauses.append("warehouse_id=?")
        params.append(warehouse_id)
    if sku:
        clauses.append("sku=?")
        params.append(sku)
    sql = "SELECT * FROM inventory_snapshot"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY warehouse_id,sku,location,id"
    result = []
    for row in db.execute(sql, params):
        item = dict(row)
        item["inventory_row_id"] = item.pop("id")
        item["allocatable_qty"] = (
            0
            if item["inventory_status"] != "AVAILABLE" or item["blocked_allocation"]
            else max(0, min(item["wms_qty"], item["erp_qty"], item["vision_qty"]))
        )
        result.append(item)
    return result


def cutoff(service: str, created_at: datetime) -> datetime:
    if service not in SERVICES:
        raise HTTPException(422, "order_service must be Same_Day, Next_Day, or Standard")
    return created_at + timedelta(hours=SERVICES[service])


def request_fingerprint(payload: Any, created_at: str) -> str:
    canonical = {
        "warehouse_id": payload.warehouse_id,
        "priority": payload.priority,
        "ship_by": payload.ship_by,
        "lines": sorted(
            ({"sku": line.sku, "quantity": line.quantity} for line in payload.lines),
            key=lambda item: item["sku"],
        ),
        "source_order_id": payload.source_order_id,
        "order_service": payload.order_service,
        "order_source": payload.order_source,
        "order_created_at": created_at,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _movement(
    db: sqlite3.Connection,
    *,
    event_key: str,
    order_id: str,
    sub_order_id: str,
    row_id: int,
    kind: str,
    quantity: int,
    at: str,
    actor: str = "fulfillment-v2",
    reason: str = "",
    wms: int = 0,
    erp: int = 0,
    vision: int = 0,
    reserved: int = 0,
    picked: int = 0,
    completed: int = 0,
    wip_stage: str | None = None,
    state_is_after: bool = False,
) -> bool:
    state = db.execute(
        """SELECT wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty,completed_qty
           FROM inventory_snapshot WHERE id=?""",
        (row_id,),
    ).fetchone()
    deltas = {
        "wms_qty": wms, "erp_qty": erp, "vision_qty": vision,
        "reserved_qty": reserved, "picked_qty": picked,
        "completed_qty": completed,
    }
    current = dict(state) if state else {}
    if state_is_after:
        after = current
        before = {field: current[field] - delta for field, delta in deltas.items()}
    else:
        before = current
        after = {field: current[field] + delta for field, delta in deltas.items()}
    changed = db.execute(
        """INSERT OR IGNORE INTO inventory_movements(
          id,event_key,order_id,sub_order_id,inventory_row_id,movement_type,quantity,
          wms_delta,erp_delta,vision_delta,reserved_delta,picked_delta,completed_delta,
          wip_stage,at,reason,actor,before_json,after_json)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"MOV-{uuid.uuid4()}", event_key, order_id, sub_order_id, row_id, kind,
            quantity, wms, erp, vision, reserved, picked, completed, wip_stage,
            at, reason, actor, json.dumps(before), json.dumps(after),
        ),
    ).rowcount
    return bool(changed)


def _weight(db: sqlite3.Connection, sku: str) -> float:
    rows = db.execute(
        "SELECT weight_kg FROM inventory_snapshot WHERE sku=?", (sku,)
    ).fetchall()
    if not rows or any(row[0] is None for row in rows):
        raise HTTPException(422, f"{sku}: every inventory row must have a positive weight_kg")
    values = {float(row[0]) for row in rows}
    if (
        len(values) != 1
        or next(iter(values), 0) <= 0
        or not math.isfinite(next(iter(values), 0))
    ):
        raise HTTPException(422, f"{sku}: inventory weight_kg must be one consistent positive value")
    return next(iter(values))


def _allocate_sub_order(
    db: sqlite3.Connection, sub_id: str, order_id: str, sku: str, quantity: int,
    at: str, warehouse_constraint: str | None = None,
) -> tuple[bool, str | None]:
    warehouses: list[tuple[int, str, list[dict[str, Any]]]] = []
    rows = inventory_rows(db, warehouse_constraint, sku)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["allocatable_qty"] > 0:
            grouped.setdefault(row["warehouse_id"], []).append(row)
    for warehouse, candidates in grouped.items():
        total = sum(row["allocatable_qty"] for row in candidates)
        if total >= quantity:
            warehouses.append((total - quantity, warehouse, candidates))
    if not warehouses:
        available = max((sum(r["allocatable_qty"] for r in rs) for rs in grouped.values()), default=0)
        reason = (
            f"INVENTORY_SHORTAGE: {sku} requires {quantity} in one warehouse; "
            f"best warehouse has {available} free"
        )
        db.execute(
            "UPDATE sub_orders SET status='held',hold_reason=?,warehouse_id=NULL WHERE id=?",
            (reason, sub_id),
        )
        return False, reason
    # Preserve the greatest remainder, then deterministic warehouse ID.
    _, warehouse, candidates = sorted(warehouses, key=lambda item: (-item[0], item[1]))[0]
    remaining = quantity
    for row in sorted(candidates, key=lambda item: (item["location"], item["inventory_row_id"])):
        take = min(remaining, row["allocatable_qty"])
        if take <= 0:
            continue
        updated = db.execute(
            """UPDATE inventory_snapshot
               SET wms_qty=wms_qty-?,erp_qty=erp_qty-?,vision_qty=vision_qty-?,
                   reserved_qty=reserved_qty+?,revision=revision+1,updated_at=?
               WHERE id=? AND inventory_status='AVAILABLE' AND blocked_allocation=0
                 AND wms_qty>=? AND erp_qty>=? AND vision_qty>=?""",
            (take, take, take, take, at, row["inventory_row_id"], take, take, take),
        ).rowcount
        if not updated:
            raise sqlite3.IntegrityError("Inventory changed during allocation")
        db.execute(
            """INSERT INTO sub_order_allocations(
                 id,sub_order_id,inventory_row_id,quantity,reserved_qty)
               VALUES (?,?,?,?,?)""",
            (f"ALLOC-{uuid.uuid4()}", sub_id, row["inventory_row_id"], take, take),
        )
        _movement(
            db, event_key=f"accept:{sub_id}:{row['inventory_row_id']}",
            order_id=order_id, sub_order_id=sub_id, row_id=row["inventory_row_id"],
            kind="accept_reserve", quantity=take, at=at, wms=-take, erp=-take,
            vision=-take, reserved=take, reason="Free stock reserved at acceptance",
            state_is_after=True,
        )
        remaining -= take
        if remaining == 0:
            break
    db.execute(
        "UPDATE sub_orders SET warehouse_id=?,status='reserved',hold_reason=NULL WHERE id=?",
        (warehouse, sub_id),
    )
    unit_weight = _weight(db, sku)
    allocations = db.execute(
        """SELECT id,quantity FROM sub_order_allocations
           WHERE sub_order_id=? ORDER BY id""",
        (sub_id,),
    ).fetchall()
    duration_seconds = task_duration_seconds(db)
    # Location Pick tasks are independently completable/accounted. All can
    # queue, but Move remains dependent on every location Pick.
    for allocation in allocations:
        db.execute(
            """INSERT INTO tasks(
                 id,order_id,stage,status,sub_order_id,allocation_id,
                 duration_seconds,payload_kg)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                f"TS-{uuid.uuid4()}", order_id, "pick", "queued", sub_id,
                allocation["id"], duration_seconds, unit_weight * allocation["quantity"],
            ),
        )
    payload = unit_weight * quantity
    for stage in STAGES[1:]:
        db.execute(
            """INSERT INTO tasks(
                 id,order_id,stage,status,sub_order_id,duration_seconds,payload_kg)
               VALUES (?,?,?,'pending',?,?,?)""",
            (f"TS-{uuid.uuid4()}", order_id, stage, sub_id, duration_seconds, payload),
        )
    db.execute("UPDATE sub_orders SET status='queued' WHERE id=?", (sub_id,))
    return True, None


def create_order(
    db: sqlite3.Connection,
    payload: Any,
    *,
    parse_utc: Any,
    now: datetime,
    known_skus: set[str],
    known_warehouses: set[str],
    order_json: Any,
    append_event: Any,
) -> dict[str, Any]:
    service = payload.order_service or ("Standard" if payload.warehouse_id else None)
    if not service:
        raise HTTPException(422, "order_service is required when warehouse_id is omitted")
    existing = db.execute(
        "SELECT id,request_fingerprint,order_created_at FROM orders WHERE request_id=?",
        (str(payload.request_id),),
    ).fetchone()
    created_value = payload.order_created_at or (
        existing["order_created_at"] if existing else None
    )
    if not created_value and payload.ship_by:
        try:
            derived = parse_utc(payload.ship_by) - timedelta(hours=SERVICES[service])
            created_value = _iso(min(derived, now))
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, "ship_by must be a future UTC ISO-8601 timestamp") from exc
    if not created_value:
        raise HTTPException(422, "order_created_at is required when warehouse_id is omitted")
    try:
        created = parse_utc(created_value)
    except ValueError as exc:
        raise HTTPException(422, f"order_created_at {exc}") from exc
    if created > now + timedelta(minutes=5):
        raise HTTPException(422, "order_created_at cannot be in the future")
    immutable_created = _iso(created)
    fingerprint = request_fingerprint(payload, immutable_created)
    if existing:
        if existing["request_fingerprint"] != fingerprint:
            raise HTTPException(409, "request_id is already associated with a different payload")
        return order_json(db, existing["id"])
    # Bazaar itself requires a warehouse for every new request. Core applies
    # the strict atomic policy only when that explicit selection is present so
    # durable pre-policy outbox messages without a warehouse can still drain
    # through the legacy automatic allocation behavior after an upgrade.
    strict_bazaar = (
        payload.order_source == "fde_bazaar" and bool(payload.warehouse_id)
    )
    if payload.warehouse_id and payload.warehouse_id not in known_warehouses:
        raise HTTPException(422, f"Unknown warehouse_id {payload.warehouse_id}")
    seen: set[str] = set()
    lines = []
    for line in payload.lines:
        if line.sku in seen:
            raise HTTPException(422, f"Duplicate SKU {line.sku}; combine quantities before submitting")
        if line.sku not in known_skus:
            raise HTTPException(422, f"Unknown SKU {line.sku}")
        seen.add(line.sku)
        lines.append((line.sku, int(line.quantity)))
    if not lines:
        raise HTTPException(422, "lines must contain at least one SKU quantity")
    if strict_bazaar:
        warehouse_id = payload.warehouse_id
        for sku, quantity in lines:
            available = sum(
                row["allocatable_qty"]
                for row in inventory_rows(db, warehouse_id, sku)
            )
            if available < quantity:
                raise HTTPException(
                    422,
                    {
                        "code": "INVENTORY_SHORTAGE",
                        "warehouse_id": warehouse_id,
                        "sku": sku,
                        "requested": quantity,
                        "available": available,
                        "message": (
                            f"Warehouse {warehouse_id} cannot allocate SKU {sku}: "
                            f"requested {quantity}, available {available}"
                        ),
                    },
                )
    deadline = cutoff(service, created)
    if payload.ship_by:
        try:
            explicit_deadline = parse_utc(payload.ship_by)
        except ValueError as exc:
            raise HTTPException(422, f"ship_by {exc}") from exc
        if explicit_deadline <= now:
            raise HTTPException(422, "ship_by must be a future UTC ISO-8601 timestamp")
        deadline = explicit_deadline
    order_id = f"FUL-{uuid.uuid4()}"
    stamp = _iso(now)
    db.execute(
        """INSERT INTO orders(
          id,warehouse_id,priority,ship_by,status,created_at,plan_json,issues_json,
          request_id,source_order_id,order_service,order_source,request_fingerprint,
          policy_version,cutoff_at,order_created_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,2,?,?)""",
        (
            order_id, payload.warehouse_id or "", payload.priority, _iso(deadline), "held", stamp, "{}",
            "[]", str(payload.request_id), payload.source_order_id,
            service, payload.order_source, fingerprint,
            _iso(deadline), immutable_created,
        ),
    )
    db.executemany(
        "INSERT INTO order_lines(order_id,sku,quantity) VALUES (?,?,?)",
        [(order_id, sku, quantity) for sku, quantity in lines],
    )
    accepted = 0
    issues: list[str] = []
    for sku, quantity in lines:
        sub_id = f"SUB-{uuid.uuid5(uuid.NAMESPACE_URL, str(payload.request_id) + ':' + sku)}"
        db.execute(
            """INSERT INTO sub_orders(
              id,order_id,sku,quantity,status,cutoff_at,created_at)
              VALUES (?,?,?,?,'held',?,?)""",
            (sub_id, order_id, sku, quantity, _iso(deadline), stamp),
        )
        ok, issue = _allocate_sub_order(
            db, sub_id, order_id, sku, quantity, stamp, payload.warehouse_id
        )
        accepted += int(ok)
        if issue:
            issues.append(issue)
    status = "active" if accepted == len(lines) else ("partially_fulfilled" if accepted else "held")
    db.execute(
        "UPDATE orders SET status=?,issues_json=? WHERE id=?",
        (status, json.dumps(issues), order_id),
    )
    append_event(
        db, order_id,
        f"Policy v2 intake accepted {accepted}/{len(lines)} SKU lines; accepted work automatically queued",
        now,
    )
    return order_json(db, order_id)


def _allocations(db: sqlite3.Connection, sub_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in db.execute(
            """SELECT a.*,i.location,i.zone,i.warehouse_id
               FROM sub_order_allocations a JOIN inventory_snapshot i
                 ON i.id=a.inventory_row_id WHERE a.sub_order_id=?
               ORDER BY i.location,a.id""",
            (sub_id,),
        )
    ]


def enrich_order(db: sqlite3.Connection, result: dict[str, Any], now: datetime) -> dict[str, Any]:
    row = db.execute(
        "SELECT policy_version,cutoff_at,order_created_at FROM orders WHERE id=?",
        (result["id"],),
    ).fetchone()
    version = int(row["policy_version"] or 1)
    result["policy_version"] = version
    if version != 2:
        return result
    result["warehouse_id"] = result["warehouse_id"] or None
    result["cutoff_at"] = row["cutoff_at"]
    result["cutoff_timezone"] = "UTC"
    result["order_created_at"] = row["order_created_at"]
    result["overdue"] = bool(row["cutoff_at"] and row["cutoff_at"] < _iso(now) and result["status"] not in {"completed", "cancelled", "rejected"})
    subs = []
    for sub in db.execute("SELECT * FROM sub_orders WHERE order_id=? ORDER BY rowid", (result["id"],)):
        item = dict(sub)
        item["allocations"] = _allocations(db, sub["id"])
        item["tasks"] = [
            dict(task)
            for task in db.execute(
                "SELECT * FROM tasks WHERE sub_order_id=? ORDER BY rowid", (sub["id"],)
            )
        ]
        subs.append(item)
    result["sub_orders"] = subs
    return result


def _update_parent(db: sqlite3.Connection, order_id: str) -> None:
    statuses = [row[0] for row in db.execute("SELECT status FROM sub_orders WHERE order_id=?", (order_id,))]
    if not statuses:
        return
    if all(status == "rejected" for status in statuses):
        status = "rejected"
    elif any(status == "recovery_required" for status in statuses):
        status = "recovery_required"
    elif all(status == "cancelled" for status in statuses):
        status = "cancelled"
    elif all(status in {"completed", "cancelled", "rejected"} for status in statuses):
        status = "completed" if all(s == "completed" for s in statuses) else "partially_fulfilled"
    elif any(status == "completed" for status in statuses):
        status = "partially_fulfilled"
    elif any(status in {"queued", "running", "reserved"} for status in statuses):
        status = "partially_fulfilled" if any(s in {"held", "rejected"} for s in statuses) else "active"
    else:
        status = "held"
    reasons = [
        row[0] for row in db.execute(
            "SELECT hold_reason FROM sub_orders WHERE order_id=? AND hold_reason IS NOT NULL",
            (order_id,),
        ) if row[0]
    ]
    db.execute(
        "UPDATE orders SET status=?,issues_json=? WHERE id=?",
        (status, json.dumps(reasons), order_id),
    )


def cancel(db: sqlite3.Connection, order_id: str, at: datetime, append_event: Any) -> None:
    stamp = _iso(at)
    subs = db.execute("SELECT * FROM sub_orders WHERE order_id=?", (order_id,)).fetchall()
    for sub in subs:
        if sub["status"] in {"completed", "cancelled"}:
            continue
        demo_hold = db.execute(
            """SELECT f.failure_reason FROM tasks t
               JOIN lifecycle_demo_failures f ON f.task_id=t.id
               WHERE t.sub_order_id=? AND f.resolved_at IS NULL LIMIT 1""",
            (sub["id"],),
        ).fetchone()
        if demo_hold:
            # Cancellation cannot silently release the protected assignment or
            # reservation underneath an unresolved explicit failure.
            db.execute(
                """UPDATE sub_orders SET status='recovery_required',hold_reason=?
                   WHERE id=?""",
                (f"DEMO_FAILURE: {demo_hold['failure_reason']}", sub["id"]),
            )
            continue
        picked_any = False
        for allocation in _allocations(db, sub["id"]):
            unpicked = allocation["reserved_qty"]
            picked_any = picked_any or allocation["picked_qty"] > allocation["completed_qty"]
            if unpicked and _movement(
                db, event_key=f"cancel:{allocation['id']}", order_id=order_id,
                sub_order_id=sub["id"], row_id=allocation["inventory_row_id"],
                kind="cancel_release", quantity=unpicked, at=stamp, wms=unpicked,
                erp=unpicked, vision=unpicked, reserved=-unpicked,
                reason="Cancellation restored only unpicked reserved units",
            ):
                db.execute(
                    """UPDATE inventory_snapshot SET
                       wms_qty=wms_qty+?,erp_qty=erp_qty+?,vision_qty=vision_qty+?,
                       reserved_qty=reserved_qty-?,revision=revision+1,updated_at=? WHERE id=?""",
                    (unpicked, unpicked, unpicked, unpicked, stamp, allocation["inventory_row_id"]),
                )
                db.execute(
                    "UPDATE sub_order_allocations SET reserved_qty=0 WHERE id=?",
                    (allocation["id"],),
                )
        new_status = "recovery_required" if picked_any else "cancelled"
        reason = "Picked work requires verified recovery" if picked_any else "Cancelled before Pick completion"
        db.execute(
            "UPDATE sub_orders SET status=?,hold_reason=?,cancelled_at=? WHERE id=?",
            (new_status, reason, stamp, sub["id"]),
        )
        db.execute(
            "UPDATE tasks SET status='cancelled',wait_reason=? WHERE sub_order_id=? AND status!='completed'",
            (reason, sub["id"]),
        )
    _update_parent(db, order_id)
    append_event(db, order_id, "Policy v2 cancellation serialized with Pick; only unpicked stock restored", at)


def reevaluate_held(
    db: sqlite3.Connection,
    at: datetime,
    order_id: str | None = None,
) -> int:
    changed = 0
    order_filter = " AND s.order_id=?" if order_id is not None else ""
    rows = db.execute(
        f"""SELECT s.*, o.warehouse_id AS requested_warehouse_id
            FROM sub_orders s JOIN orders o ON o.id=s.order_id
            WHERE o.policy_version=2 AND s.status='held'
              AND s.hold_reason LIKE 'INVENTORY_SHORTAGE:%'
              {order_filter}
            ORDER BY datetime(s.cutoff_at),s.id""",
        (order_id,) if order_id is not None else (),
    ).fetchall()
    stamp = _iso(at)
    for row in rows:
        ok, _ = _allocate_sub_order(
            db, row["id"], row["order_id"], row["sku"], row["quantity"], stamp,
            row["requested_warehouse_id"] or None,
        )
        if ok:
            changed += 1
            _update_parent(db, row["order_id"])
    return changed


def correct_inventory(
    db: sqlite3.Connection,
    row_id: int,
    values: dict[str, Any],
    basis: str,
    revision: int,
    reason: str,
    actor: str,
    at: datetime,
) -> dict[str, Any]:
    if basis not in {"free", "total_on_hand"}:
        raise HTTPException(422, "basis must be free or total_on_hand")
    if not reason.strip() or not actor.strip():
        raise HTTPException(422, "reason and actor are required")
    allowed = {"wms_qty", "erp_qty", "vision_qty"}
    if not values or set(values) - allowed:
        raise HTTPException(422, "values may contain only wms_qty, erp_qty, vision_qty")
    row = db.execute("SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Unknown inventory row {row_id}")
    if int(row["revision"]) != revision:
        raise HTTPException(409, f"Inventory revision conflict: current revision is {row['revision']}")
    updates: dict[str, int] = {}
    for field, raw in values.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not float(raw).is_integer():
            raise HTTPException(422, f"{field} must be a nonnegative integer")
        observed = int(raw)
        if observed < 0:
            raise HTTPException(422, f"{field} must be a nonnegative integer")
        free = observed
        if basis == "total_on_hand":
            free = observed - int(row["reserved_qty"]) - int(row["picked_qty"])
            if free < 0:
                raise HTTPException(
                    409, f"{field} total_on_hand is below reserved plus picked accounting"
                )
        updates[field] = free
    before = dict(row)
    assignments = ",".join(f"{field}=?" for field in updates)
    db.execute(
        f"UPDATE inventory_snapshot SET {assignments},revision=revision+1,updated_at=? WHERE id=?",
        (*updates.values(), _iso(at), row_id),
    )
    after = dict(db.execute("SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)).fetchone())
    db.execute(
        """INSERT INTO inventory_corrections(
          id,inventory_row_id,before_json,after_json,basis,reason,actor,at)
          VALUES (?,?,?,?,?,?,?,?)""",
        (
            f"COR-{uuid.uuid4()}", row_id, json.dumps(before), json.dumps(after),
            basis, reason.strip(), actor.strip(), _iso(at),
        ),
    )
    reevaluate_held(db, at)
    return next(
        item
        for item in inventory_rows(db, after["warehouse_id"], after["sku"])
        if item["inventory_row_id"] == row_id
    )


def sync_inventory_sources_to_current_max(
    db: sqlite3.Connection,
    row_id: int,
    reason: str,
    actor: str,
    at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Align one app-owned inventory row without changing allocation accounting.

    Unlike ``correct_inventory``, this deliberately does not reevaluate held
    work. Manual issue closure must not recover orders or tasks implicitly.
    Existing discrepancy/allocation safety flags are also preserved.
    """
    if not reason.strip() or not actor.strip():
        raise HTTPException(422, "reason and actor are required")
    row = db.execute("SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Unknown inventory row {row_id}")
    before = dict(row)
    fields = ("wms_qty", "erp_qty", "vision_qty")
    quantities: list[int] = []
    for field in fields:
        raw = before[field]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not float(raw).is_integer():
            raise HTTPException(409, f"Current {field} is not a valid nonnegative integer")
        quantity = int(raw)
        if quantity < 0:
            raise HTTPException(409, f"Current {field} is not a valid nonnegative integer")
        quantities.append(quantity)
    synced = max(quantities)
    if any(quantity != synced for quantity in quantities):
        db.execute(
            """UPDATE inventory_snapshot SET
               wms_qty=?,erp_qty=?,vision_qty=?,revision=revision+1,updated_at=?
               WHERE id=?""",
            (synced, synced, synced, _iso(at), row_id),
        )
        after = dict(db.execute("SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)).fetchone())
        db.execute(
            """INSERT INTO inventory_corrections(
              id,inventory_row_id,before_json,after_json,basis,reason,actor,at)
              VALUES (?,?,?,?,?,?,?,?)""",
            (
                f"COR-{uuid.uuid4()}",
                row_id,
                json.dumps(before),
                json.dumps(after),
                "free",
                reason.strip(),
                actor.strip(),
                _iso(at),
            ),
        )
    else:
        after = before
    return before, after


def verify_opening_inventory(
    db: sqlite3.Connection,
    row_id: int,
    reason: str,
    actor: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Attest and clear only a corrected opening-external-reservation block.

    The evidence is deliberately strict: all three current total-on-hand
    observations and the optimistic inventory revision must be attested
    together. Legacy-unmapped reservation anomalies are never cleared here.
    """
    if not reason.strip() or not actor.strip():
        raise HTTPException(422, "reason and actor are required")
    required = {
        "revision", "basis", "wms_qty", "erp_qty", "vision_qty", "attestation"
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise HTTPException(
            422,
            "evidence must contain exactly revision, basis, wms_qty, erp_qty, "
            "vision_qty, and attestation",
        )
    if evidence["basis"] != "total_on_hand":
        raise HTTPException(422, "opening verification evidence basis must be total_on_hand")
    if not isinstance(evidence["attestation"], str) or not evidence["attestation"].strip():
        raise HTTPException(422, "evidence attestation is required")
    if isinstance(evidence["revision"], bool) or not isinstance(evidence["revision"], int):
        raise HTTPException(422, "evidence revision must be an integer")
    for field in ("wms_qty", "erp_qty", "vision_qty"):
        value = evidence[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float(value).is_integer()
            or int(value) < 0
        ):
            raise HTTPException(422, f"evidence {field} must be a nonnegative integer")

    canonical = {
        "row_id": row_id,
        "reason": reason.strip(),
        "actor": actor.strip(),
        "evidence": evidence,
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # Lost-response retry: return the current row without another revision,
    # audit record, reevaluation, reservation, or movement.
    for correction in db.execute(
        """SELECT after_json FROM inventory_corrections
           WHERE inventory_row_id=? AND basis='opening_verification'
           ORDER BY rowid DESC""",
        (row_id,),
    ):
        recorded = json.loads(correction["after_json"])
        if recorded.get("_verification_fingerprint") == fingerprint:
            current = db.execute(
                "SELECT warehouse_id,sku FROM inventory_snapshot WHERE id=?", (row_id,)
            ).fetchone()
            if not current:
                raise HTTPException(404, f"Unknown inventory row {row_id}")
            return next(
                item
                for item in inventory_rows(db, current["warehouse_id"], current["sku"])
                if item["inventory_row_id"] == row_id
            )

    row = db.execute("SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Unknown inventory row {row_id}")
    if int(row["revision"]) != evidence["revision"]:
        raise HTTPException(
            409, f"Inventory revision conflict: current revision is {row['revision']}"
        )
    discrepancy = str(row["opening_discrepancy"] or "")
    if not row["blocked_allocation"]:
        raise HTTPException(409, "Inventory row is not blocked for opening verification")
    if "Legacy reservation" in discrepancy:
        raise HTTPException(
            409,
            "Legacy-unmapped reservation anomaly requires explicit reconciliation; "
            "opening verification cannot clear it",
        )
    if not discrepancy.startswith("Opening external reservation "):
        raise HTTPException(
            409, "Block is not an opening external-reservation inconsistency"
        )

    protected = int(row["reserved_qty"]) + int(row["picked_qty"])
    for field in ("wms_qty", "erp_qty", "vision_qty"):
        observed_total = int(evidence[field])
        expected_total = int(row[field]) + protected
        if observed_total < protected or observed_total != expected_total:
            raise HTTPException(
                409,
                f"{field} attested total must equal current free plus protected "
                f"reserved/picked accounting ({expected_total})",
            )

    before = dict(row)
    stamp = _iso(datetime.now(timezone.utc))
    db.execute(
        """UPDATE inventory_snapshot SET blocked_allocation=0,
           opening_discrepancy=NULL,revision=revision+1,updated_at=? WHERE id=?""",
        (stamp, row_id),
    )
    after = dict(db.execute(
        "SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)
    ).fetchone())
    audited_after = {
        **after,
        "_verification_fingerprint": fingerprint,
        "_verification_evidence": evidence,
    }
    db.execute(
        """INSERT INTO inventory_corrections(
          id,inventory_row_id,before_json,after_json,basis,reason,actor,at)
          VALUES (?,?,?,?,?,?,?,?)""",
        (
            f"COR-{uuid.uuid4()}", row_id, json.dumps(before),
            json.dumps(audited_after), "opening_verification",
            reason.strip(), actor.strip(), stamp,
        ),
    )
    reevaluate_held(db, datetime.now(timezone.utc))
    current = db.execute(
        "SELECT warehouse_id,sku FROM inventory_snapshot WHERE id=?", (row_id,)
    ).fetchone()
    return next(
        item
        for item in inventory_rows(db, current["warehouse_id"], current["sku"])
        if item["inventory_row_id"] == row_id
    )


def robot_eligibility(
    db: sqlite3.Connection,
    robot: dict[str, Any],
    warehouse_id: str,
    stage: str,
    payload_kg: float,
    used: set[str],
    maintenance_rows: tuple[dict[str, Any], ...],
    now: datetime,
    inflight: bool = False,
) -> tuple[bool, list[str]]:
    robot_id = str(robot.get("robot_id") or "")
    lifecycle = db.execute("SELECT * FROM resource_lifecycle WHERE resource_id=?", (robot_id,)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='resource_lifecycle'").fetchone() else None
    if lifecycle:
        reasons = json.loads(lifecycle["fitness_reasons"]) if inflight else robot_lifecycle.blockers(lifecycle)
        # Validate the supplied current source evidence as well (public eligibility
        # callers may be previewing a correction before it is persisted).
        _, source_reasons = robot_readiness(robot, maintenance_rows)
        reasons.extend(reason for reason in source_reasons if reason not in reasons)
    else:
        _, reasons = robot_readiness(robot, maintenance_rows)
        if not inflight:
            try:
                if not 10 < float(robot.get("battery_soc")) <= 100:
                    reasons.append("Battery must be strictly greater than 10%")
            except (TypeError, ValueError):
                reasons.append("Battery evidence is unknown")
    if robot.get("warehouse_id") != warehouse_id:
        reasons.append("Warehouse is incompatible")
    if robot.get("robot_type") not in ROBOT_TYPES.get(stage, set()):
        reasons.append(f"Robot type is incompatible with {stage}")
    if _f(robot.get("payload_kg")) < payload_kg:
        reasons.append("Payload capacity is insufficient")
    if robot_id in used:
        reasons.append("Resource is already claimed")
    for sql, label in (
        (
            "SELECT 1 FROM persona_safety_holds "
            "WHERE robot_id=? AND released_at IS NULL",
            "Explicit safety hold is active",
        ),
        (
            "SELECT 1 FROM persona_resource_blocks WHERE resource_id=?",
            "Explicit resource block is active",
        ),
        (
            "SELECT 1 FROM lifecycle_failed_resources "
            "WHERE resource_id=? AND recovered_at IS NULL",
            "Simulator failure block is active",
        ),
    ):
        try:
            if db.execute(sql, (robot_id,)).fetchone():
                reasons.append(label)
        except sqlite3.OperationalError:
            continue
    return not reasons, reasons


def asset_eligibility(
    asset: dict[str, Any],
    warehouse_id: str,
    stage: str,
    used: set[str],
    db: sqlite3.Connection | None = None,
) -> tuple[bool, list[str]]:
    _, reasons = asset_readiness(asset)
    if asset.get("warehouse_id") != warehouse_id:
        reasons.append("Warehouse is incompatible")
    if asset.get("asset_type") not in ASSET_TYPES.get(stage, set()):
        reasons.append(f"Asset type is incompatible with {stage}")
    if asset.get("asset_id") in used:
        reasons.append("Resource is already claimed")
    if db is not None:
        try:
            blocked = db.execute(
                "SELECT 1 FROM persona_resource_blocks WHERE resource_id=?",
                (asset.get("asset_id"),),
            ).fetchone()
            simulator_blocked = db.execute(
                """SELECT 1 FROM lifecycle_failed_resources
                   WHERE resource_id=? AND recovered_at IS NULL""",
                (asset.get("asset_id"),),
            ).fetchone()
            if blocked:
                reasons.append("Explicit resource block is active")
            if simulator_blocked:
                reasons.append("Simulator failure block is active")
        except sqlite3.OperationalError:
            pass
    return not reasons, reasons


def _choose(
    db: sqlite3.Connection,
    task: sqlite3.Row,
    source_rows: Any,
    now: datetime,
    used: set[str],
) -> tuple[str | None, str | None, list[str]]:
    sub = db.execute("SELECT warehouse_id FROM sub_orders WHERE id=?", (task["sub_order_id"],)).fetchone()
    warehouse = sub["warehouse_id"]
    preferred = db.execute(
        "SELECT resource_id,resource_type FROM task_recovery_preferences WHERE task_id=?",
        (task["id"],),
    ).fetchone()
    if preferred:
        resource_id = preferred["resource_id"]
        is_robot = task["stage"] in ROBOT_TYPES
        dataset, identity = ("robots", "robot_id") if is_robot else ("control_assets", "asset_id")
        resource = next((row for row in source_rows(dataset) if row.get(identity) == resource_id), None)
        if not resource:
            return None, None, [f"Preferred recovery resource {resource_id} is no longer registered"]
        if is_robot:
            ready, reasons = robot_eligibility(
                db, resource, warehouse, task["stage"], float(task["payload_kg"]),
                used, source_rows("maintenance"), now,
            )
        else:
            ready, reasons = asset_eligibility(resource, warehouse, task["stage"], used, db)
        if not ready:
            return None, None, [f"Preferred recovery resource {resource_id}: {reason}" for reason in reasons]
        return resource_id, "robot" if is_robot else "control_asset", []
    if task["stage"] in ROBOT_TYPES:
        excluded = []
        choices = []
        maintenance = source_rows("maintenance")
        for robot in source_rows("robots"):
            ok, reasons = robot_eligibility(
                db, robot, warehouse, task["stage"], float(task["payload_kg"]),
                used, maintenance, now,
            )
            if ok:
                choices.append(robot)
            elif robot.get("warehouse_id") == warehouse:
                excluded.extend(f"{robot.get('robot_id')}: {reason}" for reason in reasons)
        if choices:
            choice = sorted(choices, key=lambda r: (_f(r.get("payload_kg")), r.get("robot_id", "")))[0]
            return choice["robot_id"], "robot", excluded
        return None, None, excluded or ["No robot has sufficient readiness evidence"]
    excluded = []
    choices = []
    for asset in source_rows("control_assets"):
        ok, reasons = asset_eligibility(asset, warehouse, task["stage"], used, db)
        if ok:
            choices.append(asset)
        elif asset.get("warehouse_id") == warehouse:
            excluded.extend(f"{asset.get('asset_id')}: {reason}" for reason in reasons)
    if choices:
        choice = sorted(choices, key=lambda r: r.get("asset_id", ""))[0]
        return choice["asset_id"], "control_asset", excluded
    return None, None, excluded or ["No compatible AVAILABLE/CLEAR control asset"]


def _assigned_readiness(
    db: sqlite3.Connection, task: sqlite3.Row, source_rows: Any, now: datetime
) -> tuple[bool, list[str]]:
    sub = db.execute(
        "SELECT warehouse_id FROM sub_orders WHERE id=?", (task["sub_order_id"],)
    ).fetchone()
    warehouse = sub["warehouse_id"]
    if task["stage"] in ROBOT_TYPES:
        robot = next(
            (
                row for row in source_rows("robots")
                if row.get("robot_id") == task["resource_id"]
            ),
            None,
        )
        if not robot:
            return False, ["Assigned robot is missing from the current registry"]
        return robot_eligibility(
            db, robot, warehouse, task["stage"], float(task["payload_kg"]),
            set(), source_rows("maintenance"), now, inflight=True,
        )
    asset = next(
        (
            row for row in source_rows("control_assets")
            if row.get("asset_id") == task["resource_id"]
        ),
        None,
    )
    if not asset:
        return False, ["Assigned control asset is missing from the current registry"]
    return asset_eligibility(asset, warehouse, task["stage"], set(), db)


def _complete(db: sqlite3.Connection, task: sqlite3.Row, now: datetime) -> bool:
    stamp = _iso(now)
    changed = db.execute(
        "UPDATE tasks SET status='completed',completed_at=? WHERE id=? AND status='running' AND due_at<=?",
        (stamp, task["id"], stamp),
    ).rowcount
    if not changed:
        return False
    sub = db.execute("SELECT * FROM sub_orders WHERE id=?", (task["sub_order_id"],)).fetchone()
    allocations = _allocations(db, sub["id"])
    if task["stage"] == "pick":
        allocations = [
            allocation
            for allocation in allocations
            if allocation["id"] == task["allocation_id"]
        ]
        for allocation in allocations:
            quantity = allocation["reserved_qty"]
            if quantity and _movement(
                db, event_key=f"pick:{task['id']}:{allocation['id']}",
                order_id=task["order_id"], sub_order_id=sub["id"],
                row_id=allocation["inventory_row_id"], kind="pick_complete",
                quantity=quantity, at=stamp, reserved=-quantity, picked=quantity,
                wip_stage="picked", reason="Pick moved reserved units to WIP",
            ):
                db.execute(
                    """UPDATE inventory_snapshot SET reserved_qty=reserved_qty-?,
                       picked_qty=picked_qty+?,revision=revision+1,updated_at=? WHERE id=?""",
                    (quantity, quantity, stamp, allocation["inventory_row_id"]),
                )
                db.execute(
                    """UPDATE sub_order_allocations SET reserved_qty=0,
                       picked_qty=picked_qty+?,wip_stage='picked' WHERE id=?""",
                    (quantity, allocation["id"]),
                )
    elif task["stage"] == "stage":
        for allocation in allocations:
            outstanding = allocation["picked_qty"] - allocation["completed_qty"]
            if outstanding and _movement(
                db, event_key=f"complete:{task['id']}:{allocation['id']}",
                order_id=task["order_id"], sub_order_id=sub["id"],
                row_id=allocation["inventory_row_id"], kind="fulfillment_complete",
                quantity=outstanding, at=stamp, picked=-outstanding,
                completed=outstanding, wip_stage="completed",
                reason="Final Stage moved WIP to completed",
            ):
                db.execute(
                    """UPDATE inventory_snapshot SET picked_qty=picked_qty-?,
                       completed_qty=completed_qty+?,revision=revision+1,updated_at=? WHERE id=?""",
                    (outstanding, outstanding, stamp, allocation["inventory_row_id"]),
                )
                db.execute(
                    """UPDATE sub_order_allocations SET completed_qty=completed_qty+?,
                       wip_stage='completed' WHERE id=?""",
                    (outstanding, allocation["id"]),
                )
        db.execute(
            "UPDATE sub_orders SET status='completed',completed_at=?,hold_reason=NULL WHERE id=?",
            (stamp, sub["id"]),
        )
    else:
        for allocation in allocations:
            outstanding = allocation["picked_qty"] - allocation["completed_qty"]
            if outstanding:
                _movement(
                    db, event_key=f"transfer:{task['id']}:{allocation['id']}",
                    order_id=task["order_id"], sub_order_id=sub["id"],
                    row_id=allocation["inventory_row_id"],
                    kind=f"{task['stage']}_complete", quantity=outstanding,
                    at=stamp, wip_stage=task["stage"],
                    reason=f"{task['stage']} transferred WIP without a stock debit",
                )
        db.execute(
            "UPDATE sub_order_allocations SET wip_stage=? WHERE sub_order_id=?",
            (task["stage"], sub["id"]),
        )
    unfinished_picks = db.execute(
        """SELECT 1 FROM tasks WHERE sub_order_id=? AND stage='pick'
           AND status!='completed' LIMIT 1""",
        (sub["id"],),
    ).fetchone()
    next_task = None
    if not unfinished_picks:
        next_task = db.execute(
            "SELECT id FROM tasks WHERE sub_order_id=? AND status='pending' ORDER BY rowid LIMIT 1",
            (sub["id"],),
        ).fetchone()
    if next_task:
        db.execute("UPDATE tasks SET status='queued' WHERE id=?", (next_task["id"],))
        db.execute("UPDATE sub_orders SET status='queued' WHERE id=?", (sub["id"],))
    _update_parent(db, task["order_id"])
    return True


def replace_queued_task(
    db: sqlite3.Connection, task_id: str, now: datetime, source_rows: Any,
    append_event: Any, excluded_resources: set[str] | None = None,
) -> str | None:
    """Assign only one queued task without consuming the global cadence gate."""
    import persona_v2
    supplied_source_rows = source_rows
    cache: dict[str, tuple[dict[str, Any], ...]] = {}

    def effective_rows(dataset: str):
        if dataset not in cache:
            cache[dataset] = persona_v2.effective_source_rows(
                db, dataset, supplied_source_rows(dataset)
            )
        return cache[dataset]

    robot_lifecycle.reconcile(db, now, effective_rows)
    task = db.execute(
        """SELECT t.* FROM tasks t JOIN orders o ON o.id=t.order_id
           WHERE t.id=? AND o.policy_version=2 AND t.status='queued'""",
        (task_id,),
    ).fetchone()
    if not task:
        return None
    used = {
        row[0]
        for row in db.execute(
            """SELECT resource_id FROM tasks
               WHERE resource_id IS NOT NULL AND status IN ('running','paused')"""
        )
    }
    used.update(excluded_resources or set())
    try:
        used.update(
            row[0]
            for row in db.execute(
                """SELECT tr.resource_id FROM task_resources tr
                   JOIN tasks t ON t.id=tr.task_id
                   WHERE t.status IN ('pending','queued','running','paused')"""
            )
        )
    except sqlite3.OperationalError:
        pass
    resource, kind, reasons = _choose(db, task, effective_rows, now, used)
    if not resource:
        waiting = "WAITING_FOR_RESOURCE: " + "; ".join(reasons[:8])
        db.execute("UPDATE tasks SET wait_reason=? WHERE id=?", (waiting, task_id))
        db.execute(
            "UPDATE sub_orders SET status='reserved',hold_reason=? WHERE id=?",
            (waiting, task["sub_order_id"]),
        )
        _update_parent(db, task["order_id"])
        append_event(db, task["order_id"], waiting, now)
        return None
    duration_seconds = task_duration_seconds(db)
    due_at = now + timedelta(seconds=duration_seconds)
    changed = db.execute(
        """UPDATE tasks SET status='running',resource_id=?,resource_type=?,
             started_at=?,due_at=?,duration_seconds=?,wait_reason=NULL,
             assignment_version=assignment_version+1
           WHERE id=? AND status='queued'""",
        (resource, kind, _iso(now), _iso(due_at), duration_seconds, task_id),
    ).rowcount
    if not changed:
        return None
    db.execute("DELETE FROM task_recovery_preferences WHERE task_id=?", (task_id,))
    db.execute(
        "UPDATE sub_orders SET status='running',hold_reason=NULL WHERE id=?",
        (task["sub_order_id"],),
    )
    _update_parent(db, task["order_id"])
    append_event(
        db, task["order_id"],
        f"Policy v2 {task['stage']} promptly replaced assignment with {resource}", now,
    )
    robot_lifecycle.reconcile(db, now, effective_rows)
    return resource


def trigger_planner(
    db: sqlite3.Connection,
    order_id: str,
    now: datetime,
    supplied_source_rows: Any,
    append_event: Any,
) -> dict[str, int]:
    """Plan one order immediately without advancing the global executor.

    The caller owns the transaction. This deliberately neither consults nor
    updates lifecycle_scheduler, and it never completes running work.
    """
    import persona_v2

    order = db.execute(
        "SELECT status,policy_version FROM orders WHERE id=?", (order_id,)
    ).fetchone()
    if not order or int(order["policy_version"] or 1) != 2:
        return {"rechecked": 0, "resumed": 0, "assigned": 0}
    if order["status"] in {"completed", "cancelled", "rejected"}:
        return {"rechecked": 0, "resumed": 0, "assigned": 0}

    effective_cache: dict[str, tuple[dict[str, Any], ...]] = {}

    def source_rows(dataset: str):
        if dataset not in effective_cache:
            effective_cache[dataset] = persona_v2.effective_source_rows(
                db, dataset, supplied_source_rows(dataset)
            )
        return effective_cache[dataset]

    robot_lifecycle.reconcile(db, now, source_rows)
    counts = {
        "rechecked": db.execute(
            """SELECT count(*) FROM sub_orders
               WHERE order_id=? AND status='held'
                 AND hold_reason LIKE 'INVENTORY_SHORTAGE:%'""",
            (order_id,),
        ).fetchone()[0],
        "resumed": 0,
        "assigned": 0,
    }
    reevaluate_held(db, now, order_id=order_id)

    # Only ordinary readiness pauses are planner-recoverable. Persona recovery
    # pauses and lifecycle demo failures require their explicit verification
    # flows, even if their source resource now appears healthy.
    paused = db.execute(
        """SELECT t.* FROM tasks t
           WHERE t.order_id=? AND t.status='paused'
             AND NOT EXISTS (
               SELECT 1 FROM lifecycle_demo_failures f
               WHERE f.task_id=t.id AND f.resolved_at IS NULL
             )
             AND NOT EXISTS (
               SELECT 1 FROM persona_task_pauses p WHERE p.task_id=t.id
             )
           ORDER BY t.id""",
        (order_id,),
    ).fetchall()
    for task in paused:
        ready, _ = _assigned_readiness(db, task, source_rows, now)
        if not ready:
            continue
        changed = db.execute(
            """UPDATE tasks SET status='queued',resource_id=NULL,resource_type=NULL,
                 started_at=NULL,due_at=NULL,wait_reason=NULL
               WHERE id=? AND status='paused'""",
            (task["id"],),
        ).rowcount
        if changed:
            counts["resumed"] += 1
            db.execute(
                "UPDATE sub_orders SET status='queued',hold_reason=NULL WHERE id=?",
                (task["sub_order_id"],),
            )

    # Claims are global even though candidates are scoped. This prevents a
    # targeted trigger from stealing resources from unrelated running/paused
    # work or from legacy multi-resource tasks.
    used = {
        row[0]
        for row in db.execute(
            """SELECT resource_id FROM tasks
               WHERE resource_id IS NOT NULL AND status IN ('running','paused')"""
        )
    }
    try:
        used.update(
            row[0]
            for row in db.execute(
                """SELECT tr.resource_id FROM task_resources tr
                   JOIN tasks t ON t.id=tr.task_id
                   WHERE t.status IN ('pending','queued','running','paused')"""
            )
        )
    except sqlite3.OperationalError:
        pass

    queued = db.execute(
        """SELECT t.* FROM tasks t JOIN sub_orders s ON s.id=t.sub_order_id
           WHERE t.order_id=? AND t.status='queued'
             AND NOT EXISTS (
               SELECT 1 FROM lifecycle_demo_failures f
               WHERE f.task_id=t.id AND f.resolved_at IS NULL
             )
             AND NOT EXISTS (
               SELECT 1 FROM persona_task_pauses p WHERE p.task_id=t.id
             )
           ORDER BY datetime(s.cutoff_at),s.id,
             CASE t.stage WHEN 'pick' THEN 1 WHEN 'move' THEN 2
                          WHEN 'pack_feed' THEN 3 ELSE 4 END,t.id""",
        (order_id,),
    ).fetchall()
    for task in queued:
        resource, kind, reasons = _choose(db, task, source_rows, now, used)
        if not resource:
            reason = "WAITING_FOR_RESOURCE: " + "; ".join(reasons[:8])
            db.execute(
                "UPDATE tasks SET wait_reason=? WHERE id=?", (reason, task["id"])
            )
            db.execute(
                "UPDATE sub_orders SET status='reserved',hold_reason=? WHERE id=?",
                (reason, task["sub_order_id"]),
            )
            _update_parent(db, order_id)
            continue
        duration_seconds = task_duration_seconds(db)
        changed = db.execute(
            """UPDATE tasks SET status='running',resource_id=?,resource_type=?,
                 started_at=?,due_at=?,duration_seconds=?,wait_reason=NULL,
                 assignment_version=assignment_version+1
               WHERE id=? AND status='queued'""",
            (
                resource,
                kind,
                _iso(now),
                _iso(now + timedelta(seconds=duration_seconds)),
                duration_seconds,
                task["id"],
            ),
        ).rowcount
        if not changed:
            continue
        counts["assigned"] += 1
        used.add(resource)
        db.execute(
            "DELETE FROM task_recovery_preferences WHERE task_id=?", (task["id"],)
        )
        db.execute(
            "UPDATE sub_orders SET status='running',hold_reason=NULL WHERE id=?",
            (task["sub_order_id"],),
        )
        _update_parent(db, order_id)
        append_event(
            db,
            order_id,
            f"Policy v2 trigger planner {task['stage']} acquired {resource}",
            now,
        )
    _update_parent(db, order_id)
    robot_lifecycle.reconcile(db, now, source_rows)
    return counts


def executor_once(
    db: sqlite3.Connection, now: datetime, source_rows: Any, append_event: Any,
    force_assignment: bool = False, stats: dict | None = None,
) -> int:
    import persona_v2
    supplied_source_rows = source_rows
    effective_cache = {}
    def source_rows(dataset):
        if dataset not in effective_cache:
            effective_cache[dataset] = persona_v2.effective_source_rows(
                db, dataset, supplied_source_rows(dataset))
        return effective_cache[dataset]
    robot_lifecycle.reconcile(db, now, source_rows)
    assign = robot_lifecycle.assignment_due(db, now, force_assignment)
    counts = stats if stats is not None else {}
    counts.update(assigned=0, resumed=0, rechecked=0, still_waiting=0)
    if assign:
        counts["rechecked"] = db.execute("SELECT count(*) FROM sub_orders WHERE status='held'").fetchone()[0]
        reevaluate_held(db, now)
    completed = 0
    # A safety/readiness correction can recover paused simulated work without
    # replaying a completed stage. The old claim remains protected until this
    # atomic transition clears it.
    paused = db.execute(
        """SELECT t.* FROM tasks t JOIN orders o ON o.id=t.order_id
           WHERE o.policy_version=2 AND t.status='paused'
           ORDER BY t.id"""
    ).fetchall()
    for task in paused:
        if not assign:
            continue
        explicit_failure = db.execute(
            """SELECT 1 FROM lifecycle_demo_failures
               WHERE task_id=? AND resolved_at IS NULL""",
            (task["id"],),
        ).fetchone()
        if explicit_failure:
            # Source readiness never heals an explicit operator failure.
            continue
        ready, _ = _assigned_readiness(db, task, source_rows, now)
        if ready:
            counts["resumed"] += 1
            db.execute(
                """UPDATE tasks SET status='queued',resource_id=NULL,resource_type=NULL,
                   started_at=NULL,due_at=NULL,wait_reason=NULL WHERE id=? AND status='paused'""",
                (task["id"],),
            )
            db.execute(
                "UPDATE sub_orders SET status='queued',hold_reason=NULL WHERE id=?",
                (task["sub_order_id"],),
            )
    due = db.execute(
        """SELECT t.* FROM tasks t JOIN orders o ON o.id=t.order_id
           WHERE o.policy_version=2 AND t.status='running'
             AND NOT EXISTS (
               SELECT 1 FROM lifecycle_demo_failures f
               WHERE f.task_id=t.id AND f.resolved_at IS NULL
             )
           ORDER BY t.due_at,t.id""",
        (),
    ).fetchall()
    for task in due:
        ready, reasons = _assigned_readiness(db, task, source_rows, now)
        if not ready:
            reason = "WAITING_FOR_RESOURCE: assigned resource became ineligible: " + "; ".join(reasons)
            db.execute(
                "UPDATE tasks SET status='paused',wait_reason=? WHERE id=? AND status='running'",
                (reason, task["id"]),
            )
            db.execute(
                "UPDATE sub_orders SET status='reserved',hold_reason=? WHERE id=?",
                (reason, task["sub_order_id"]),
            )
            _update_parent(db, task["order_id"])
            append_event(db, task["order_id"], reason, now)
            continue
        if task["due_at"] and task["due_at"] <= _iso(now) and _complete(db, task, now):
            completed += 1
            append_event(db, task["order_id"], f"Policy v2 {task['stage']} completed", now)
    # Release completed claims and apply automatic low-battery docking before
    # considering any newly queued work in this same transaction.
    robot_lifecycle.reconcile(db, now, source_rows)
    if not assign:
        counts["still_waiting"] = db.execute(
            "SELECT count(*) FROM sub_orders WHERE status IN ('held','reserved','queued')"
        ).fetchone()[0]
        return completed
    used = {
        row[0]
        for row in db.execute(
            """SELECT t.resource_id FROM tasks t JOIN orders o ON o.id=t.order_id
               WHERE t.resource_id IS NOT NULL AND
                 (t.status IN ('running','paused') OR
                   0)"""
        )
    }
    try:
        used.update(
            row[0]
            for row in db.execute(
                """SELECT tr.resource_id FROM task_resources tr
                   JOIN tasks t ON t.id=tr.task_id
                   WHERE t.status IN ('pending','queued','running','paused')"""
            )
        )
    except sqlite3.OperationalError:
        pass
    queued = db.execute(
        """SELECT t.* FROM tasks t JOIN sub_orders s ON s.id=t.sub_order_id
           JOIN orders o ON o.id=t.order_id
           WHERE o.policy_version=2 AND t.status='queued'
             AND NOT EXISTS (
               SELECT 1 FROM lifecycle_demo_failures f
               WHERE f.task_id=t.id AND f.resolved_at IS NULL
             )
           ORDER BY datetime(s.cutoff_at),s.id,
             CASE t.stage WHEN 'pick' THEN 1 WHEN 'move' THEN 2
                          WHEN 'pack_feed' THEN 3 ELSE 4 END,t.id"""
    ).fetchall()
    for task in queued:
        counts["rechecked"] += 1
        resource, kind, reasons = _choose(db, task, source_rows, now, used)
        if not resource:
            reason = "WAITING_FOR_RESOURCE: " + "; ".join(reasons[:8])
            db.execute("UPDATE tasks SET wait_reason=? WHERE id=?", (reason, task["id"]))
            db.execute(
                "UPDATE sub_orders SET status='reserved',hold_reason=? WHERE id=?",
                (reason, task["sub_order_id"]),
            )
            _update_parent(db, task["order_id"])
            continue
        duration_seconds = task_duration_seconds(db)
        due_at = now + timedelta(seconds=duration_seconds)
        if db.execute(
            """UPDATE tasks SET status='running',resource_id=?,resource_type=?,
               started_at=?,due_at=?,duration_seconds=?,wait_reason=NULL,
               assignment_version=assignment_version+1
               WHERE id=? AND status='queued'""",
            (resource, kind, _iso(now), _iso(due_at), duration_seconds, task["id"]),
        ).rowcount:
            counts["assigned"] += 1
            db.execute("DELETE FROM task_recovery_preferences WHERE task_id=?", (task["id"],))
            used.add(resource)
            db.execute(
                "UPDATE sub_orders SET status='running',hold_reason=NULL WHERE id=?",
                (task["sub_order_id"],),
            )
            _update_parent(db, task["order_id"])
            append_event(db, task["order_id"], f"Policy v2 {task['stage']} acquired {resource}", now)
    counts["still_waiting"] = db.execute("SELECT count(*) FROM sub_orders WHERE status IN ('held','reserved','queued')").fetchone()[0]
    robot_lifecycle.reconcile(db, now, source_rows)
    return completed