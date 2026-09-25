"""Read-only frozen DC-01 evidence for the transfer sandbox.

This module deliberately does not import fulfillment_api, source_rows, schema
helpers, or any reconciliation code. SQLite is opened in transactional
read-only mode and every object returned to callers is detached from
operational state.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT / "brownfield" / "AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2" / "data" / "raw"
DB_PATH = Path(os.environ.get("FULFILLMENT_DB_PATH", ROOT / ".local" / "fulfillment.sqlite"))
TTL_SECONDS = 1800
MAX_SNAPSHOTS = 64
# Lifecycle assignment/evolution is scheduled once per 60 seconds.
LIFECYCLE_FRESHNESS_SECONDS = 60
PICK_TYPES = {"AGV", "AMR", "CASE_PICKER", "FORK_AMR"}
TRANSFER_TYPES = PICK_TYPES | {"PALLET_MOVER", "TUGGER"}
_lock = threading.Lock()
_snapshots: dict[str, tuple[float, dict[str, Any]]] = {}


class SnapshotError(RuntimeError):
    pass


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _csv(name: str) -> list[dict[str, str]]:
    with (SOURCE_ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _ro_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SnapshotError("Operational database is unavailable; live snapshot cannot be created.")
    db = sqlite3.connect(f"file:{DB_PATH.resolve()}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    # Python's sqlite3 driver does not start a transaction for plain SELECTs.
    # Begin one explicitly so every live input is read from one SQLite snapshot.
    db.execute("BEGIN")
    return db


def _overlays(db: sqlite3.Connection, dataset: str) -> dict[int, dict[str, Any]]:
    table = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scenario_overrides'"
    ).fetchone()
    if table is None:
        # Older operational databases legitimately predate scenario overlays.
        return {}
    try:
        rows = db.execute(
            "SELECT row_index,values_json FROM scenario_overrides WHERE dataset=? ORDER BY row_index",
            (dataset,),
        )
        result: dict[int, dict[str, Any]] = {}
        for row in rows:
            values = json.loads(row["values_json"])
            if not isinstance(values, dict):
                raise ValueError("overlay values must be an object")
            result[int(row["row_index"])] = values
        return result
    except (sqlite3.OperationalError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Scenario overrides for {dataset} could not be read.") from exc


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _reference_rows(db: sqlite3.Connection, filename: str, dataset: str) -> list[dict[str, Any]]:
    rows = _csv(filename)
    overlays = _overlays(db, dataset)
    for index, values in overlays.items():
        if 0 <= index < len(rows) and isinstance(values, dict):
            rows[index].update(values)
    return rows


def _map(zones: list[dict[str, Any]]) -> dict[str, Any]:
    selected = sorted(
        [z for z in zones if z.get("warehouse_id") == "DC-01"],
        key=lambda z: z.get("zone_id", ""),
    )
    if len(selected) != 12:
        raise SnapshotError(f"DC-01 reference data has {len(selected)} zones; exactly 12 are required.")
    nodes: list[dict[str, Any]] = []
    mapped: list[dict[str, Any]] = []
    for index, zone in enumerate(selected):
        col, row = index % 4, index // 4
        x, y = 70 + col * 245, 70 + row * 185
        zid = str(zone["zone_id"])
        mapped.append({
            "id": zid, "label": zid, "zone_type": zone.get("zone_type"),
            "x": x, "y": y, "width": 190, "height": 125,
            "mapping": "illustrative_assumed_coordinate",
            "source_map_version": zone.get("map_version"),
            "robot_access": zone.get("robot_access"),
        })
        nodes.append({"id": zid, "x": x + 95, "y": y + 62, "zone_id": zid})
    nodes.extend([
        {"id": f"AISLE-{row + 1}", "x": 1080, "y": 132 + row * 185, "zone_id": None}
        for row in range(3)
    ])
    nodes.append({"id": "CONVEYOR", "x": 1160, "y": 350, "zone_id": None})
    edges: list[dict[str, str]] = []
    for row in range(3):
        row_ids = [selected[row * 4 + col]["zone_id"] for col in range(4)]
        edges.extend({"from": str(a), "to": str(b)} for a, b in zip(row_ids, row_ids[1:]))
        edges.append({"from": str(row_ids[-1]), "to": f"AISLE-{row + 1}"})
        edges.append({"from": f"AISLE-{row + 1}", "to": "CONVEYOR"})
    for row in range(2):
        edges.append({"from": f"AISLE-{row + 1}", "to": f"AISLE-{row + 2}"})
    return {
        "width": 1220, "height": 700, "zones": mapped, "nodes": nodes, "edges": edges,
        "conveyor": {"id": "CONVEYOR-01", "node_id": "CONVEYOR", "label": "Conveyor receipt"},
        "geometry_provenance": "Illustrative deterministic layout using live zone IDs; coordinates are assumed, not surveyed.",
    }


def _inventory(db: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = db.execute(
            """SELECT id,source_row_index,sku,location,zone,inventory_status,
                      wms_qty,erp_qty,vision_qty,weight_kg,blocked_allocation,revision,updated_at
               FROM inventory_snapshot WHERE warehouse_id='DC-01'
               ORDER BY sku,location,id"""
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise SnapshotError("Operational inventory snapshot is not initialized.") from exc
    result = []
    for row in rows:
        item = dict(row)
        quantities = [item.get("wms_qty"), item.get("erp_qty"), item.get("vision_qty")]
        free = min(int(value) for value in quantities) if all(isinstance(v, int) for v in quantities) else 0
        item["available_unreserved_qty"] = (
            max(0, free)
            if item["inventory_status"] == "AVAILABLE" and not item["blocked_allocation"]
            else 0
        )
        item["source_id"] = f"inventory_snapshot:{item['id']}"
        # This table's quantities are already net of operational reservations.
        item["quantity_semantics"] = "free_net_of_reservations"
        result.append(item)
    return result


def _robots(
    db: sqlite3.Connection,
    reference: list[dict[str, Any]],
    map_data: dict[str, Any],
    clock: datetime,
) -> list[dict[str, Any]]:
    lifecycle = {
        row["resource_id"]: dict(row)
        for row in db.execute(
            """SELECT resource_id,resource_kind,resource_type,warehouse_id,fitness_status,
                      fitness_reasons,charging,battery_pct,battery_at,current_task_id,
                      current_stage,updated_at,revision
               FROM resource_lifecycle WHERE resource_kind='robot' AND warehouse_id='DC-01'"""
        )
    }
    zone_nodes = [zone["id"] for zone in map_data["zones"]]
    result = []
    for index, source in enumerate(r for r in reference if r.get("warehouse_id") == "DC-01"):
        rid = str(source.get("robot_id") or "")
        live = lifecycle.get(rid)
        reasons: list[str] = []
        if live is None:
            reasons.append("Missing persisted lifecycle evidence")
        else:
            try:
                parsed = json.loads(live.get("fitness_reasons") or "[]")
                reasons.extend(str(v) for v in parsed if v)
            except (TypeError, ValueError):
                reasons.append("Malformed lifecycle fitness reasons")
            if str(live.get("fitness_status")).upper() not in {"Y", "FIT", "READY"}:
                reasons.append(f"Lifecycle fitness is {live.get('fitness_status')}")
            if live.get("current_task_id"):
                reasons.append(f"Claimed by task {live['current_task_id']}")
            if str(live.get("charging")).upper() in {"Y", "YES", "TRUE", "1"}:
                reasons.append("Currently charging")
            updated = _timestamp(live.get("updated_at"))
            battery_at = _timestamp(live.get("battery_at"))
            if updated is None:
                reasons.append("Malformed lifecycle updated_at evidence")
            if battery_at is None:
                reasons.append("Malformed lifecycle battery_at evidence")
            if updated is not None and (clock - updated).total_seconds() > LIFECYCLE_FRESHNESS_SECONDS:
                reasons.append(
                    f"Lifecycle evidence is older than {LIFECYCLE_FRESHNESS_SECONDS} seconds"
                )
            if battery_at is not None and (clock - battery_at).total_seconds() > LIFECYCLE_FRESHNESS_SECONDS:
                reasons.append(
                    f"Battery evidence is older than {LIFECYCLE_FRESHNESS_SECONDS} seconds"
                )
        robot_type = str((live or {}).get("resource_type") or source.get("robot_type") or "")
        try:
            capacity = float(source.get("payload_kg"))
        except (TypeError, ValueError):
            capacity = None
        if capacity is None or not math.isfinite(capacity) or capacity <= 0:
            reasons.append("Missing positive payload capacity")
        battery = live.get("battery_pct") if live else None
        if not isinstance(battery, (int, float)) or not math.isfinite(float(battery)):
            reasons.append("Missing evolved lifecycle battery evidence")
        elif float(battery) <= 10:
            reasons.append("Lifecycle battery is at or below 10%")
        capabilities = []
        if robot_type in PICK_TYPES:
            capabilities.append("pick")
        if robot_type in TRANSFER_TYPES:
            capabilities.append("transfer")
        if not capabilities:
            reasons.append(f"Robot type {robot_type or 'missing'} is not transfer-compatible")
        result.append({
            "id": rid, "source_id": rid, "type": robot_type, "capacity_kg": capacity,
            "battery_percent": battery, "battery_at": live.get("battery_at") if live else None,
            "lifecycle_updated_at": live.get("updated_at") if live else None,
            "lifecycle_evidence_age_seconds": (
                max(0.0, (clock - _timestamp(live.get("updated_at"))).total_seconds())
                if live and _timestamp(live.get("updated_at")) is not None else None
            ),
            "battery_evidence_age_seconds": (
                max(0.0, (clock - _timestamp(live.get("battery_at"))).total_seconds())
                if live and _timestamp(live.get("battery_at")) is not None else None
            ),
            "state": "blocked" if reasons else "idle", "available": not reasons,
            "capabilities": capabilities, "eligible": not reasons,
            "exclusion_reasons": reasons, "start_node": zone_nodes[index % len(zone_nodes)],
            "current_task_id": live.get("current_task_id") if live else None,
            "lifecycle_revision": live.get("revision") if live else None,
            "provenance": {"reference": "robots.csv with direct scenario overlay", "fitness": "resource_lifecycle"},
        })
    return result


def create_snapshot(mode: str = "live") -> dict[str, Any]:
    if mode == "synthetic_demo":
        from transfer_demo import synthetic_snapshot
        snap = synthetic_snapshot()
    elif mode != "live":
        raise SnapshotError("mode must be live or synthetic_demo")
    else:
        with _ro_db() as db:
            zones = _reference_rows(db, "zones.csv", "zones")
            robot_refs = _reference_rows(db, "robots.csv", "robots")
            map_data = _map(zones)
            inventory = _inventory(db)
            lifecycle_values = [r["updated_at"] for r in db.execute(
                "SELECT updated_at FROM resource_lifecycle WHERE warehouse_id='DC-01' AND updated_at IS NOT NULL"
            )]
            lifecycle_times = [_timestamp(value) for value in lifecycle_values]
            valid_lifecycle_times = [value for value in lifecycle_times if value is not None]
            if not valid_lifecycle_times:
                raise SnapshotError("Live simulation clock evidence is unavailable.")
            clock = max(valid_lifecycle_times)
            clock_at = _iso(clock)
            robots = _robots(db, robot_refs, map_data, clock)
        eligible = sorted((r for r in robots if r["eligible"]), key=lambda r: r["id"])
        blockers = []
        if not any("pick" in r["capabilities"] for r in eligible):
            blockers.append("Eligible DC-01 fleet has no pick resource.")
        if not any("transfer" in r["capabilities"] for r in eligible):
            blockers.append("Eligible DC-01 fleet has no transfer resource.")
        snap = {
            "warehouse_id": "DC-01", "mode": "live", "map": map_data,
            "robots": robots, "selected_robot_ids": [r["id"] for r in eligible],
            "inventory": inventory, "blockers": blockers,
            "clock": {"at": clock_at, "timezone": "UTC", "source": "resource_lifecycle live simulation clock"},
            "assumptions": [
                "Frozen read-only snapshot; no reservations, dispatches, schema changes, or source reconciliation.",
                "Inventory quantities are already free and net of reservations; they are not reduced again.",
                "Exactly 12 live DC-01 zone IDs are retained; coordinates and graph are illustrative assumptions.",
                "Lifecycle battery and fitness are live evidence; source battery is not reused.",
                f"Lifecycle and battery evidence older than {LIFECYCLE_FRESHNESS_SECONDS} seconds "
                "relative to the frozen simulation clock is excluded from robot readiness.",
                "The server selects every eligible frozen DC-01 robot; clients cannot choose a subset.",
            ],
        }
    now = datetime.now(timezone.utc)
    canonical = json.dumps(snap, sort_keys=True, separators=(",", ":"), default=str)
    snap["snapshot_id"] = "TS-" + uuid.uuid4().hex
    snap["snapshot_at"] = _iso(now)
    snap["expires_at"] = _iso(now + timedelta(seconds=TTL_SECONDS))
    snap["source_version"] = hashlib.sha256(canonical.encode()).hexdigest()
    with _lock:
        _purge()
        _snapshots[snap["snapshot_id"]] = (time.monotonic() + TTL_SECONDS, copy.deepcopy(snap))
        while len(_snapshots) > MAX_SNAPSHOTS:
            oldest = min(_snapshots, key=lambda key: _snapshots[key][0])
            _snapshots.pop(oldest, None)
    return copy.deepcopy(snap)


def _purge() -> None:
    now = time.monotonic()
    for key in [key for key, value in _snapshots.items() if value[0] <= now]:
        _snapshots.pop(key, None)


def get_snapshot(snapshot_id: str) -> dict[str, Any]:
    with _lock:
        _purge()
        entry = _snapshots.get(snapshot_id)
        if not entry:
            raise SnapshotError("Snapshot is unknown or expired; create a new preview.")
        return copy.deepcopy(entry[1])


def public_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    inventory = snap["inventory"]
    eligible = [r for r in inventory if r["available_unreserved_qty"] > 0 and r.get("weight_kg")]
    return {
        "warehouse_id": snap["warehouse_id"], "mode": snap["mode"],
        "ready": not snap["blockers"], "blockers": snap["blockers"],
        "snapshot": {key: snap[key] for key in ("snapshot_id", "snapshot_at", "expires_at", "source_version")} | {"clock": snap["clock"]},
        "map": snap["map"], "robots": [r for r in snap["robots"] if r["id"] in snap["selected_robot_ids"]],
        "robot_candidates": snap["robots"],
        "selection": {"selected_robot_ids": snap["selected_robot_ids"],
                      "required_count": len(snap["selected_robot_ids"]), "editable": False,
                      "policy": "all_eligible_dc01"},
        "inventory_summary": {"eligible_skus": len({r["sku"] for r in eligible}), "eligible_bins": len(eligible)},
        "assumptions": snap["assumptions"],
    }