"""Read-only replay evidence; merged identities resolve to ordinary operations."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse

from persona_api import _role

ROOT = Path(__file__).resolve().parent / ".local" / "replays"
router = APIRouter(prefix="/api/fulfillment/replays", tags=["fulfillment-replays"])


def _authorize(persona: str | None) -> None:
    if _role(persona) not in {"supervisor", "admin"}:
        raise HTTPException(403, "Replay results require supervisor or admin persona")


def _directory(run_id: str) -> Path:
    try:
        normalized = str(uuid.UUID(run_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(404, "Replay not found") from exc
    if normalized != run_id.lower():
        raise HTTPException(404, "Replay not found")
    return ROOT / normalized


def _manifest(run_id: str) -> dict:
    path = _directory(run_id) / "manifest.json"
    if not path.is_file():
        raise HTTPException(404, "Replay not found")
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "Replay manifest is unavailable") from exc


@contextmanager
def _db(run_id: str):
    path = _directory(run_id) / "simulation.sqlite"
    if not path.is_file():
        raise HTTPException(409, "Replay database is not ready")
    db: sqlite3.Connection | None = None
    try:
        # Do not use immutable=1: a running replay writes through WAL and readers
        # must participate in normal SQLite locking/checkpoint visibility.
        db = sqlite3.connect(
            f"file:{path.resolve()}?mode=ro", uri=True, timeout=1
        )
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA busy_timeout=1000")
        db.execute("BEGIN")
        yield db
    except sqlite3.OperationalError as exc:
        raise HTTPException(503, "Replay results are temporarily unavailable") from exc
    finally:
        if db is not None:
            if db.in_transaction:
                db.rollback()
            db.close()


def _row(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in (
        "source_order_id", "core_order_id", "warehouse_id", "sku", "quantity",
        "priority", "created_at", "cutoff", "status", "finished_at",
        "cycle_time_seconds", "benchmark_actual_departure",
        "benchmark_cycle_time_seconds", "reason",
    )}

def _unified_target(run_id: str, source_order_id: str | None = None) -> str | None:
    """Resolve by both business and idempotency identity, never archive status.

    Opening both files read-only deliberately avoids the operational initializer
    and lifecycle/write transactions. A complete imported run has no second
    order-list authority; individual imported rows redirect even during a merge.
    """
    # Do not import fulfillment_api here: its module initializer writes schema.
    db_path = Path(getattr(sys.modules.get("fulfillment_api"), "DB_PATH",
                          os.environ.get("FULFILLMENT_DB_PATH", ROOT.parent / "fulfillment.sqlite")))
    if not db_path.is_file() or not (_directory(run_id) / "simulation.sqlite").is_file():
        return None
    with _db(run_id) as db:
        archive_columns = {row["name"] for row in db.execute("PRAGMA table_info(replay_orders)")}
        if not {"source_order_id", "request_id"} <= archive_columns:
            return None
        db.execute("ATTACH DATABASE ? AS operational", (f"file:{db_path.resolve()}?mode=ro",))
        # An older, uninitialized operational schema cannot contain merged rows.
        columns = {row["name"] for row in db.execute("PRAGMA operational.table_info(orders)")}
        if not {"source_order_id", "request_id", "id"} <= columns:
            return None
        join = """FROM replay_orders r JOIN operational.orders o
                  ON o.source_order_id=r.source_order_id AND o.request_id=r.request_id"""
        if source_order_id is not None:
            row = db.execute(f"SELECT o.id {join} WHERE r.source_order_id=?", (source_order_id,)).fetchone()
            return f"/api/fulfillment/orders/{quote(row['id'], safe='')}" if row else None
        total = db.execute("SELECT count(*) FROM replay_orders").fetchone()[0]
        matched = db.execute(f"SELECT count(DISTINCT r.source_order_id) {join}").fetchone()[0]
        return "/api/fulfillment/orders" if total > 0 and matched == total else None


def _summary(run_id: str, manifest: dict) -> dict:
    target = _unified_target(run_id)
    if target:
        # Archived counters are evidence, not a live fulfillment dashboard.
        return {
            "run_id": run_id,
            "started_at": manifest.get("started_at"),
            "status": "available",
            "unified_url": target.removeprefix("/api"),
        }
    return _running_summary(run_id, manifest)


def _effective_select() -> str:
    """Project live engine truth without mutating in-progress replay rows."""

    return """
      SELECT r.source_order_id,COALESCE(r.core_order_id,o.id) AS core_order_id,
             r.warehouse_id,r.sku,r.quantity,r.priority,r.created_at,r.cutoff,
             CASE WHEN r.status='rejected' THEN 'rejected'
                  WHEN o.id IS NULL THEN r.status ELSE o.status END AS status,
             CASE WHEN o.status='completed' THEN x.finished_at END AS finished_at,
             CASE WHEN o.status='completed' AND x.finished_at IS NOT NULL
                  THEN (julianday(x.finished_at)-julianday(r.created_at))*86400 END
                  AS cycle_time_seconds,
             r.benchmark_actual_departure,r.benchmark_cycle_time_seconds,
             CASE WHEN r.status='rejected' THEN r.reason
                  WHEN o.id IS NOT NULL THEN o.issues_json ELSE r.reason END AS reason,
             r.input_json,r.benchmark_json
      FROM replay_orders r
      LEFT JOIN orders o ON o.source_order_id=r.source_order_id
      LEFT JOIN (
        SELECT order_id,max(completed_at) AS finished_at
        FROM tasks WHERE completed_at IS NOT NULL GROUP BY order_id
      ) x ON x.order_id=o.id
    """


def _running_summary(run_id: str, manifest: dict) -> dict:
    if manifest.get("status") != "running":
        return manifest
    try:
        with _db(run_id) as db:
            rows = db.execute(
                f"""SELECT status,count(*) AS count,
                           avg(cycle_time_seconds) AS cycle,
                           avg(finished_at<=cutoff) AS on_time
                    FROM ({_effective_select()})
                    GROUP BY status"""
            ).fetchall()
            benchmark = db.execute(
                """SELECT avg(benchmark_cycle_time_seconds) AS cycle,
                          avg(benchmark_actual_departure<=benchmark_planned_departure)
                            AS on_time
                   FROM replay_orders"""
            ).fetchone()
    except HTTPException as exc:
        # During preparation the manifest remains the sole progress authority.
        if exc.status_code in {409, 503}:
            return manifest
        raise
    counts = {str(row["status"]): int(row["count"]) for row in rows}
    # The manifest is checkpointed every 100 arrivals. Mixing its older cursor
    # with current engine counts can show more completions than accepted orders.
    processed = sum(counts.values()) - counts.get("pending", 0)
    rejected = counts.get("rejected", 0)
    completed = counts.get("completed", 0)
    held = counts.get("held", 0)
    known = rejected + completed + held
    accepted = max(0, processed - rejected)
    completion_metrics = next((row for row in rows if row["status"] == "completed"), None)
    return {
        **manifest,
        "processed_orders": processed,
        "accepted_orders": accepted,
        "rejected_orders": rejected,
        "completed_orders": completed,
        "held_orders": held,
        "other_orders": max(0, processed - known),
        "metrics": {
            "simulated_average_cycle_seconds": completion_metrics["cycle"] if completion_metrics else None,
            "simulated_on_time_percent": completion_metrics["on_time"] * 100
                if completion_metrics and completion_metrics["on_time"] is not None else None,
            "benchmark_average_cycle_seconds": benchmark["cycle"],
            "benchmark_on_time_percent": benchmark["on_time"] * 100
                if benchmark["on_time"] is not None else None,
        },
    }


@router.get("")
def collection(x_demo_persona: str | None = Header(None, alias="X-Demo-Persona")):
    _authorize(x_demo_persona)
    items = []
    if ROOT.is_dir():
        for path in sorted(ROOT.iterdir(), reverse=True):
            if path.is_dir():
                try:
                    items.append(_summary(path.name, _manifest(path.name)))
                except HTTPException as exc:
                    if exc.status_code != 404:
                        raise
    items.sort(key=lambda item: str(item.get("started_at") or ""), reverse=True)
    return {"items": items}


@router.get("/{run_id}")
def summary(run_id: str, x_demo_persona: str | None = Header(None, alias="X-Demo-Persona")):
    _authorize(x_demo_persona)
    return _summary(run_id, _manifest(run_id))


@router.get("/{run_id}/orders")
def orders(
    run_id: str,
    status: str | None = Query(None, max_length=40),
    warehouse: str | None = Query(None, max_length=64),
    search: str | None = Query(None, max_length=100),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    x_demo_persona: str | None = Header(None, alias="X-Demo-Persona"),
):
    _authorize(x_demo_persona)
    status = status if isinstance(status, str) else None
    warehouse = warehouse if isinstance(warehouse, str) else None
    search = search if isinstance(search, str) else None
    limit = limit if isinstance(limit, int) else 25
    offset = offset if isinstance(offset, int) else 0
    target = _unified_target(run_id)
    if target:
        filters = {"limit": limit, "offset": offset}
        filters.update({key: value for key, value in (
            ("status", status), ("warehouse", warehouse), ("search", search)
        ) if value})
        return RedirectResponse(f"{target}?{urlencode(filters)}", status_code=307)
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    if warehouse:
        clauses.append("warehouse_id=?")
        params.append(warehouse)
    if search:
        clauses.append("(source_order_id LIKE ? OR core_order_id LIKE ? OR sku LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _db(run_id) as db:
        manifest = _manifest(run_id)
        source = (
            f"({_effective_select()}) effective"
            if manifest.get("status") == "running"
            else "replay_orders"
        )
        total = db.execute(f"SELECT count(*) FROM {source}{where}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM {source}{where} ORDER BY created_at,source_order_id LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return {"items": [_row(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{run_id}/orders/{source_order_id}")
def order_detail(
    run_id: str, source_order_id: str,
    x_demo_persona: str | None = Header(None, alias="X-Demo-Persona"),
):
    _authorize(x_demo_persona)
    target = _unified_target(run_id, source_order_id)
    if target:
        return RedirectResponse(target, status_code=307)
    with _db(run_id) as db:
        manifest = _manifest(run_id)
        source = (
            f"({_effective_select()}) effective"
            if manifest.get("status") == "running"
            else "replay_orders"
        )
        replay = db.execute(
            f"SELECT * FROM {source} WHERE source_order_id=?", (source_order_id,)
        ).fetchone()
        if not replay:
            raise HTTPException(404, "Replay order not found")
        core_id = replay["core_order_id"]
        tasks = [dict(row) for row in db.execute(
            "SELECT * FROM tasks WHERE order_id=? ORDER BY rowid", (core_id,)
        )] if core_id else []
        allocations = [dict(row) for row in db.execute(
            """SELECT a.* FROM sub_order_allocations a JOIN sub_orders s
               ON s.id=a.sub_order_id WHERE s.order_id=? ORDER BY a.rowid""", (core_id,)
        )] if core_id else []
        events = [dict(row) for row in db.execute(
            "SELECT at,message FROM events WHERE order_id=? ORDER BY id", (core_id,)
        )] if core_id else []
        return {
            "order": _row(replay), "tasks": tasks, "allocations": allocations,
            "events": events, "source": json.loads(replay["input_json"]),
            "benchmark": json.loads(replay["benchmark_json"]),
        }