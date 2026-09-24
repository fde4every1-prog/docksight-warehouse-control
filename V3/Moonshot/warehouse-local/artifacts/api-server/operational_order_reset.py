"""Guarded, offline, one-time removal of operational order data.

This module is deliberately not imported by application startup.  Managed API
processes hold ``runtime_lock``; this maintenance operation takes the matching
exclusive lock for its entire backup and reset window.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from maintenance_lock import exclusive_maintenance


RESET_KEY = "v2-only-order-reset-v1"
Failpoint = Callable[[str], None]


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _has_table(db: sqlite3.Connection, name: str, schema: str = "main") -> bool:
    return (
        db.execute(
            f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _require_tables(
    db: sqlite3.Connection, names: set[str], schema: str = "main"
) -> None:
    missing = sorted(name for name in names if not _has_table(db, name, schema))
    if missing:
        raise RuntimeError(
            f"Refusing reset: {schema} database is missing required tables: "
            + ", ".join(missing)
        )


def _table_columns(
    db: sqlite3.Connection, table: str, schema: str = "main"
) -> set[str]:
    return {
        str(row[1])
        for row in db.execute(f"PRAGMA {schema}.table_info({table})")
    }


def _backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"Refusing to overwrite backup: {destination}")
    with closing(sqlite3.connect(source, timeout=1)) as src, closing(
        sqlite3.connect(destination)
    ) as dst:
        src.execute("PRAGMA busy_timeout=1000")
        src.backup(dst)
        result = dst.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed: {destination}")


def _json_contains_identity(value: Any, identities: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            _json_contains_identity(key, identities)
            or _json_contains_identity(item, identities)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_json_contains_identity(item, identities) for item in value)
    return isinstance(value, str) and any(
        identity in value for identity in identities
    )


def _scrub_json(value: Any, identities: set[str]) -> Any:
    identity_keys = {
        "order_id",
        "task_id",
        "sub_order_id",
        "allocation_id",
        "target_order_id",
        "linked_order_id",
    }
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in identity_keys:
                continue
            if key == "linked_work" and isinstance(item, list):
                # A linked-work object is one relationship.  Removing only its
                # order/task keys can leave a misleading partial P1 link.
                item = [
                    entry
                    for entry in item
                    if not _json_contains_identity(entry, identities)
                ]
            scrubbed = _scrub_json(item, identities)
            if key == "linked_work" and isinstance(scrubbed, list):
                scrubbed = [entry for entry in scrubbed if entry not in ({}, None)]
            cleaned[key] = scrubbed
        return cleaned
    if isinstance(value, list):
        return [
            scrubbed
            for item in value
            if (scrubbed := _scrub_json(item, identities)) is not None
        ]
    if isinstance(value, str):
        if value in identities:
            return None
        return _scrub_text(value, identities)
    return value


def _scrub_text(value: str | None, identities: set[str]) -> str | None:
    if value is None:
        return None
    result = value
    for identity in identities:
        if identity in result:
            result = result.replace(identity, "[retired reference]")
    return result


def _scrub_persona_rows(db: sqlite3.Connection, identities: set[str]) -> None:
    if not _has_table(db, "persona_interventions"):
        return

    protected: set[str] = set()
    for table in (
        "persona_safety_holds",
        "persona_resource_blocks",
        "persona_inventory_overlays",
        "persona_source_corrections",
    ):
        if _has_table(db, table):
            protected.update(
                str(row[0])
                for row in db.execute(
                    f"SELECT DISTINCT intervention_id FROM {table} "
                    "WHERE intervention_id IS NOT NULL"
                )
            )

    deleted: set[str] = set()
    rows = db.execute(
        "SELECT id,dedupe_key,kind,entity_id,title,description,evidence_json,"
        "proposed_action_json FROM persona_interventions"
    ).fetchall()
    for row in rows:
        (
            intervention_id,
            dedupe_key,
            kind,
            entity_id,
            title,
            description,
            evidence_raw,
            proposed_raw,
        ) = row
        evidence = json.loads(evidence_raw or "{}")
        proposed = json.loads(proposed_raw) if proposed_raw else None
        order_specific = kind in {
            "priority_override",
            "task_completion_conflict",
        } or entity_id in identities
        if order_specific and intervention_id not in protected:
            deleted.add(intervention_id)
            continue
        db.execute(
            "UPDATE persona_interventions SET dedupe_key=?,entity_id=?,title=?,"
            "description=?,evidence_json=?,proposed_action_json=? WHERE id=?",
            (
                None
                if dedupe_key
                and any(identity in dedupe_key for identity in identities)
                else dedupe_key,
                "[retired reference]" if entity_id in identities else entity_id,
                _scrub_text(title, identities),
                _scrub_text(description, identities),
                json.dumps(_scrub_json(evidence, identities), sort_keys=True),
                json.dumps(_scrub_json(proposed, identities), sort_keys=True)
                if proposed is not None
                else None,
                intervention_id,
            ),
        )

    if deleted:
        marks = ",".join("?" for _ in deleted)
        if _has_table(db, "persona_intervention_events"):
            db.execute(
                f"DELETE FROM persona_intervention_events "
                f"WHERE intervention_id IN ({marks})",
                tuple(deleted),
            )
        db.execute(
            f"DELETE FROM persona_interventions WHERE id IN ({marks})", tuple(deleted)
        )

    if _has_table(db, "persona_intervention_events"):
        for row in db.execute(
            "SELECT id,reason,details_json FROM persona_intervention_events"
        ).fetchall():
            details = json.loads(row[2] or "{}")
            db.execute(
                "UPDATE persona_intervention_events SET reason=?,details_json=? WHERE id=?",
                (
                    _scrub_text(row[1], identities),
                    json.dumps(_scrub_json(details, identities), sort_keys=True),
                    row[0],
                ),
            )
    if _has_table(db, "persona_audit_events"):
        for row in db.execute(
            "SELECT id,entity_id,reason,details_json FROM persona_audit_events"
        ).fetchall():
            details = json.loads(row[3] or "{}")
            if (
                row[1] in identities
                or row[1] in deleted
                or _json_contains_identity(details, identities)
            ):
                db.execute("DELETE FROM persona_audit_events WHERE id=?", (row[0],))
            else:
                db.execute(
                    "UPDATE persona_audit_events SET reason=?,details_json=? WHERE id=?",
                    (
                        _scrub_text(row[2], identities),
                        json.dumps(_scrub_json(details, identities), sort_keys=True),
                        row[0],
                    ),
                )

    for table in ("persona_safety_holds", "persona_resource_blocks"):
        if _has_table(db, table) and "reason" in _table_columns(db, table):
            for row in db.execute(f"SELECT rowid,reason FROM {table}").fetchall():
                db.execute(
                    f"UPDATE {table} SET reason=? WHERE rowid=?",
                    (_scrub_text(row[1], identities), row[0]),
                )

    for table in ("persona_detection_state", "persona_v2_detection_state"):
        if _has_table(db, table):
            db.execute(f"DELETE FROM {table}")


def _scrub_table_text(
    db: sqlite3.Connection, table: str, identities: set[str]
) -> None:
    """Scrub identities from preserved free-text and JSON correction evidence."""

    if not _has_table(db, table):
        return
    text_columns = [
        str(row[1])
        for row in db.execute(f"PRAGMA table_info({table})")
        if str(row[2]).upper() in {"TEXT", ""}
    ]
    for column in text_columns:
        for rowid, value in db.execute(
            f"SELECT rowid,{column} FROM {table} WHERE {column} IS NOT NULL"
        ).fetchall():
            try:
                decoded = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                cleaned = _scrub_text(str(value), identities)
            else:
                cleaned = json.dumps(
                    _scrub_json(decoded, identities), sort_keys=True
                )
            if cleaned != value:
                db.execute(
                    f"UPDATE {table} SET {column}=? WHERE rowid=?",
                    (cleaned, rowid),
                )


def _perform_reset(db: sqlite3.Connection, now: str, failpoint: Failpoint | None) -> dict[str, int]:
    _require_tables(
        db,
        {
            "orders",
            "order_lines",
            "reservations",
            "tasks",
            "task_resources",
            "events",
            "stock_effects",
            "inventory_snapshot",
            "sub_orders",
            "sub_order_allocations",
            "inventory_movements",
            "legacy_inventory_allocations",
        },
    )
    _require_tables(db, {"orders", "order_lines", "outbox"}, "bazaar")

    db.execute(
        "CREATE TABLE IF NOT EXISTS maintenance_resets("
        "reset_key TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS retired_order_requests("
        "request_digest TEXT PRIMARY KEY)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS bazaar.retired_order_requests("
        "request_digest TEXT PRIMARY KEY)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS operational_reset_inventory_baseline("
        "reset_key TEXT NOT NULL, inventory_row_id INTEGER NOT NULL,"
        "warehouse_id TEXT NOT NULL, sku TEXT NOT NULL, location TEXT NOT NULL,"
        "wms_qty INTEGER NOT NULL, erp_qty INTEGER NOT NULL, vision_qty INTEGER NOT NULL,"
        "reserved_qty INTEGER NOT NULL, external_reserved_qty INTEGER NOT NULL,"
        "picked_qty INTEGER NOT NULL, completed_qty INTEGER NOT NULL,"
        "released_unpicked_qty INTEGER NOT NULL, recorded_at TEXT NOT NULL,"
        "PRIMARY KEY(reset_key,inventory_row_id))"
    )

    order_ids = {str(row[0]) for row in db.execute("SELECT id FROM orders")}
    bazaar_order_ids = {
        str(row[0]) for row in db.execute("SELECT id FROM bazaar.orders")
    }
    reservation_ids = {
        str(row[0]) for row in db.execute("SELECT id FROM reservations")
    }
    sub_order_ids = {str(row[0]) for row in db.execute("SELECT id FROM sub_orders")}
    task_ids = {str(row[0]) for row in db.execute("SELECT id FROM tasks")}
    allocation_ids = {
        str(row[0]) for row in db.execute("SELECT id FROM sub_order_allocations")
    }
    identities = (
        order_ids
        | bazaar_order_ids
        | reservation_ids
        | sub_order_ids
        | task_ids
        | allocation_ids
    )

    for row in db.execute("SELECT request_id FROM orders WHERE request_id IS NOT NULL"):
        db.execute(
            "INSERT OR IGNORE INTO retired_order_requests(request_digest) VALUES (?)",
            (hashlib.sha256(str(row[0]).encode()).hexdigest(),),
        )
    for row in db.execute(
        "SELECT request_id FROM bazaar.orders WHERE request_id IS NOT NULL"
    ):
        db.execute(
            "INSERT OR IGNORE INTO bazaar.retired_order_requests(request_digest) VALUES (?)",
            (hashlib.sha256(str(row[0]).encode()).hexdigest(),),
        )

    invalid_snapshot = db.execute(
        "SELECT 1 FROM inventory_snapshot WHERE wms_qty<0 OR erp_qty<0 "
        "OR vision_qty<0 OR reserved_qty<0 OR external_reserved_qty<0 "
        "OR picked_qty<0 OR completed_qty<0 "
        "OR external_reserved_qty>reserved_qty LIMIT 1"
    ).fetchone()
    if invalid_snapshot:
        raise RuntimeError("Refusing reset: inconsistent inventory counters")

    counters_by_row: dict[int, list[int]] = {}
    for table in ("sub_order_allocations", "legacy_inventory_allocations"):
        inconsistent = db.execute(
            f"SELECT 1 FROM {table} WHERE quantity<=0 OR reserved_qty<0 "
            "OR picked_qty<0 OR completed_qty<0 "
            "OR (reserved_qty+picked_qty+completed_qty)>quantity LIMIT 1"
        ).fetchone()
        if inconsistent:
            raise RuntimeError(
                f"Refusing reset: inconsistent allocation counters in {table}"
            )
        for inventory_row_id, reserved, picked, completed in db.execute(
            f"SELECT inventory_row_id,COALESCE(SUM(reserved_qty),0),"
            "COALESCE(SUM(picked_qty),0),COALESCE(SUM(completed_qty),0) "
            f"FROM {table} GROUP BY inventory_row_id"
        ):
            aggregate = counters_by_row.setdefault(int(inventory_row_id), [0, 0, 0])
            aggregate[0] += int(reserved)
            aggregate[1] += int(picked)
            aggregate[2] += int(completed)
    release_by_row = {
        inventory_row_id: counters[0]
        for inventory_row_id, counters in counters_by_row.items()
    }
    for inventory_row_id, counters in counters_by_row.items():
        quantity, allocated_picked, allocated_completed = counters
        current = db.execute(
            "SELECT reserved_qty,external_reserved_qty,picked_qty,completed_qty "
            "FROM inventory_snapshot WHERE id=?",
            (inventory_row_id,),
        ).fetchone()
        if (
            current is None
            or any(int(counter) < 0 for counter in current)
            or int(current[1]) > int(current[0])
            or quantity < 0
            or quantity > int(current[0]) - int(current[1])
            or allocated_picked > int(current[2])
            or allocated_completed > int(current[3])
        ):
            raise RuntimeError(
                f"Refusing reset: inconsistent reserved balance for inventory row "
                f"{inventory_row_id}"
            )
        db.execute(
            "UPDATE inventory_snapshot SET wms_qty=wms_qty+?,erp_qty=erp_qty+?,"
            "vision_qty=vision_qty+?,reserved_qty=reserved_qty-?,revision=revision+1,"
            "updated_at=? WHERE id=?",
            (quantity, quantity, quantity, quantity, now, inventory_row_id),
        )
    if failpoint:
        failpoint("after_inventory_release")

    for row in db.execute(
        "SELECT id,warehouse_id,sku,location,wms_qty,erp_qty,vision_qty,reserved_qty,"
        "external_reserved_qty,picked_qty,completed_qty FROM inventory_snapshot"
    ):
        db.execute(
            "INSERT INTO operational_reset_inventory_baseline VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                RESET_KEY,
                *row,
                release_by_row.get(int(row[0]), 0),
                now,
            ),
        )

    _scrub_persona_rows(db, identities)
    _scrub_table_text(db, "inventory_corrections", identities)
    # Keep discrepancy/anomaly state active, but remove retired reservation or
    # order identifiers from its explanatory text.
    for rowid, discrepancy in db.execute(
        "SELECT rowid,opening_discrepancy FROM inventory_snapshot "
        "WHERE opening_discrepancy IS NOT NULL"
    ).fetchall():
        db.execute(
            "UPDATE inventory_snapshot SET opening_discrepancy=? WHERE rowid=?",
            (_scrub_text(discrepancy, identities), rowid),
        )
    if _has_table(db, "persona_task_pauses"):
        db.execute("DELETE FROM persona_task_pauses")

    db.execute("DELETE FROM task_resources")
    db.execute("DELETE FROM stock_effects")
    db.execute("DELETE FROM tasks")
    db.execute("DELETE FROM events")
    db.execute("DELETE FROM sub_order_allocations")
    db.execute("DELETE FROM legacy_inventory_allocations")
    db.execute("DELETE FROM inventory_movements")
    db.execute("DELETE FROM reservations")
    db.execute("DELETE FROM sub_orders")
    db.execute("DELETE FROM order_lines")
    db.execute("DELETE FROM orders")
    if failpoint:
        failpoint("after_fulfillment_delete")

    db.execute("DELETE FROM bazaar.outbox")
    db.execute("DELETE FROM bazaar.order_lines")
    db.execute("DELETE FROM bazaar.orders")
    if failpoint:
        failpoint("after_bazaar_delete")

    db.execute(
        "INSERT INTO maintenance_resets(reset_key,applied_at) VALUES (?,?)",
        (RESET_KEY, now),
    )
    main_fk = db.execute("PRAGMA main.foreign_key_check").fetchall()
    bazaar_fk = db.execute("PRAGMA bazaar.foreign_key_check").fetchall()
    if main_fk or bazaar_fk:
        raise RuntimeError("Refusing reset: foreign key violations remain")
    return {
        "fulfillment_orders": len(order_ids),
        "bazaar_orders": len(bazaar_order_ids),
        "released_unpicked_qty": sum(release_by_row.values()),
        "baseline_rows": db.execute(
            "SELECT COUNT(*) FROM operational_reset_inventory_baseline "
            "WHERE reset_key=?",
            (RESET_KEY,),
        ).fetchone()[0],
    }


def reset_operational_orders(
    fulfillment_path: str | Path,
    bazaar_path: str | Path,
    *,
    backup_dir: str | Path | None = None,
    development: bool = False,
    failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    """Back up and atomically retire all pre-reset operational orders."""

    if not development:
        raise RuntimeError("Refusing reset without explicit development opt-in")
    if (
        os.environ.get("APP_ENV", "development").lower()
        in {"production", "prod", "published"}
        or os.environ.get("NODE_ENV", "").lower() == "production"
        or os.environ.get("REPLIT_DEPLOYMENT", "").lower()
        in {"1", "true", "yes"}
    ):
        raise RuntimeError("Refusing destructive reset outside development")

    fulfillment_path = Path(fulfillment_path).resolve()
    bazaar_path = Path(bazaar_path).resolve()
    if fulfillment_path.parent != bazaar_path.parent:
        raise RuntimeError("Both databases must share the guarded data directory")
    if not fulfillment_path.is_file() or not bazaar_path.is_file():
        raise RuntimeError("Both operational SQLite databases must already exist")
    data_dir = fulfillment_path.parent
    backup_root = Path(backup_dir).resolve() if backup_dir else data_dir / "backups"

    with exclusive_maintenance(data_dir):
        with closing(sqlite3.connect(fulfillment_path, timeout=1)) as check:
            if _has_table(check, "maintenance_resets") and check.execute(
                "SELECT 1 FROM maintenance_resets WHERE reset_key=?", (RESET_KEY,)
            ).fetchone():
                return {"applied": False, "reason": "already_applied"}

        suffix = _stamp()
        fulfillment_backup = backup_root / f"fulfillment-before-order-reset-{suffix}.sqlite"
        bazaar_backup = backup_root / f"bazaar-before-order-reset-{suffix}.sqlite"
        _backup(fulfillment_path, fulfillment_backup)
        try:
            _backup(bazaar_path, bazaar_backup)
        except Exception:
            fulfillment_backup.unlink(missing_ok=True)
            raise

        db = sqlite3.connect(fulfillment_path, timeout=1, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=1000")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("ATTACH DATABASE ? AS bazaar", (str(bazaar_path),))
            db.execute("PRAGMA bazaar.journal_mode=DELETE")
            db.execute("PRAGMA bazaar.synchronous=FULL")
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("BEGIN IMMEDIATE")
            try:
                counts = _perform_reset(db, _iso_now(), failpoint)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        finally:
            db.close()
        return {
            "applied": True,
            "backups": {
                "fulfillment": str(fulfillment_backup),
                "bazaar": str(bazaar_backup),
            },
            **counts,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fulfillment-db", type=Path, required=True)
    parser.add_argument("--bazaar-db", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument(
        "--development-confirm",
        action="store_true",
        help="required explicit acknowledgement for destructive development reset",
    )
    args = parser.parse_args()
    result = reset_operational_orders(
        args.fulfillment_db,
        args.bazaar_db,
        backup_dir=args.backup_dir,
        development=args.development_confirm,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())