"""Offline, guarded bulk correction of synthetic fleet readiness sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import fleet_readiness
import fleet_repair
import fulfillment_api as fulfillment
import persona_api as persona
from maintenance_lock import exclusive_maintenance


REASON = "Authorized synthetic data correction: fleet readiness source repair"
MUTABLE_TABLES = {
    "persona_source_corrections",
    "registered_resources",
    "persona_interventions",
    "persona_intervention_events",
    "persona_audit_events",
}
Failpoint = Callable[[str], None]


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"Refusing to overwrite backup: {destination}")
    with closing(sqlite3.connect(source, timeout=1)) as src, closing(
        sqlite3.connect(destination)
    ) as dst:
        src.execute("PRAGMA busy_timeout=1000")
        src.backup(dst)
        check = dst.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed: {destination}")


def _table_digest(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Hash every non-maintenance application table without assuming its schema."""

    result: dict[str, dict[str, Any]] = {}
    names = [
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        if str(row[0]) not in MUTABLE_TABLES
    ]
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        rows = db.execute(f"SELECT * FROM {quoted} ORDER BY rowid").fetchall()
        digest = hashlib.sha256()
        for row in rows:
            digest.update(
                json.dumps(list(row), sort_keys=True, default=str, separators=(",", ":")).encode()
            )
            digest.update(b"\n")
        result[name] = {"rows": len(rows), "sha256": digest.hexdigest()}
    return result


def select_balanced(
    candidates: list[dict[str, Any]], target: int
) -> list[dict[str, Any]]:
    """Deterministic warehouse round-robin, alternating resource kinds."""

    if target < 1 or len(candidates) < target:
        raise RuntimeError(
            f"Cannot select exactly {target} repairable issues from {len(candidates)} candidates"
        )
    buckets: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"fleet_readiness": [], "control_asset_readiness": []}
    )
    for item in candidates:
        buckets[item["warehouse_id"]][item["kind"]].append(item)
    for kinds in buckets.values():
        for values in kinds.values():
            values.sort(
                key=lambda item: (
                    not bool(item.get("impacted")),
                    -len(item["spec"]["blockers"]),
                    item["entity_id"],
                    item["id"],
                )
            )
    warehouses = sorted(buckets)
    selected: list[dict[str, Any]] = []
    preferred = {warehouse: "fleet_readiness" for warehouse in warehouses}
    while len(selected) < target:
        progressed = False
        for warehouse in warehouses:
            first = preferred[warehouse]
            for kind in (
                first,
                "control_asset_readiness"
                if first == "fleet_readiness"
                else "fleet_readiness",
            ):
                bucket = buckets[warehouse][kind]
                if bucket:
                    selected.append(bucket.pop(0))
                    progressed = True
                    preferred[warehouse] = (
                        "control_asset_readiness"
                        if kind == "fleet_readiness"
                        else "fleet_readiness"
                    )
                    break
            if len(selected) == target:
                break
        if not progressed:
            raise RuntimeError(f"Selection exhausted before exactly {target} issues")
    if len(warehouses) <= target and {item["warehouse_id"] for item in selected} != set(warehouses):
        raise RuntimeError("Balanced selection failed to represent every warehouse")
    return selected


def _fresh_spec(
    db: sqlite3.Connection,
    item: dict[str, Any],
    robots: dict[str, dict[str, Any]],
    maintenance: dict[str, dict[str, Any]],
    assets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild one context from current in-transaction bulk snapshots."""

    entity_id = item["entity_id"]
    if item["kind"] == "control_asset_readiness":
        asset = assets[entity_id]
        _, blockers = fleet_readiness.asset_readiness(asset)
        contexts = [fleet_repair._context(db, "control_asset", entity_id, asset)]
    else:
        robot = robots[entity_id]
        linked = sorted(
            (row for row in maintenance.values() if str(row.get("robot_id") or "") == entity_id),
            key=lambda row: str(row.get("work_order_id") or ""),
        )
        _, blockers = fleet_readiness.robot_readiness(robot, linked)
        contexts = [fleet_repair._context(db, "robot", entity_id, robot)]
        if linked:
            contexts.extend(
                fleet_repair._context(
                    db, "maintenance", str(row["work_order_id"]), row
                )
                for row in linked
            )
        else:
            contexts.append(
                fleet_repair._context(
                    db,
                    "maintenance",
                    fleet_repair.missing_maintenance_id(entity_id),
                    None,
                    missing=True,
                )
            )
    return {**item["spec"], "blockers": blockers, "contexts": contexts}


def _repair_values(context: dict[str, Any]) -> dict[str, Any]:
    values = dict(context["values"])
    if context["entity_type"] == "robot":
        values.update(
            health_status="HEALTHY",
            safety_cert_status="VALID",
            connectivity="ONLINE",
        )
    elif context["entity_type"] == "maintenance":
        values.update(cmms_status="CLOSED", fleet_availability="AVAILABLE")
    else:
        values.update(state="AVAILABLE", maintenance_state="CLEAR")
    return {
        "entity_type": context["entity_type"],
        "entity_id": context["entity_id"],
        "revision": context["revision"],
        "values": values,
    }


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    warehouses: dict[str, dict[str, int]] = {}
    for item in items:
        counts = warehouses.setdefault(item["warehouse_id"], {"robots": 0, "assets": 0})
        counts["robots" if item["kind"] == "fleet_readiness" else "assets"] += 1
    return {"warehouse_count": len(warehouses), "warehouses": warehouses}


def _run_transaction(
    db: sqlite3.Connection,
    *,
    target: int,
    expected_total: int,
    dry_run: bool,
    failpoint: Failpoint | None,
) -> dict[str, Any]:
    before_invariants = _table_digest(db)
    specs = persona._sync_fleet_issues(db)
    rows = db.execute(
        "SELECT * FROM persona_interventions WHERE status<>'resolved' "
        "AND kind IN ('fleet_readiness','control_asset_readiness') "
        "AND (dedupe_key LIKE 'fleet_readiness:%' "
        "OR dedupe_key LIKE 'v2:control_asset:%')"
    ).fetchall()
    if len(rows) != expected_total or len(specs) != expected_total:
        raise RuntimeError(
            f"Refusing repair: expected exactly {expected_total} current issues, "
            f"found {len(rows)} open and {len(specs)} source issues"
        )
    impacts = fleet_repair.readiness_impacts(db)
    candidates = []
    for row in rows:
        spec = specs.get(row["dedupe_key"])
        if spec is None or not spec["blockers"]:
            continue
        if fleet_repair.assignment_blockers(db, str(row["entity_id"])):
            continue
        candidates.append(
            {
                "id": str(row["id"]),
                "dedupe_key": str(row["dedupe_key"]),
                "kind": str(row["kind"]),
                "entity_id": str(row["entity_id"]),
                "warehouse_id": str(row["warehouse_id"]),
                "impacted": bool(impacts.get(str(row["entity_id"]))),
                "spec": spec,
            }
        )
    selected = select_balanced(candidates, target)
    selected_ids = {item["id"] for item in selected}
    original_ids = {str(row["id"]) for row in rows}
    remaining_ids = original_ids - selected_ids

    # One complete effective read per source dataset; update these maps locally
    # after each approved correction instead of rescanning imported CSVs.
    robots = {str(row["robot_id"]): dict(row) for row in fulfillment.source_rows("robots")}
    maintenance = {
        str(row["work_order_id"]): dict(row)
        for row in fulfillment.source_rows("maintenance")
        if row.get("work_order_id")
    }
    assets = {
        str(row["asset_id"]): dict(row)
        for row in fulfillment.source_rows("control_assets")
    }
    now = _now()
    changes = 0
    for index, item in enumerate(selected):
        spec = _fresh_spec(db, item, robots, maintenance, assets)
        submitted = [_repair_values(context) for context in spec["contexts"]]
        contexts = fleet_repair.validate_snapshot(db, spec["contexts"], submitted)
        item_changes = fleet_repair.apply_repairs(
            db, contexts, spec["contexts"], item["id"], now
        )
        changes += len(item_changes)
        for context in contexts:
            target_map = {
                "robot": robots,
                "maintenance": maintenance,
                "control_asset": assets,
            }[context["entity_type"]]
            current = target_map.setdefault(context["entity_id"], {})
            if context["entity_type"] == "maintenance" and not current:
                current.update(
                    work_order_id=context["entity_id"],
                    robot_id=item["entity_id"],
                    warehouse_id=item["warehouse_id"],
                )
            current.update(context["values"])
        row = db.execute(
            "SELECT * FROM persona_interventions WHERE id=?", (item["id"],)
        ).fetchone()
        persona._add_event(
            db,
            row,
            "fleet",
            "repaired",
            REASON,
            {"changes": item_changes, "maintenance_mode": "offline_bulk"},
        )
        persona._audit(
            db,
            "fleet",
            "fleet_repair",
            item["entity_id"],
            REASON,
            {"intervention_id": item["id"], "changes": item_changes},
        )
        if failpoint and index == target // 2:
            failpoint("mid_repair")

    # Truth verification is independent of intervention status: project all
    # source conditions once after all overlays have been written.
    truth_specs = persona._sync_fleet_issues(db)
    truth_keys = set(truth_specs)
    selected_keys = {item["dedupe_key"] for item in selected}
    remaining_keys = {
        str(row["dedupe_key"]) for row in rows if str(row["id"]) in remaining_ids
    }
    if truth_keys & selected_keys:
        raise RuntimeError("Refusing commit: at least one selected source issue still exists")
    if truth_keys != remaining_keys or len(truth_keys) != expected_total - target:
        raise RuntimeError(
            "Refusing commit: non-target issue truth changed or an unexpected issue appeared"
        )
    open_ids = {
        str(row[0])
        for row in db.execute(
            "SELECT id FROM persona_interventions WHERE status<>'resolved' "
            "AND kind IN ('fleet_readiness','control_asset_readiness') "
            "AND (dedupe_key LIKE 'fleet_readiness:%' "
            "OR dedupe_key LIKE 'v2:control_asset:%')"
        )
    }
    if open_ids != remaining_ids:
        raise RuntimeError("Refusing commit: projected open issue identities are not exact")
    after_invariants = _table_digest(db)
    if before_invariants != after_invariants:
        changed = sorted(
            name
            for name in set(before_invariants) | set(after_invariants)
            if before_invariants.get(name) != after_invariants.get(name)
        )
        raise RuntimeError("Refusing commit: operational invariants changed: " + ", ".join(changed))
    result = {
        "applied": not dry_run,
        "dry_run": dry_run,
        "expected_before": expected_total,
        "selected": target,
        "remaining": expected_total - target,
        "source_field_changes": changes,
        "selection": _summary(selected),
        "selected_issue_ids": sorted(selected_ids),
        "remaining_issue_ids": sorted(remaining_ids),
        "operational_invariants": before_invariants,
    }
    return result


def repair_fleet_issues(
    fulfillment_path: str | Path,
    bazaar_path: str | Path,
    *,
    target: int = 800,
    expected_total: int = 891,
    dry_run: bool = True,
    backup_dir: str | Path | None = None,
    failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    fulfillment_path = Path(fulfillment_path).resolve()
    bazaar_path = Path(bazaar_path).resolve()
    if fulfillment_path.parent != bazaar_path.parent:
        raise RuntimeError("Both databases must share the guarded data directory")
    if not fulfillment_path.is_file() or not bazaar_path.is_file():
        raise RuntimeError("Both initialized SQLite databases must already exist")
    data_dir = fulfillment_path.parent
    backup_root = Path(backup_dir).resolve() if backup_dir else data_dir / "backups"
    run_dir: Path | None = None

    with exclusive_maintenance(data_dir):
        if not dry_run:
            run_dir = backup_root / _stamp()
            _backup(fulfillment_path, run_dir / "fulfillment.sqlite")
            _backup(bazaar_path, run_dir / "bazaar.sqlite")
        original_path = fulfillment.DB_PATH
        fulfillment.DB_PATH = fulfillment_path
        db = sqlite3.connect(fulfillment_path, timeout=1, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=1000")
        db.execute("PRAGMA foreign_keys=ON")
        token = fulfillment._active_db.set(db)
        try:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = _run_transaction(
                    db,
                    target=target,
                    expected_total=expected_total,
                    dry_run=dry_run,
                    failpoint=failpoint,
                )
                db.execute("ROLLBACK" if dry_run else "COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        finally:
            fulfillment._active_db.reset(token)
            db.close()
            fulfillment.DB_PATH = original_path
        if run_dir is not None:
            report = {
                **result,
                "completed_at": _now(),
                "reason": REASON,
                "backups": {
                    "fulfillment": str(run_dir / "fulfillment.sqlite"),
                    "bazaar": str(run_dir / "bazaar.sqlite"),
                },
            }
            report_path = run_dir / "report.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            result = {**report, "report": str(report_path)}
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fulfillment-db", type=Path, required=True)
    parser.add_argument("--bazaar-db", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument(
        "--apply",
        action="store_true",
        help="apply exactly 800 corrections; API must be stopped",
    )
    args = parser.parse_args()
    result = repair_fleet_issues(
        args.fulfillment_db,
        args.bazaar_db,
        dry_run=not args.apply,
        backup_dir=args.backup_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())