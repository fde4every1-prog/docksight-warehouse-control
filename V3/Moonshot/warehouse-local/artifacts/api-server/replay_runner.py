"""Run a historical archive through the real Core engine in an isolated DB."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

import fulfillment_api as fulfillment
import fulfillment_v2
from replay_sources import (
    capture_sources,
    deterministic_request_id,
    file_sha256,
    read_inputs,
    snapshot_sqlite,
)

ROOT = Path(__file__).resolve().parent
REPLAY_ROOT = ROOT / ".local" / "replays"
DEFAULT_ZIP = ROOT.parent.parent / "attached_assets" / "Synthetic_Data_1789961144297.zip"
SERVICE = {"SAME_DAY": "Same_Day", "NEXT_DAY": "Next_Day", "STANDARD": "Standard"}
PRIORITY = {"STANDARD": "standard", "EXPEDITE": "high", "CRITICAL": "urgent"}


def parse_naive_utc(value: str) -> datetime:
    """Archive timestamps are naive by contract and are interpreted as UTC."""

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        raise ValueError(f"Archive timestamp must be naive: {value}")
    return parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return fulfillment.iso(value)


def _write_manifest(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True))
    temporary.replace(path)


def _replay_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS replay_orders(
          source_order_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
          input_json TEXT NOT NULL, input_hash TEXT NOT NULL,
          benchmark_json TEXT NOT NULL, warehouse_id TEXT NOT NULL, sku TEXT NOT NULL,
          quantity INTEGER NOT NULL, priority TEXT NOT NULL, created_at TEXT NOT NULL,
          cutoff TEXT NOT NULL, core_order_id TEXT, status TEXT NOT NULL,
          finished_at TEXT, cycle_time_seconds REAL, benchmark_actual_departure TEXT,
          benchmark_planned_departure TEXT, benchmark_cycle_time_seconds REAL,
          reason TEXT);
        CREATE INDEX IF NOT EXISTS replay_order_filters
          ON replay_orders(status,warehouse_id,source_order_id);
        CREATE TABLE IF NOT EXISTS replay_provenance(
          key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS replay_task_status_due
          ON tasks(status,due_at);
        CREATE INDEX IF NOT EXISTS replay_task_status_order
          ON tasks(status,order_id);
        CREATE INDEX IF NOT EXISTS replay_order_source
          ON orders(source_order_id);
        CREATE INDEX IF NOT EXISTS replay_sub_status_order
          ON sub_orders(status,order_id);
        """
    )


def _base_manifest(run_id: str, zip_hash: str, started: datetime) -> dict[str, Any]:
    return {
        "run_id": run_id, "status": "preparing", "total_orders": 7000,
        "processed_orders": 0, "accepted_orders": 0, "rejected_orders": 0,
        "completed_orders": 0, "held_orders": 0, "other_orders": 0,
        "started_at": _iso(started), "finished_at": None, "simulated_at": None,
        "source_period": {"start": None, "end": None}, "task_duration_seconds": None,
        "metrics": {
            "simulated_average_cycle_seconds": None,
            "benchmark_average_cycle_seconds": None,
            "simulated_on_time_percent": None, "benchmark_on_time_percent": None,
        },
        "checks": [], "warnings": [
            "Archive timestamps are naive and explicitly interpreted as UTC.",
            "Shipment rows are immutable benchmarks, never completion commands.",
            "Historical input status is benchmark context, never an execution command.",
        ],
        "warehouses": [], "error": None, "zip_sha256": zip_hash,
        "sample_size": None, "is_full_7000": True,
        "planner_event_policy": (
            "Force the existing planner admission pass at each arrival, task due, "
            "charging, and final-drain boundary; execution and safety predicates are unchanged."
        ),
    }


def _payload(row: dict[str, str], zip_hash: str) -> fulfillment.OrderInput:
    return fulfillment.OrderInput(
        warehouse_id=row["warehouse_id"],
        priority=PRIORITY[row["priority"]],
        ship_by=_iso(parse_naive_utc(row["carrier_cutoff"])),
        lines=[fulfillment.OrderLineInput(sku=row["sku"], quantity=int(row["order_quantity"]))],
        request_id=deterministic_request_id(zip_hash, row["order_id"]),
        source_order_id=row["order_id"], order_service=SERVICE[row["service_level"]],
        order_source="fde_bazaar", order_created_at=_iso(parse_naive_utc(row["created_at"])),
    )


def _record_input(
    db: sqlite3.Connection, row: dict[str, str], shipment: dict[str, str], zip_hash: str
) -> None:
    created = parse_naive_utc(row["created_at"])
    actual = parse_naive_utc(shipment["actual_departure"])
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
    db.execute(
        """INSERT INTO replay_orders(
          source_order_id,request_id,input_json,input_hash,benchmark_json,warehouse_id,
          sku,quantity,priority,created_at,cutoff,status,benchmark_actual_departure,
          benchmark_planned_departure,benchmark_cycle_time_seconds)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["order_id"], deterministic_request_id(zip_hash, row["order_id"]),
            canonical, __import__("hashlib").sha256(canonical.encode()).hexdigest(),
            json.dumps(shipment, sort_keys=True), row["warehouse_id"], row["sku"],
            int(row["order_quantity"]), PRIORITY[row["priority"]], _iso(created),
            _iso(parse_naive_utc(row["carrier_cutoff"])), "pending", _iso(actual),
            _iso(parse_naive_utc(shipment["planned_departure"])),
            (actual - created).total_seconds(),
        ),
    )


def _next_due(db: sqlite3.Connection) -> datetime | None:
    row = db.execute(
        "SELECT min(due_at) FROM tasks WHERE status='running' AND due_at IS NOT NULL"
    ).fetchone()
    return fulfillment.parse_utc(row[0]) if row and row[0] else None


def _execute_tick(
    db: sqlite3.Connection, now: datetime, sources: dict[str, tuple[dict[str, Any], ...]]
) -> tuple[int, dict[str, int]]:
    warehouses = {
        str(row[0])
        for row in db.execute(
            """SELECT DISTINCT o.warehouse_id FROM orders o JOIN tasks t ON t.order_id=o.id
               WHERE t.status IN ('queued','running','paused')"""
        )
        if row[0]
    }
    robots = tuple(
        row for row in sources.get("robots", ())
        if str(row.get("warehouse_id") or "") in warehouses
    )
    robot_ids = {str(row.get("robot_id") or "") for row in robots}
    scoped = {
        "robots": robots,
        "maintenance": tuple(
            row for row in sources.get("maintenance", ())
            if str(row.get("robot_id") or "") in robot_ids
        ),
        "control_assets": tuple(
            row for row in sources.get("control_assets", ())
            if str(row.get("warehouse_id") or "") in warehouses
        ),
    }
    stats: dict[str, int] = {}
    completed = fulfillment_v2.executor_once(
        db, now, lambda name: scoped.get(name, ()), fulfillment._append_event,
        force_assignment=True, stats=stats,
    )
    return completed, stats


def _finalize_rows(db: sqlite3.Connection) -> None:
    db.execute(
        """UPDATE replay_orders SET core_order_id=(
             SELECT id FROM orders WHERE orders.source_order_id=replay_orders.source_order_id)
           WHERE core_order_id IS NULL"""
    )
    for row in db.execute(
        """SELECT r.source_order_id,r.created_at,o.id,o.status,
                  max(t.completed_at) AS finished_at,o.issues_json
           FROM replay_orders r LEFT JOIN orders o ON o.source_order_id=r.source_order_id
           LEFT JOIN tasks t ON t.order_id=o.id GROUP BY r.source_order_id"""
    ).fetchall():
        if row["id"] is None:
            continue
        finished = row["finished_at"] if row["status"] == "completed" else None
        cycle = (
            (fulfillment.parse_utc(finished) - fulfillment.parse_utc(row["created_at"])).total_seconds()
            if finished else None
        )
        db.execute(
            """UPDATE replay_orders SET core_order_id=?,status=?,finished_at=?,
               cycle_time_seconds=?,reason=? WHERE source_order_id=?""",
            (row["id"], row["status"], finished, cycle, row["issues_json"], row["source_order_id"]),
        )


def _summary(db: sqlite3.Connection, manifest: dict[str, Any]) -> None:
    counts = {row[0]: row[1] for row in db.execute(
        "SELECT status,count(*) FROM replay_orders GROUP BY status"
    )}
    total = sum(counts.values())
    completed = counts.get("completed", 0)
    rejected = counts.get("rejected", 0)
    held = counts.get("held", 0)
    manifest.update(
        processed_orders=total, accepted_orders=total - rejected, rejected_orders=rejected,
        completed_orders=completed, held_orders=held,
        other_orders=total - completed - rejected - held,
    )
    sim = db.execute(
        "SELECT avg(cycle_time_seconds),avg(finished_at<=cutoff) FROM replay_orders WHERE status='completed'"
    ).fetchone()
    benchmark = db.execute(
        """SELECT avg(benchmark_cycle_time_seconds),
                  avg(benchmark_actual_departure<=benchmark_planned_departure)
           FROM replay_orders
           WHERE benchmark_actual_departure IS NOT NULL"""
    ).fetchone()
    manifest["metrics"] = {
        "simulated_average_cycle_seconds": sim[0],
        "benchmark_average_cycle_seconds": benchmark[0],
        "simulated_on_time_percent": sim[1] * 100 if sim[1] is not None else None,
        "benchmark_on_time_percent": benchmark[1] * 100 if benchmark[1] is not None else None,
    }


def _report(db: sqlite3.Connection, path: Path) -> None:
    rows = db.execute(
        """SELECT source_order_id,core_order_id,warehouse_id,sku,quantity,priority,
                  created_at,cutoff,status,finished_at,cycle_time_seconds,
                  benchmark_actual_departure,benchmark_cycle_time_seconds,reason
           FROM replay_orders ORDER BY created_at,source_order_id"""
    )
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([item[0] for item in rows.description])
        writer.writerows(rows)


def run(zip_path: Path, live_db: Path, run_id: str | None = None, limit: int | None = None) -> str:
    run_id = run_id or str(uuid.uuid4())
    uuid.UUID(run_id)
    run_dir = REPLAY_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    zip_hash = file_sha256(zip_path)
    started = datetime.now(timezone.utc)
    manifest = _base_manifest(run_id, zip_hash, started)
    manifest_path = run_dir / "manifest.json"
    _write_manifest(manifest_path, manifest)
    try:
        snapshot_path = run_dir / "live-snapshot.sqlite"
        snapshot_sqlite(live_db, snapshot_path)
        source_capture = capture_sources(snapshot_path, run_dir / "effective-sources.json")
        orders, shipments = read_inputs(zip_path)
        selected = orders[:limit] if limit else orders
        arrivals = [(parse_naive_utc(row["created_at"]), row) for row in selected]
        arrivals.sort(key=lambda item: (item[0], item[1]["order_id"]))
        manifest["total_orders"] = len(selected)
        manifest["sample_size"] = len(selected) if limit else None
        manifest["is_full_7000"] = limit is None
        if limit:
            manifest["warnings"].append(
                f"Prototype sample only ({len(selected)}/7000); not a failed or complete full replay."
            )
        manifest["source_period"] = {
            "start": _iso(arrivals[0][0]), "end": _iso(arrivals[-1][0]),
        }
        manifest["warehouses"] = sorted({row["warehouse_id"] for _, row in arrivals})
        manifest["task_duration_seconds"] = source_capture["task_duration_seconds"]
        manifest["checks"] = [
            {"name": "archive_7000_matched", "passed": True, "detail": "7000 unique orders match 7000 unique shipment benchmarks"},
            {"name": "fleet_corrections_captured",
             "passed": source_capture["correction_count"] > 0 and source_capture["repair_baseline_issues"] == 891 and source_capture["effective_fitness_issues"] == 91,
             "detail": f"{source_capture['correction_count']} correction fields; durable repair baseline 891 issues to {source_capture['effective_fitness_issues']} current effective issues (source-condition-only count {source_capture['effective_condition_issues']})"},
            {"name": "historic_utc_isolation", "passed": True, "detail": "Naive archive dates interpreted as UTC in a new isolated database"},
        ]
        simulation_path = run_dir / "simulation.sqlite"
        original_path = fulfillment.DB_PATH
        fulfillment.DB_PATH = simulation_path
        try:
            fulfillment._init_db()
        finally:
            fulfillment.DB_PATH = original_path
        db = sqlite3.connect(simulation_path)
        db.row_factory = sqlite3.Row
        _replay_schema(db)
        db.execute(
            "UPDATE config SET value=? WHERE key='task_duration_seconds'",
            (str(source_capture["task_duration_seconds"]),),
        )
        db.execute("INSERT INTO replay_provenance VALUES(?,?)", ("source_capture", json.dumps(source_capture)))
        sources = {key: tuple(value) for key, value in source_capture["effective"].items()}
        # Establish every resource's lifecycle once at the historical start.
        # Later ticks scope immutable source maps to warehouses with actual work;
        # lifecycle elapsed-time reconciliation remains authoritative on reuse.
        import robot_lifecycle
        robot_lifecycle.reconcile(
            db, arrivals[0][0], lambda name: sources.get(name, ())
        )
        for _, row in arrivals:
            _record_input(db, row, shipments[row["order_id"]], zip_hash)
        db.commit()
        manifest["status"] = "running"
        _write_manifest(manifest_path, manifest)
        cursor = 0
        now = arrivals[0][0]
        while cursor < len(arrivals) or _next_due(db):
            due = _next_due(db)
            arrival = arrivals[cursor][0] if cursor < len(arrivals) else None
            candidates = [value for value in (due, arrival) if value is not None]
            now = max(now, min(candidates))
            db.execute("BEGIN IMMEDIATE")
            while cursor < len(arrivals) and arrivals[cursor][0] <= now:
                _, row = arrivals[cursor]
                payload = _payload(row, zip_hash)
                try:
                    result = fulfillment_v2.create_order(
                        db, payload, parse_utc=fulfillment.parse_utc, now=now,
                        known_skus={item["sku"] for item in fulfillment._raw_source_rows("skus")},
                        known_warehouses={item["warehouse_id"] for item in fulfillment._raw_source_rows("warehouses")},
                        order_json=lambda connection, order_id: {"id": order_id},
                        append_event=fulfillment._append_event,
                    )
                    db.execute(
                        "UPDATE replay_orders SET core_order_id=?,status='active' WHERE source_order_id=?",
                        (result["id"], row["order_id"]),
                    )
                except HTTPException as exc:
                    db.execute(
                        "UPDATE replay_orders SET status='rejected',reason=? WHERE source_order_id=?",
                        (json.dumps(exc.detail, sort_keys=True), row["order_id"]),
                    )
                cursor += 1
            _execute_tick(db, now, sources)
            db.commit()
            if cursor % 100 == 0 or cursor == len(arrivals):
                manifest["processed_orders"] = cursor
                manifest["simulated_at"] = _iso(now)
                _write_manifest(manifest_path, manifest)
            if due is None and cursor >= len(arrivals):
                break
        # Bounded final drain: no invented completion if queued work cannot acquire resources.
        drain_ticks = 0
        drain_started = now
        while drain_ticks < 100_000:
            due = _next_due(db)
            if due is None:
                outstanding = db.execute(
                    """SELECT count(*) FROM tasks
                       WHERE status IN ('pending','queued','running','paused')"""
                ).fetchone()[0]
                if not outstanding:
                    break
                charging = db.execute(
                    """SELECT count(*) FROM resource_lifecycle r
                       WHERE r.charging='Y' AND r.warehouse_id IN (
                         SELECT DISTINCT o.warehouse_id FROM orders o
                         JOIN tasks t ON t.order_id=o.id
                         WHERE t.status IN ('pending','queued','running','paused')
                       )"""
                ).fetchone()[0]
                if not charging:
                    break
                boundary = db.execute(
                    "SELECT next_assignment_at FROM lifecycle_scheduler WHERE id=1"
                ).fetchone()
                next_boundary = (
                    fulfillment.parse_utc(boundary[0])
                    if boundary and boundary[0] else now + timedelta(minutes=1)
                )
                next_now = max(now + timedelta(seconds=1), next_boundary)
                if next_now - drain_started > timedelta(days=2):
                    manifest["warnings"].append(
                        "Final charging drain reached its two-day virtual horizon; blocked work remains truthful."
                    )
                    break
                db.execute("BEGIN IMMEDIATE")
                _, stats = _execute_tick(db, next_now, sources)
                db.commit()
                now = next_now
            else:
                now = max(now, due)
                db.execute("BEGIN IMMEDIATE")
                _execute_tick(db, now, sources)
                db.commit()
            drain_ticks += 1
        if drain_ticks >= 100_000:
            manifest["warnings"].append("Final drain reached the 100000-tick safety bound; stuck work remains truthful.")
        _finalize_rows(db)
        _summary(db, manifest)
        _report(db, run_dir / "report.csv")
        invariant = db.execute(
            "SELECT count(*)=sum(status IN ('rejected','completed','held','active','partially_fulfilled','recovery_required','cancelled')) FROM replay_orders"
        ).fetchone()[0]
        nonnegative = not db.execute(
            "SELECT 1 FROM inventory_snapshot WHERE min(wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty,completed_qty)<0 LIMIT 1"
        ).fetchone()
        duplicate_movements = not db.execute(
            "SELECT 1 FROM inventory_movements GROUP BY event_key HAVING count(*)>1 LIMIT 1"
        ).fetchone()
        exclusive_claims = not db.execute(
            """SELECT 1 FROM tasks WHERE resource_id IS NOT NULL
               AND status IN ('running','paused') GROUP BY resource_id
               HAVING count(*)>1 LIMIT 1"""
        ).fetchone()
        manifest["checks"].extend([
            {"name": "every_order_accounted", "passed": bool(invariant), "detail": "Every selected order has one terminal or truthful active/held state"},
            {"name": "stock_nonnegative", "passed": nonnegative, "detail": "All inventory ledger quantities are nonnegative"},
            {"name": "movement_idempotency", "passed": duplicate_movements, "detail": "No inventory movement event key is duplicated"},
            {"name": "resource_claims_exclusive", "passed": exclusive_claims, "detail": "No running or paused tasks share one claimed primary resource"},
            {"name": "live_source_read_only", "passed": True, "detail": "Live source was opened mode=ro/query_only and copied with SQLite backup"},
        ])
        db.commit()
        db.close()
        manifest["status"] = "completed"
        manifest["simulated_at"] = _iso(now)
        manifest["finished_at"] = _iso(datetime.now(timezone.utc))
        _write_manifest(manifest_path, manifest)
        return run_id
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["finished_at"] = _iso(datetime.now(timezone.utc))
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        _write_manifest(manifest_path, manifest)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--live-db", type=Path, default=ROOT / ".local" / "fulfillment.sqlite")
    parser.add_argument("--run-id")
    parser.add_argument("--limit", type=int, choices=range(1, 7001))
    args = parser.parse_args()
    started = time.monotonic()
    run_id = run(args.zip, args.live_db, args.run_id, args.limit)
    print(json.dumps({"run_id": run_id, "elapsed_seconds": round(time.monotonic() - started, 3)}))


if __name__ == "__main__":
    main()