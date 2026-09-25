"""Transparent warehouse/SKU demand forecasts backed by operational SQLite data."""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
LOOKBACK_DAYS = 60
LEGACY_METHOD = "mean_daily_ordered_units_completed_ist_days_v1"
METHOD = "mean_daily_ordered_units_completed_ist_days_60d_v2"
SCHEDULED_TIME = "06:00"
TIMEZONE = "Asia/Kolkata"
logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None


def run_lookback_days(run: sqlite3.Row) -> int:
    """Describe the saved calculation, not the current scheduler setting."""
    return {LEGACY_METHOD: 30, METHOD: LOOKBACK_DAYS}[run["method"]]


def ensure_schema(db: sqlite3.Connection) -> None:
    """Create forecast storage without committing a caller-owned transaction."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS demand_forecast_runs (
             id TEXT PRIMARY KEY,
             forecast_date TEXT NOT NULL UNIQUE,
             generated_at TEXT NOT NULL,
             window_start TEXT NOT NULL,
             window_end TEXT NOT NULL,
             method TEXT NOT NULL,
             excluded_unassigned_units INTEGER NOT NULL DEFAULT 0
           )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS demand_forecasts (
             run_id TEXT NOT NULL REFERENCES demand_forecast_runs(id) ON DELETE CASCADE,
             warehouse_id TEXT NOT NULL,
             sku TEXT NOT NULL,
             daily_demand REAL NOT NULL,
             forecast_7d INTEGER NOT NULL,
             forecast_30d INTEGER NOT NULL,
             history_units INTEGER NOT NULL,
             history_days INTEGER NOT NULL,
             history_status TEXT NOT NULL,
             PRIMARY KEY(run_id,warehouse_id,sku)
           )"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS demand_forecasts_lookup "
        "ON demand_forecasts(warehouse_id,sku,run_id)"
    )
    # A separate marker distinguishes a captured empty window from legacy
    # evidence that was never recorded. Evidence is retained by immutable run ID
    # when its parent run moves to the superseded archive.
    db.execute(
        """CREATE TABLE IF NOT EXISTS demand_forecast_captures (
             run_id TEXT PRIMARY KEY
           )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS demand_forecast_daily_inputs (
             run_id TEXT NOT NULL,
             warehouse_id TEXT NOT NULL,
             sku TEXT NOT NULL,
             date TEXT NOT NULL,
             ordered_units INTEGER NOT NULL,
             PRIMARY KEY(run_id,warehouse_id,sku,date)
           )"""
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def expected_forecast_date(now: datetime) -> date:
    """Return the latest scheduled business date, using real IST wall time."""
    local = now.astimezone(IST)
    if local.timetz().replace(tzinfo=None) < time(6):
        return local.date() - timedelta(days=1)
    return local.date()


def next_scheduled_at(now: datetime) -> datetime:
    local = now.astimezone(IST)
    candidate = datetime.combine(local.date(), time(6), IST)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def _order_rows(db: sqlite3.Connection) -> list[sqlite3.Row]:
    """Read the canonical demand source once; never join allocations or tasks."""
    return db.execute(
        """SELECT s.warehouse_id,s.sku,s.quantity,s.status AS sub_status,
                  o.status AS order_status,
                  COALESCE(o.order_created_at,o.created_at) AS demand_at
           FROM sub_orders s
           JOIN orders o ON o.id=s.order_id"""
    ).fetchall()


def generate(
    db: sqlite3.Connection,
    forecast_date: date,
    generated_at: datetime,
) -> dict[str, Any]:
    """Persist one all-catalog daily snapshot inside the caller's transaction."""
    ensure_schema(db)
    existing = db.execute(
        "SELECT id FROM demand_forecast_runs WHERE forecast_date=?",
        (forecast_date.isoformat(),),
    ).fetchone()
    if existing:
        return {"run_id": existing["id"], "created": False}

    window_end_local = datetime.combine(forecast_date, time.min, IST)
    window_start_local = window_end_local - timedelta(days=LOOKBACK_DAYS)
    order_rows = _order_rows(db)
    dated_rows: list[tuple[sqlite3.Row, datetime]] = []
    earliest: date | None = None
    for row in order_rows:
        stamp = _parse_timestamp(row["demand_at"])
        if stamp is None:
            continue
        local = stamp.astimezone(IST)
        # A historical import is not proof of continuing observation after its
        # last record. Never let out-of-window records establish coverage.
        if local >= window_end_local or local < window_start_local:
            continue
        if str(row["order_status"]).lower() == "cancelled":
            continue
        if str(row["sub_status"]).lower() == "cancelled":
            continue
        dated_rows.append((row, local))
        earliest = local.date() if earliest is None else min(earliest, local.date())

    history_days = (
        min(LOOKBACK_DAYS, max(1, (forecast_date - earliest).days))
        if earliest is not None and earliest < forecast_date
        else 0
    )
    effective_start = window_end_local - timedelta(days=history_days)
    units: dict[tuple[str, str], int] = {}
    buckets: dict[tuple[str, str, str], int] = {}
    excluded = 0
    for row, local in dated_rows:
        quantity = max(0, int(row["quantity"] or 0))
        if local < effective_start:
            continue
        warehouse = str(row["warehouse_id"] or "").strip()
        if not warehouse:
            excluded += quantity
            continue
        key = (warehouse, str(row["sku"]))
        units[key] = units.get(key, 0) + quantity
        bucket = (*key, local.date().isoformat())
        buckets[bucket] = buckets.get(bucket, 0) + quantity

    catalog = [
        (str(row["warehouse_id"]), str(row["sku"]))
        for row in db.execute(
            "SELECT DISTINCT warehouse_id,sku FROM inventory_snapshot "
            "WHERE warehouse_id!='' AND sku!='' ORDER BY warehouse_id,sku"
        )
    ]
    run_id = f"DFR-{uuid.uuid4()}"
    db.execute(
        """INSERT INTO demand_forecast_runs(
             id,forecast_date,generated_at,window_start,window_end,method,
             excluded_unassigned_units) VALUES (?,?,?,?,?,?,?)""",
        (
            run_id,
            forecast_date.isoformat(),
            generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            effective_start.isoformat(),
            window_end_local.isoformat(),
            METHOD,
            excluded,
        ),
    )
    values = []
    for warehouse, sku in catalog:
        history_units = units.get((warehouse, sku), 0)
        daily = history_units / history_days if history_days else 0.0
        if history_units <= 0:
            history_status = "no_history"
        elif history_days < LOOKBACK_DAYS:
            history_status = "short_history"
        else:
            history_status = "observed"
        values.append(
            (
                run_id,
                warehouse,
                sku,
                daily,
                (
                    (history_units * 7 + history_days - 1) // history_days
                    if history_days
                    else 0
                ),
                (
                    (history_units * 30 + history_days - 1) // history_days
                    if history_days
                    else 0
                ),
                history_units,
                history_days,
                history_status,
            )
        )
    db.executemany(
        """INSERT INTO demand_forecasts(
             run_id,warehouse_id,sku,daily_demand,forecast_7d,forecast_30d,
             history_units,history_days,history_status) VALUES (?,?,?,?,?,?,?,?,?)""",
        values,
    )
    db.execute("INSERT INTO demand_forecast_captures VALUES (?)", (run_id,))
    db.executemany(
        "INSERT INTO demand_forecast_daily_inputs VALUES (?,?,?,?,?)",
        [(run_id, warehouse, sku, day, quantity)
         for (warehouse, sku, day), quantity in buckets.items()],
    )
    return {"run_id": run_id, "created": True}


def ensure_due_run(
    transaction: Callable[[], Any],
    now: datetime,
) -> dict[str, Any]:
    """Create only the latest scheduled business-date run, including first install."""
    with transaction() as db:
        ensure_schema(db)
        business_date = expected_forecast_date(now)
        return generate(db, business_date, now)


def refresh_current(db: sqlite3.Connection, now: datetime) -> dict[str, Any]:
    """Explicit maintenance refresh; preserve the superseded snapshot verbatim.

    Normal scheduled generation stays idempotent. Imports call this inside the
    same transaction as their graph writes, so projections cannot describe a
    partially imported dataset. Prior business dates remain untouched.
    """
    if not db.in_transaction:
        raise ValueError("Forecast refresh requires a caller-owned transaction")
    ensure_schema(db)
    business_date = expected_forecast_date(now)
    old = db.execute(
        "SELECT * FROM demand_forecast_runs WHERE forecast_date=?",
        (business_date.isoformat(),),
    ).fetchone()
    archived_id = None
    if old:
        archived_id = old["id"]
        db.execute(
            """CREATE TABLE IF NOT EXISTS demand_forecast_superseded_runs AS
               SELECT *,CAST(NULL AS TEXT) AS superseded_at
               FROM demand_forecast_runs WHERE 0"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS demand_forecast_superseded_values AS
               SELECT * FROM demand_forecasts WHERE 0"""
        )
        db.execute(
            "INSERT INTO demand_forecast_superseded_runs SELECT *,? "
            "FROM demand_forecast_runs WHERE id=?",
            (now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), archived_id),
        )
        db.execute(
            "INSERT INTO demand_forecast_superseded_values "
            "SELECT * FROM demand_forecasts WHERE run_id=?", (archived_id,),
        )
        db.execute("DELETE FROM demand_forecasts WHERE run_id=?", (archived_id,))
        db.execute("DELETE FROM demand_forecast_runs WHERE id=?", (archived_id,))
    return {**generate(db, business_date, now), "superseded_run_id": archived_id}


def latest_run(db: sqlite3.Connection) -> sqlite3.Row | None:
    ensure_schema(db)
    return db.execute(
        "SELECT * FROM demand_forecast_runs ORDER BY forecast_date DESC LIMIT 1"
    ).fetchone()


def saved_detail(
    db: sqlite3.Connection, warehouse_id: str, sku: str, run_id: str | None = None,
) -> dict[str, Any] | None:
    """Read saved evidence only; never reconstruct a legacy run from orders."""
    ensure_schema(db)
    run = latest_run(db) if run_id is None else db.execute(
        "SELECT * FROM demand_forecast_runs WHERE id=?", (run_id,),
    ).fetchone()
    values_table = "demand_forecasts"
    if run is None and run_id is not None and db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='demand_forecast_superseded_runs'"
    ).fetchone():
        run = db.execute(
            "SELECT * FROM demand_forecast_superseded_runs WHERE id=?", (run_id,),
        ).fetchone()
        values_table = "demand_forecast_superseded_values"
    if run is None:
        return None
    item = db.execute(
        f"SELECT * FROM {values_table} WHERE run_id=? AND warehouse_id=? AND sku=?",
        (run["id"], warehouse_id, sku),
    ).fetchone()
    if item is None:
        return None
    captured = db.execute(
        "SELECT 1 FROM demand_forecast_captures WHERE run_id=?", (run["id"],),
    ).fetchone() is not None
    history = []
    if captured:
        buckets = {row["date"]: row["ordered_units"] for row in db.execute(
            "SELECT date,ordered_units FROM demand_forecast_daily_inputs "
            "WHERE run_id=? AND warehouse_id=? AND sku=?",
            (run["id"], warehouse_id, sku),
        )}
        start = datetime.fromisoformat(run["window_start"]).date()
        for index in range(item["history_days"]):
            day = (start + timedelta(days=index)).isoformat()
            history.append({"date": day, "ordered_units": buckets.get(day, 0),
                            "rolling_7d": None})
            if index >= 6:
                history[-1]["rolling_7d"] = sum(
                    entry["ordered_units"] for entry in history[-7:]
                ) / 7
    forecast_date = date.fromisoformat(run["forecast_date"])
    return {
        "run": dict(run), "item": dict(item), "history_available": captured,
        "history": history,
        "projection": [
            {"date": (forecast_date + timedelta(days=index)).isoformat(),
             "daily_demand": item["daily_demand"]}
            for index in range(30)
        ],
    }


def current_thresholds(db: sqlite3.Connection) -> tuple[sqlite3.Row | None, dict[tuple[str, str], dict[str, Any]]]:
    run = latest_run(db)
    if run is None:
        return None, {}
    rows = {
        (row["warehouse_id"], row["sku"]): dict(row)
        for row in db.execute(
            "SELECT * FROM demand_forecasts WHERE run_id=?", (run["id"],)
        )
    }
    return run, rows


def start(transaction: Callable[[], Any]) -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()

    def loop() -> None:
        while not _stop.is_set():
            try:
                # Deliberately use real wall-clock time, not the simulator clock.
                ensure_due_run(transaction, datetime.now(timezone.utc))
            except Exception:
                logger.exception("Scheduled demand forecast failed; retaining previous valid run")
                # Retry transient database/source failures without waiting a
                # full day. Idempotence makes a race-safe retry harmless.
                if _stop.wait(60):
                    break
                continue
            now = datetime.now(timezone.utc)
            wait = max(1.0, (next_scheduled_at(now) - now).total_seconds())
            if _stop.wait(wait):
                break

    _thread = threading.Thread(target=loop, name="demand-forecast-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    global _thread
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2)
    _thread = None


if __name__ == "__main__":
    import argparse
    import json
    from contextlib import closing
    from pathlib import Path
    from maintenance_lock import exclusive_maintenance

    parser = argparse.ArgumentParser(description="Explicit audited current forecast refresh")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--refresh-current", action="store_true", required=True)
    args = parser.parse_args()
    path = args.db.resolve()
    if not path.is_file():
        parser.error("Database must already exist")
    now = datetime.now(timezone.utc)
    with exclusive_maintenance(path.parent):
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"before-forecast-refresh-{now.strftime('%Y%m%dT%H%M%S%fZ')}.sqlite"
        with closing(sqlite3.connect(path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with closing(sqlite3.connect(backup_path)) as backup:
                db.backup(backup)
            db.execute("BEGIN IMMEDIATE")
            try:
                result = refresh_current(db, now)
                db.commit()
            except BaseException:
                db.rollback()
                raise
    print(json.dumps({**result, "backup": str(backup_path)}, indent=2))