"""Immutable input capture for isolated historical fulfillment replays."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import uuid
import zipfile
from pathlib import Path
from typing import Any

import fulfillment_api as fulfillment
import persona_v2
from fleet_readiness import asset_readiness, robot_readiness

REQUIRED_MEMBERS = ("synthetic_orders_7000.csv", "synthetic_shipments_7000.csv")
FLEET_DATASETS = ("robots", "maintenance", "control_assets")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_request_id(zip_hash: str, source_order_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fulfillment-replay:{zip_hash}:{source_order_id}"))


def snapshot_sqlite(live_path: Path, destination: Path) -> None:
    """Use SQLite backup from a query-only source connection."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{live_path.resolve()}?mode=ro", uri=True)
    target = sqlite3.connect(destination)
    try:
        source.execute("PRAGMA query_only=ON")
        source.backup(target)
    finally:
        target.close()
        source.close()


def _scenario_rows(db: sqlite3.Connection, dataset: str) -> tuple[dict[str, Any], ...]:
    rows = tuple(dict(row) for row in fulfillment._raw_source_rows(dataset))
    try:
        overrides = {
            int(row["row_index"]): json.loads(row["values_json"])
            for row in db.execute(
                "SELECT row_index,values_json FROM scenario_overrides WHERE dataset=?",
                (dataset,),
            )
        }
    except sqlite3.OperationalError:
        overrides = {}
    result = tuple({**row, **overrides.get(index, {})} for index, row in enumerate(rows))
    try:
        registered = tuple(
            json.loads(row["values_json"])
            for row in db.execute(
                "SELECT values_json FROM registered_resources WHERE dataset=? "
                "ORDER BY registered_at,row_id",
                (dataset,),
            )
        )
    except sqlite3.OperationalError:
        registered = ()
    return result + registered


def capture_sources(snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    """Capture corrected fleet rows from the snapshot, never an empty replay DB."""

    db = sqlite3.connect(snapshot_path)
    db.row_factory = sqlite3.Row
    try:
        raw = {name: _scenario_rows(db, name) for name in FLEET_DATASETS}
        effective = {
            name: persona_v2.effective_source_rows(db, name, raw[name])
            for name in FLEET_DATASETS
        }
        raw_condition_issues = sum(
            not robot_readiness(row, raw["maintenance"])[0] for row in raw["robots"]
        ) + sum(not asset_readiness(row)[0] for row in raw["control_assets"])
        effective_condition_issues = sum(
            not robot_readiness(row, effective["maintenance"])[0]
            for row in effective["robots"]
        ) + sum(
            not asset_readiness(row)[0] for row in effective["control_assets"]
        )
        current_open_issues = db.execute(
            """SELECT count(*) FROM persona_interventions
               WHERE status<>'resolved'
                 AND kind IN ('fleet_readiness','control_asset_readiness')
                 AND (dedupe_key LIKE 'fleet_readiness:%'
                      OR dedupe_key LIKE 'v2:control_asset:%')"""
        ).fetchone()[0]
        correction_count = db.execute(
            "SELECT count(*) FROM persona_source_corrections"
        ).fetchone()[0]
        task_seconds = int(
            db.execute(
                "SELECT value FROM config WHERE key='task_duration_seconds'"
            ).fetchone()[0]
        )
    finally:
        db.close()
    payload = {
        "effective": {key: list(value) for key, value in effective.items()},
        "source_counts": {key: len(value) for key, value in effective.items()},
        "correction_count": correction_count,
        "raw_condition_issues": raw_condition_issues,
        "effective_condition_issues": effective_condition_issues,
        "repair_baseline_issues": 891,
        "effective_fitness_issues": current_open_issues,
        "task_duration_seconds": task_seconds,
        "note": "Fleet rows include scenario overlays followed by durable persona corrections.",
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def read_inputs(zip_path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with zipfile.ZipFile(zip_path) as archive:
        missing = set(REQUIRED_MEMBERS) - set(archive.namelist())
        if missing:
            raise ValueError(f"Replay archive is missing: {sorted(missing)}")
        orders = list(
            csv.DictReader(io.TextIOWrapper(archive.open(REQUIRED_MEMBERS[0]), encoding="utf-8"))
        )
        shipments = list(
            csv.DictReader(io.TextIOWrapper(archive.open(REQUIRED_MEMBERS[1]), encoding="utf-8"))
        )
    order_ids = [row["order_id"] for row in orders]
    shipment_ids = [row["order_id"] for row in shipments]
    if len(orders) != 7000 or len(shipments) != 7000:
        raise ValueError(f"Expected 7000 orders and shipments; found {len(orders)} and {len(shipments)}")
    if len(set(order_ids)) != len(order_ids) or len(set(shipment_ids)) != len(shipment_ids):
        raise ValueError("Order and shipment identities must be unique")
    if set(order_ids) != set(shipment_ids):
        raise ValueError("Shipment benchmark must match the selected orders exactly")
    return orders, {row["order_id"]: row for row in shipments}
