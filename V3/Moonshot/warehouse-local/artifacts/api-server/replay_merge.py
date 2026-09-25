"""Offline, fail-closed replay merge. Dry-run is the default; stop API before apply."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from maintenance_lock import exclusive_maintenance

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / ".local/replays/9f25c721-25ef-4d6c-a258-00b34c421191/simulation.sqlite"
RAW = ROOT / "brownfield/AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2/data/raw/inventory_snapshot.csv"
FIELDS = ("wms", "erp", "vision", "reserved", "picked", "completed")
TABLES = ("orders", "order_lines", "sub_orders", "sub_order_allocations",
          "tasks", "inventory_movements", "events")
IDENTITY = ("source_row_index", "warehouse_id", "sku", "location", "zone",
            "inventory_status", "external_reserved_qty", "weight_kg")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def connect(path, readonly=True):
    path = Path(path).resolve()
    require(path.is_file(), f"Database does not exist: {path}")
    db = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                         uri=True, timeout=1, isolation_level=None)
    db.row_factory = sqlite3.Row
    return db


def rows(db, table):
    return [dict(r) for r in db.execute(f'SELECT * FROM "{table}"')]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inventory(db, *, source):
    stock = {r["id"]: r for r in rows(db, "inventory_snapshot")}
    expected = {}
    baseline = {}
    if not source:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='operational_reset_inventory_baseline'").fetchone()
        if exists:
            for r in rows(db, "operational_reset_inventory_baseline"):
                require(r["inventory_row_id"] not in baseline, "Ambiguous reset baseline")
                baseline[r["inventory_row_id"]] = r
    with RAW.open(newline="") as handle:
        raw = list(csv.DictReader(handle))
    require(len(raw) == len(stock), "Inventory dataset size differs")
    for key, r in stock.items():
        origin = raw[r["source_row_index"]]
        require(all(str(origin[f]) == str(r[f]) for f in ("warehouse_id", "sku", "location", "inventory_status")),
                f"Unstable inventory identity: {key}")
        external = max(0, int(origin["reserved_qty"]))
        require(r["external_reserved_qty"] == external, f"External reservations differ: {key}")
        b = baseline.get(key)
        if b:
            require(all(b[f] == r[f] for f in ("warehouse_id", "sku", "location")), "Reset identity differs")
            expected[key] = [b[f + "_qty"] for f in FIELDS]
        else:
            expected[key] = [max(0, int(origin[f + "_qty"]) - external) for f in FIELDS[:3]] + [external, 0, 0]
    for correction in rows(db, "inventory_corrections"):
        key = correction["inventory_row_id"]
        if key in baseline and correction["at"] <= baseline[key]["recorded_at"]:
            continue
        before, after = (json.loads(correction[f]) for f in ("before_json", "after_json"))
        for i, f in enumerate(FIELDS):
            expected[key][i] += after[f + "_qty"] - before[f + "_qty"]
    deltas = {key: [0] * 6 for key in stock}
    for movement in rows(db, "inventory_movements"):
        key = movement["inventory_row_id"]
        require(key in stock, "Movement has missing stock row")
        before, after = (json.loads(movement[f] or "{}") for f in ("before_json", "after_json"))
        for i, f in enumerate(FIELDS):
            delta = movement[f + "_delta"]
            require(before.get(f + "_qty") is not None and after.get(f + "_qty") - before[f + "_qty"] == delta,
                    f"Movement evidence differs: {movement['id']}")
            expected[key][i] += delta
            deltas[key][i] += delta
    for key, r in stock.items():
        require(expected[key] == [r[f + "_qty"] for f in FIELDS],
                f"{'Source' if source else 'Destination'} ledger does not reconcile: inventory {key}")
        require(min(expected[key]) >= 0, f"Negative inventory: {key}")
    allocation_totals = {key: [0, 0, 0] for key in stock}
    for table in ("sub_order_allocations", "legacy_inventory_allocations"):
        for allocation in rows(db, table):
            key = allocation["inventory_row_id"]
            require(key in stock, "Allocation has missing inventory")
            require(0 <= allocation["completed_qty"] <= allocation["picked_qty"] <= allocation["quantity"],
                    "Allocation counters violate execution order")
            for i, field in enumerate(("reserved_qty", "picked_qty", "completed_qty")):
                allocation_totals[key][i] += allocation[field]
    for key, r in stock.items():
        reserved, picked, completed = allocation_totals[key]
        b = baseline.get(key, {})
        require(r["reserved_qty"] == b.get("reserved_qty", r["external_reserved_qty"]) + reserved
                and r["picked_qty"] == b.get("picked_qty", 0) + picked - completed
                and r["completed_qty"] == b.get("completed_qty", 0) + completed,
                f"Allocation WIP counters do not reconcile: inventory {key}")
    return stock, deltas


def graph(source):
    data = {table: rows(source, table) for table in TABLES}
    replay = rows(source, "replay_orders")
    require(Counter(r["status"] for r in replay) == {"completed": 5735, "rejected": 1156, "active": 109},
            "Not the verified full 7000-order replay")
    require(len(data["orders"]) == 5844 and len(data["tasks"]) == 23376, "Accepted graph count differs")
    require(Counter((r["status"], r["stage"]) for r in data["tasks"]) == {
        ("completed", "pick"): 5844, ("completed", "move"): 5735,
        ("completed", "pack_feed"): 5735, ("completed", "stage"): 5735,
        ("queued", "move"): 109, ("pending", "pack_feed"): 109, ("pending", "stage"): 109},
        "Pending graph is not the authorized pick-complete graph")
    require(not rows(source, "task_resources") and not rows(source, "reservations"), "Replay owns live resources")
    orders = {r["id"]: r for r in data["orders"]}
    for r in replay:
        require(digest(json.loads(r["input_json"])) == r["input_hash"], "Replay input hash differs")
        if r["status"] != "rejected":
            require(r["core_order_id"] in orders and orders[r["core_order_id"]]["request_id"] == r["request_id"],
                    "Replay request linkage differs")
            oid = r["core_order_id"]
        else:
            require(r["reason"] and not r["core_order_id"], "Rejected record lacks reason or owns graph")
            oid = "FUL-" + str(uuid.uuid5(uuid.NAMESPACE_URL, r["request_id"]))
            sid = "SUB-" + str(uuid.uuid5(uuid.NAMESPACE_URL, oid + ":" + r["sku"]))
            original = json.loads(r["input_json"])
            data["orders"].append(dict(id=oid, warehouse_id=r["warehouse_id"], priority=r["priority"],
                ship_by=r["cutoff"], status="rejected", created_at=r["created_at"], plan_json="{}",
                issues_json=json.dumps([r["reason"]]), request_id=r["request_id"],
                source_order_id=r["source_order_id"], order_service={"SAME_DAY": "Same_Day",
                "NEXT_DAY": "Next_Day", "STANDARD": "Standard"}[original["service_level"]],
                order_source="fde_bazaar", request_fingerprint=None, policy_version=2,
                cutoff_at=r["cutoff"], order_created_at=r["created_at"]))
            data["order_lines"].append(dict(order_id=oid, sku=r["sku"], quantity=r["quantity"]))
            data["sub_orders"].append(dict(id=sid, order_id=oid, sku=r["sku"], quantity=r["quantity"],
                warehouse_id=r["warehouse_id"], status="rejected", hold_reason=r["reason"],
                cutoff_at=r["cutoff"], created_at=r["created_at"], completed_at=None, cancelled_at=None))
        data["events"].append(dict(order_id=oid, at=r["created_at"],
            message="Original shipment benchmark (not execution): " + r["benchmark_json"]))
    return data


def verify_graph(db):
    for table, column, parent in (("tasks", "order_id", "orders"), ("tasks", "sub_order_id", "sub_orders"),
            ("tasks", "allocation_id", "sub_order_allocations"), ("order_lines", "order_id", "orders"),
            ("sub_orders", "order_id", "orders"), ("sub_order_allocations", "sub_order_id", "sub_orders"),
            ("inventory_movements", "order_id", "orders")):
        require(not db.execute(f"SELECT 1 FROM {table} t LEFT JOIN {parent} p ON p.id=t.{column} "
                              f"WHERE t.{column} IS NOT NULL AND p.id IS NULL LIMIT 1").fetchone(),
                f"Orphan graph: {table}.{column}")
    require(not db.execute("PRAGMA foreign_key_check").fetchone(), "Foreign key violation")


def preflight(source, destination):
    data = graph(source)
    verify_graph(source)
    verify_graph(destination)
    src_stock, deltas = inventory(source, source=True)
    dst_stock, _ = inventory(destination, source=False)
    by_identity = {tuple(r[f] for f in IDENTITY): r for r in dst_stock.values()}
    require(len(by_identity) == len(dst_stock), "Duplicate inventory identity")
    mapping = {}
    for key, r in src_stock.items():
        match = by_identity.get(tuple(r[f] for f in IDENTITY))
        require(match is not None, f"Incompatible inventory baseline: {key}")
        mapping[key] = match["id"]
    for table in ("sub_order_allocations", "inventory_movements"):
        for r in data[table]:
            r["inventory_row_id"] = mapping[r["inventory_row_id"]]
    requests = {r["request_id"]: r for r in rows(destination, "orders")}
    present = [r for r in data["orders"] if r["request_id"] in requests]
    require(len(present) in (0, 7000), "Partial merge/request collision; refusing")
    retired = {r["request_digest"] for r in rows(destination, "retired_order_requests")}
    require(not any(hashlib.sha256(r["request_id"].encode()).hexdigest() in retired
                    for r in data["orders"]), "Replay request collides with retired operational request")
    # The transaction receipt authenticates the imported immutable graph. It is
    # maintenance evidence only: no runtime query uses it to segregate orders.
    if present:
        receipt_table = destination.execute(
            "SELECT 1 FROM sqlite_master WHERE name='maintenance_replay_merges'").fetchone()
        require(receipt_table and destination.execute(
            "SELECT 1 FROM maintenance_replay_merges WHERE source_digest=?", (digest(data),)).fetchone(),
            "Existing requests have no matching atomic merge receipt")
    active_ids = {r["id"] for r in data["orders"] if r["status"] not in ("completed", "rejected")}
    imported_ids = {r["id"] for r in data["orders"]}
    sub_ids = {r["id"] for r in data["sub_orders"]}
    for table in TABLES:
        expected = data[table]
        existing = rows(destination, table)
        if present:
            actual = [r for r in existing if (r.get("order_id", r.get("id")) in imported_ids
                      or (table == "sub_order_allocations" and r["sub_order_id"] in sub_ids))]
            def canonical(r):
                return digest({k: v for k, v in r.items() if not (table == "events" and k == "id")})
            if table in ("events", "inventory_movements"):
                require(not (Counter(map(canonical, expected)) - Counter(map(canonical, actual))),
                        f"Existing request graph differs: {table}")
                continue
            require(len(actual) == len(expected), f"Existing request graph differs: {table}")
            actual_index = {(r.get("id") or (r["order_id"], r["sku"])): r for r in actual}
            active_subs = {r["id"] for r in data["sub_orders"] if r["order_id"] in active_ids}
            for original in expected:
                current = actual_index.get(original.get("id") or (original["order_id"], original["sku"]))
                require(current is not None, f"Existing request graph differs: {table}")
                active = (original.get("order_id", original.get("id")) in active_ids
                          or original.get("sub_order_id") in active_subs)
                mutable = set()
                if active:
                    mutable = {
                        "orders": {"status", "issues_json", "plan_json"},
                        "sub_orders": {"status", "hold_reason", "completed_at", "cancelled_at"},
                        "sub_order_allocations": {"reserved_qty", "picked_qty", "completed_qty", "wip_stage"},
                        "tasks": {"status", "resource_id", "resource_type", "started_at", "due_at",
                                  "completed_at", "duration_seconds", "wait_reason", "assignment_version"},
                    }.get(table, set())
                    if table == "tasks" and original["status"] == "completed":
                        mutable = set()  # Previously completed picks are immutable.
                    elif table == "tasks":
                        require(current["status"] in ("pending", "queued", "running", "paused", "completed", "cancelled"),
                                "Invalid continued task status")
                        if current["status"] in ("running", "completed"):
                            require(current["resource_id"] and current["started_at"] and current["due_at"]
                                    and current["assignment_version"] > original["assignment_version"],
                                    "Continued task lacks assignment evidence")
                        if current["status"] == "completed":
                            require(current["completed_at"], "Continued task lacks completion evidence")
                require(all(current[k] == v for k, v in original.items() if k not in mutable),
                        f"Existing request graph differs: {table}")
        else:
            for key in ("id", "request_id", "event_key"):
                if table == "events" or not expected or key not in expected[0]:
                    continue
                require(not ({r[key] for r in expected} & {r[key] for r in existing}), f"Identity collision: {table}.{key}")
    if not present:
        for key, delta in deltas.items():
            r = dst_stock[mapping[key]]
            require(all(r[f + "_qty"] + delta[i] >= 0 for i, f in enumerate(FIELDS)),
                    f"Combined stock would be negative: {key}")
    return data, mapping, deltas, bool(present)


def merge_replay(source_path, destination_path, *, apply=False, backup_dir=None, failpoint=None):
    source_path, destination_path = Path(source_path).resolve(), Path(destination_path).resolve()
    require(source_path != destination_path, "Source and destination must differ")
    with exclusive_maintenance(destination_path.parent):
        with closing(connect(source_path)) as source, closing(connect(destination_path, not apply)) as db:
            source.execute("BEGIN")
            db.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
            try:
                data, mapping, deltas, existing = preflight(source, db)
                result = dict(applied=False, already_applied=existing, accepted=5844, rejected=1156,
                              completed=5735, pending=109, tasks=23376,
                              before_orders=db.execute("SELECT count(*) FROM orders").fetchone()[0])
                if not apply or existing:
                    db.rollback()
                    return result
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                folder = Path(backup_dir) if backup_dir else destination_path.parent / "backups"
                folder.mkdir(parents=True, exist_ok=True)
                backup = folder / f"before-replay-merge-{stamp}.sqlite"
                with closing(connect(destination_path)) as reader, closing(sqlite3.connect(backup)) as target:
                    reader.backup(target)
                    require(target.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "Backup integrity failed")
                for table in TABLES:
                    for row in data[table]:
                        row = {k: v for k, v in row.items() if not (table == "events" and k == "id")}
                        columns = list(row)
                        db.execute(f'INSERT INTO "{table}" ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                                   list(row.values()))
                if failpoint:
                    failpoint("after_graph")
                for key, delta in deltas.items():
                    if any(delta):
                        db.execute("UPDATE inventory_snapshot SET " +
                            ",".join(f"{f}_qty={f}_qty+?" for f in FIELDS) + ",revision=revision+1 WHERE id=?",
                            [*delta, mapping[key]])
                inventory(db, source=False)
                verify_graph(db)
                import order_progress
                order_progress.sync(db, datetime.now(timezone.utc))
                import demand_forecast
                result["forecast_refresh"] = demand_forecast.refresh_current(
                    db, datetime.now(timezone.utc)
                )
                require(db.execute("SELECT count(*) FROM orders").fetchone()[0] == result["before_orders"] + 7000,
                        "Unified counter differs")
                db.execute("CREATE TABLE IF NOT EXISTS maintenance_replay_merges "
                           "(source_digest TEXT PRIMARY KEY, applied_at TEXT NOT NULL, audit_json TEXT NOT NULL)")
                result.update(applied=True, backup=str(backup), after_orders=result["before_orders"] + 7000)
                db.execute("INSERT INTO maintenance_replay_merges VALUES (?,?,?)",
                           (digest(data), stamp, json.dumps(result, sort_keys=True)))
                if failpoint:
                    failpoint("before_commit")
                # Portable external manifest accompanies the backup. The small
                # in-DB receipt above is needed for atomic, crash-safe retries.
                backup.with_suffix(".audit.json").write_text(json.dumps({
                    **result, "source": str(source_path), "source_digest": digest(data),
                    "commit_verification": "Check matching atomic database receipt; manifest alone does not prove commit",
                    "request_ids": [r["request_id"] for r in data["orders"]],
                    "inventory_id_map": mapping,
                }, indent=2, sort_keys=True))
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(merge_replay(args.source, args.destination, apply=args.apply,
                                 backup_dir=args.backup_dir), indent=2))


if __name__ == "__main__":
    main()