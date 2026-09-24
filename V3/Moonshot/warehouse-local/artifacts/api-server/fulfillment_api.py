"""Transactional, simulation-only customer fulfillment proof of concept.

The brownfield data is deliberately read-only reference material.  This
module owns a separate SQLite database for customer orders and the simulated
reservation/task executor; it never imports or mutates the legacy database.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, conint, confloat, validator

import fulfillment_v2
import demand_forecast
import robot_lifecycle
import order_progress
from fleet_readiness import robot_readiness


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = (
    ROOT
    / "brownfield"
    / "AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2"
)
DB_PATH = Path(os.environ.get("FULFILLMENT_DB_PATH", ROOT / ".local" / "fulfillment.sqlite"))
STAGES = ("pick", "transfer", "pack", "dispatch")
ROBOT_STAGE_TYPES: dict[str, set[str]] = {
    # Demo compatibility assumptions only: these mappings are not a live
    # warehouse topology or a controller certification.
    "pick": {"AGV", "AMR", "CASE_PICKER", "FORK_AMR"},
    "transfer": {"AGV", "AMR", "FORK_AMR", "PALLET_MOVER", "TUGGER"},
}
MANUAL_PAYLOAD_LIMIT_KG = 25.0
DEFAULT_CONFIG = {
    "min_stock_threshold": 10,
    "unit_weight_kg": 1.0,
    "staging_capacity": 10,
    "shift": "1",
    "manual_payload_limit_kg": MANUAL_PAYLOAD_LIMIT_KG,
    "task_duration_seconds": 45,
}

DATASETS: dict[str, str] = {
    "warehouses": "data/reference/warehouses.csv",
    "skus": "data/reference/skus.csv",
    "vendors": "data/reference/vendors.csv",
    "robots": "data/raw/robots.csv",
    "robot_aliases": "data/raw/robot_aliases.csv",
    "inventory": "data/raw/inventory_snapshot.csv",
    "tasks": "data/raw/tasks.csv",
    "maintenance": "data/raw/maintenance.csv",
    "priorities": "data/shadow/wave_priority_FINAL_v7.csv",
    "zones": "data/raw/zones.csv",
    "telemetry": "data/telemetry/robot_telemetry.csv",
    "vision_observations": "data/telemetry/vision_observations.csv",
    "safety_events": "data/raw/safety_events.csv",
    "events": "data/raw/events.jsonl",
    "charging_state": "data/raw/charging_state.csv",
    "control_assets": "data/raw/control_assets.csv",
    "labor_capacity": "data/raw/labor_capacity.csv",
    "orders": "data/raw/orders.csv",
    "shipments": "data/raw/shipments.csv",
}

# This is intentionally explicit: resource-browser edits are useful for
# scenario exploration, but most of the supplied brownfield files are context
# and do not feed this POC's order planner.
PLANNING_IMPACT: dict[str, str] = {
    "inventory": (
        "Policy v2 uses eligible location free stock: minimum(WMS, ERP, vision). "
        "Acceptance debits each source and credits ledger-controlled reservations; "
        "reserved quantities must not be subtracted again or edited directly. "
        "Per-unit weight_kg is synthetic demo data: validated consistent SKU "
        "weights times ordered quantities determine pick/transfer payload and manual limits."
    ),
    "robots": (
        "Source readiness requires HEALTHY health, a nonblank non-EXPIRED safety "
        "certificate status, ONLINE/INTERMITTENT connectivity, and ready linked "
        "maintenance. Warehouse, type, payload and exclusive claims remain "
        "independent assignment constraints; battery and calibration are not gates."
    ),
    "maintenance": (
        "Policy v2 requires known maintenance evidence, no OPEN/IN_PROGRESS work "
        "and AVAILABLE fleet availability. Blocking evidence wins; a safety "
        "release flag does not override these rules."
    ),
    "labor_capacity": (
        "Direct planner input: warehouse_id, shift, actual_workers, "
        "certified_robot_operators, and pack_staff bound shared labor pools."
    ),
    "control_assets": (
        "Policy v2 selects stage-compatible control assets in the warehouse "
        "with AVAILABLE state, CLEAR maintenance and no conflicting resource claim."
    ),
    "warehouses": (
        "Order-input validation context: warehouse_id is checked against this "
        "dataset; it is not otherwise a scheduling capacity input."
    ),
    "skus": (
        "Order-input validation context: sku is checked against this dataset; "
        "it is not otherwise a scheduling capacity input."
    ),
}
_CONTEXT_ONLY_IMPACT = (
    "Context-only for this POC planner: edits are visible in the resource browser "
    "and catalog but are not consumed by order scheduling."
)

# Identifiers and relationship keys remain visible but cannot be changed.  A
# conservative explicit set protects references such as zones and locations
# while leaving operational state (health, quantities, capacities, etc.)
# scenario-editable.
_REFERENCE_FIELDS = {
    "sku",
    "warehouse_id",
    "robot_id",
    "vendor_id",
    "asset_id",
    "work_order_id",
    "task_id",
    "order_id",
    "shipment_id",
    "event_id",
    "camera_id",
    "zone_id",
    "entity_id",
    "fleet_id",
    "source_zone",
    "dest_zone",
    "location",
    "zone",
    "preferred_charger",
    "shift",
    "source",
}
ASSUMPTIONS = [
    "All supplied source files are immutable reference snapshots, not live operational state.",
    "Every assignment, reservation, task transition, and completion in this POC is simulated; no live feasibility certification or physical actuation is performed.",
    "Policy v2 allocates the minimum of free WMS, ERP and vision quantities. Acceptance debits all three and credits reserved stock; Pick releases that reservation without another source debit.",
    "All simulated robot and control-asset stages use the shared configurable task duration (45 seconds by default) after resource acquisition; it is not an observed handling rate.",
    "Inventory weight_kg values are synthetic demo per-unit SKU weights, not measured physical weights. "
    "New plans and explicit replans use the sum of quantity × SKU weight; every inventory row for "
    "each requested SKU must have a consistent positive finite weight, with no default fallback.",
    "Policy v2 plans independently per SKU: location-level Pick tasks precede Move, Pack_feed and Stage. Payload uses the quantity carried by each task; required resources have no manual bypass.",
    "The deprecated unit_weight_kg configuration is retained for compatibility only and is not used by new plans or replans. Existing saved plans are not automatically recalculated.",
    "Missing topology, travel, rate, and live-busy signals are configurable/demo assumptions rather than invented real metrics.",
    "Historical policy-v1 plans retain their saved deadlines and task stages. Imported legacy tasks are context only; POC-persisted tasks hold exclusive simulator resource claims.",
]

_db_lock = threading.RLock()
_active_db: ContextVar[sqlite3.Connection | None] = ContextVar(
    "fulfillment_active_db", default=None
)
_executor_stop = threading.Event()
_executor_thread: threading.Thread | None = None
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Clock seam used by tests and by the persisted executor."""

    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError("must include an explicit UTC offset (use a trailing Z)")
    return result.astimezone(timezone.utc)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=len(DATASETS))
def _raw_source_rows(dataset: str) -> tuple[dict[str, Any], ...]:
    """Load the complete immutable source dataset without scenario overlays."""

    relative = DATASETS[dataset]
    path = SOURCE_ROOT / relative
    if path.suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return tuple(rows)
    with path.open(encoding="utf-8", newline="") as handle:
        return tuple(dict(row) for row in csv.DictReader(handle))


def _source_field_union(dataset: str) -> list[str]:
    """Return every header/key in source order, not only keys in the first row."""

    fields: list[str] = []
    seen: set[str] = set()
    for row in _raw_source_rows(dataset):
        for field in row:
            if field not in seen:
                seen.add(field)
                fields.append(field)
    return fields


def _read_scenario_overrides(
    dataset: str,
) -> dict[int, dict[str, Any]]:
    """Read overrides through the caller's transaction when one is active.

    Planner calls source_rows while holding BEGIN IMMEDIATE.  Reusing that
    connection avoids a nested SQLite writer/read connection (and the lock
    inversion that can otherwise produce SQLITE_BUSY under concurrent API
    requests).  A short-lived read connection is used only for top-level
    browser/catalog reads.
    """

    active = _active_db.get()
    if active is not None:
        rows = active.execute(
            "SELECT row_index,values_json FROM scenario_overrides WHERE dataset=?",
            (dataset,),
        )
        return {
            int(row["row_index"]): json.loads(row["values_json"])
            for row in rows
        }
    _init_db()
    with _db_lock:
        db = sqlite3.connect(DB_PATH, timeout=5)
        try:
            rows = db.execute(
                "SELECT row_index,values_json FROM scenario_overrides WHERE dataset=?",
                (dataset,),
            )
            return {
                int(row[0]): json.loads(row[1])
                for row in rows
            }
        finally:
            db.close()


def _source_rows_with_meta(
    dataset: str,
) -> list[tuple[dict[str, Any], int, bool]]:
    fields = _source_field_union(dataset)
    overrides = _read_scenario_overrides(dataset)
    result: list[tuple[dict[str, Any], int, bool]] = []
    for row_index, original in enumerate(_raw_source_rows(dataset)):
        row = {field: original.get(field) for field in fields}
        override = overrides.get(row_index)
        if override:
            row.update(override)
        result.append((row, row_index, bool(override)))
    return result


def source_rows(dataset: str) -> tuple[dict[str, Any], ...]:
    """Return complete source rows with the persistent SQLite scenario overlay."""

    return tuple(row for row, _, _ in _source_rows_with_meta(dataset))


@lru_cache(maxsize=1)
def source_stock_index() -> dict[tuple[str, str], dict[str, int]]:
    """Immutable one-pass WMS stock index used by all ATP calculations.

    The raw snapshot never changes during a server process, while POC
    commitments are intentionally queried from SQLite for every operation.
    Keeping only the immutable source aggregation cached avoids repeatedly
    scanning all 9,360 inventory rows without caching live state.
    """

    index: dict[tuple[str, str], dict[str, int]] = {}
    for row in source_rows("inventory"):
        key = (row.get("warehouse_id", ""), row.get("sku", ""))
        totals = index.setdefault(key, {"wms": 0, "source_reserved": 0})
        if row.get("inventory_status") == "AVAILABLE":
            totals["wms"] += _int(row.get("wms_qty"))
            totals["source_reserved"] += _int(row.get("reserved_qty"))
    return index


def source_fields(dataset: str) -> list[str]:
    return _source_field_union(dataset)


def _scenario_revision(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT revision FROM scenario_state WHERE id=1").fetchone()
    return int(row["revision"]) if row else 0


def _scenario_modified_count(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT COUNT(*) AS count FROM scenario_overrides").fetchone()
    return int(row["count"]) if row else 0


def _scenario_details(db: sqlite3.Connection) -> dict[str, int]:
    return {
        "revision": _scenario_revision(db),
        "modified_count": _scenario_modified_count(db),
    }


def _planning_impact(dataset: str) -> str:
    return PLANNING_IMPACT.get(dataset, _CONTEXT_ONLY_IMPACT)


def _field_type(dataset: str, field: str) -> str:
    values = [
        row.get(field)
        for row in _raw_source_rows(dataset)
        if row.get(field) not in (None, "")
    ]
    if field.endswith("_json") or any(isinstance(value, (dict, list)) for value in values):
        return "json"
    normalized = {str(value).strip().lower() for value in values}
    if normalized and normalized <= {"y", "n", "yes", "no", "true", "false"}:
        return "boolean"
    numeric = True
    for value in values:
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            numeric = False
            break
        if not math.isfinite(number):
            numeric = False
            break
    if values and numeric:
        return "number"
    return "string"


def _field_types(dataset: str) -> dict[str, str]:
    return {field: _field_type(dataset, field) for field in source_fields(dataset)}


def _excluded_fields(dataset: str) -> dict[str, str]:
    excluded: dict[str, str] = {}
    for field in source_fields(dataset):
        if field.startswith("poc_"):
            excluded[field] = "Computed POC field; it is never scenario-editable."
        elif field in _REFERENCE_FIELDS or field.endswith("_id"):
            excluded[field] = (
                "Identity/reference key; editing it would break source relationships."
            )
    return excluded


def _editable_fields(dataset: str) -> list[str]:
    excluded = _excluded_fields(dataset)
    return [field for field in source_fields(dataset) if field not in excluded]


def _active_order_guard(db: sqlite3.Connection) -> None:
    row = db.execute(
        """
        SELECT COUNT(*) AS count FROM orders
        WHERE status IN ('planned','queued','running')
           OR status IN ('active','partially_fulfilled','recovery_required')
           OR EXISTS (
               SELECT 1 FROM tasks
               WHERE tasks.order_id=orders.id
                 AND tasks.status IN ('queued','running','paused')
           )
        """
    ).fetchone()
    if row and row["count"]:
        raise HTTPException(
            409,
            "Scenario changes are blocked while a planned, queued, running, or "
            "paused order exists. Cancel the order or let it finish, then retry.",
        )


def _resource_contract(db: sqlite3.Connection, dataset: str) -> dict[str, Any]:
    details = _scenario_details(db)
    excluded = _excluded_fields(dataset)
    return {
        "fields": source_fields(dataset),
        "editable_fields": _editable_fields(dataset),
        "field_types": _field_types(dataset),
        "excluded_fields": excluded,
        # Keep a named alias for clients that prefer an explicit reason map.
        "excluded_field_reasons": excluded,
        "planning_impact": _planning_impact(dataset),
        "revision": details["revision"],
        "scenario_modified_count": details["modified_count"],
    }


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HTTPException(422, f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise HTTPException(422, f"{field} must be a finite number")
    if field in {
        "battery_soc",
        "battery_soh",
        "soc_pct",
        "soh_pct",
        "confidence",
        "localization_confidence",
    } and not 0 <= number <= (1 if "confidence" in field else 100):
        raise HTTPException(422, f"{field} is outside its valid numeric domain")
    if (
        any(token in field for token in ("qty", "quantity", "workers", "capacity", "staff"))
        or field in {"payload_kg", "speed_mps", "planned_workers", "actual_workers"}
    ) and number < 0:
        raise HTTPException(422, f"{field} cannot be negative")
    return number


def _normalise_scenario_value(
    dataset: str, field: str, value: Any, original: Any
) -> Any:
    kind = _field_type(dataset, field)
    if kind == "string":
        if not isinstance(value, str):
            raise HTTPException(422, f"{field} must be a string")
        return value
    if kind == "number":
        number = _finite_number(value, field)
        # CSV rows are strings by design. Keep the wire/source representation
        # string-typed even when the UI submits a JSON number.
        original_text = "" if original is None else str(original)
        if "." not in original_text and "e" not in original_text.lower():
            if not number.is_integer():
                raise HTTPException(422, f"{field} must be an integer")
            return str(int(number))
        return str(number)
    if kind == "boolean":
        if isinstance(value, bool):
            truth = value
        elif isinstance(value, str) and value.strip().lower() in {
            "y",
            "yes",
            "true",
            "n",
            "no",
            "false",
        }:
            truth = value.strip().lower() in {"y", "yes", "true"}
        else:
            raise HTTPException(422, f"{field} must be a boolean")
        original_text = str(original or "").strip().lower()
        if original_text in {"y", "n"}:
            return "Y" if truth else "N"
        if original_text in {"yes", "no"}:
            return "yes" if truth else "no"
        if original_text in {"true", "false"}:
            return "true" if truth else "false"
        return truth
    if isinstance(value, (dict, list)):
        _validate_json_value(value, field)
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(
                value,
                parse_constant=lambda constant: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant {constant}")
                ),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"{field} must contain valid JSON") from exc
        if not isinstance(parsed, (dict, list)):
            raise HTTPException(422, f"{field} must contain a JSON object or array")
        return value
    raise HTTPException(422, f"{field} must contain a JSON object or array")


def _validate_json_value(value: Any, field: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise HTTPException(422, f"{field} contains a non-finite number")
    if isinstance(value, dict):
        for nested in value.values():
            _validate_json_value(nested, field)
    elif isinstance(value, list):
        for nested in value:
            _validate_json_value(nested, field)


def _validate_scenario_values(
    dataset: str,
    row: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(values, dict) or not values:
        raise HTTPException(422, "values must be a non-empty object")
    fields = set(source_fields(dataset))
    editable = set(_editable_fields(dataset))
    unknown = sorted(set(values) - fields)
    if unknown:
        raise HTTPException(422, f"Unknown source field(s): {', '.join(unknown)}")
    excluded = sorted(set(values) - editable)
    if excluded:
        reasons = _excluded_fields(dataset)
        detail = "; ".join(f"{field}: {reasons[field]}" for field in excluded)
        raise HTTPException(422, f"Non-editable source field(s): {detail}")
    return {
        field: _normalise_scenario_value(dataset, field, value, row.get(field))
        for field, value in values.items()
    }


def _scenario_row(
    db: sqlite3.Connection, dataset: str, row_id: int
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if dataset not in DATASETS:
        raise HTTPException(404, f"Unknown dataset {dataset}; see /api/fulfillment/catalog")
    rows = _source_rows_with_meta(dataset)
    if row_id < 0 or row_id >= len(rows):
        raise HTTPException(404, f"Unknown {dataset} scenario row {row_id}")
    row, _, modified = rows[row_id]
    raw = _raw_source_rows(dataset)[row_id]
    original = {field: raw.get(field) for field in source_fields(dataset)}
    return row, original, modified


def _scenario_mutation_result(
    db: sqlite3.Connection, dataset: str, row_id: int
) -> dict[str, Any]:
    _scenario_row(db, dataset, row_id)
    row = next(
        row for row in _resource_rows(db, dataset)
        if row.get("_scenario_row_id") == row_id
    )
    result = _resource_contract(db, dataset)
    result.update({"dataset": dataset, "row": dict(row)})
    return result


def patch_scenario_resource(
    dataset: str, row_id: int, values: dict[str, Any], revision: int
) -> dict[str, Any]:
    with db_transaction() as db:
        _active_order_guard(db)
        current = _scenario_revision(db)
        if revision != current:
            raise HTTPException(
                409,
                f"Scenario revision conflict: request has {revision}, current revision is "
                f"{current}. Refresh resources and retry.",
            )
        row, original, _ = _scenario_row(db, dataset, row_id)
        normalised = _validate_scenario_values(dataset, row, values)
        existing_row = db.execute(
            "SELECT values_json FROM scenario_overrides WHERE dataset=? AND row_index=?",
            (dataset, row_id),
        ).fetchone()
        merged = json.loads(existing_row["values_json"]) if existing_row else {}
        merged.update(normalised)
        # Writing the source value back removes that field from the overlay,
        # so reset-to-original behaves exactly like an untouched row.
        merged = {
            field: value
            for field, value in merged.items()
            if value != original.get(field)
        }
        if merged:
            db.execute(
                """
                INSERT INTO scenario_overrides(dataset,row_index,values_json)
                VALUES (?,?,?)
                ON CONFLICT(dataset,row_index) DO UPDATE SET values_json=excluded.values_json
                """,
                (dataset, row_id, json.dumps(merged, allow_nan=False)),
            )
        else:
            db.execute(
                "DELETE FROM scenario_overrides WHERE dataset=? AND row_index=?",
                (dataset, row_id),
            )
        db.execute("UPDATE scenario_state SET revision=revision+1 WHERE id=1")
        if dataset == "inventory":
            effective = db.execute(
                "SELECT id,revision FROM inventory_snapshot WHERE source_row_index=?",
                (row_id,),
            ).fetchone()
            source_values = {
                field: _int(value)
                for field, value in normalised.items()
                if field in {"wms_qty", "erp_qty", "vision_qty"}
            }
            if effective and source_values:
                fulfillment_v2.correct_inventory(
                    db,
                    effective["id"],
                    source_values,
                    "free",
                    effective["revision"],
                    "Legacy scenario editor synchronized to effective free stock",
                    "scenario-editor",
                    utc_now(),
                )
        source_stock_index.cache_clear()
        return _scenario_mutation_result(db, dataset, row_id)


def reset_scenario_resource(
    dataset: str, row_id: int, revision: int
) -> dict[str, Any]:
    with db_transaction() as db:
        _active_order_guard(db)
        current = _scenario_revision(db)
        if revision != current:
            raise HTTPException(
                409,
                f"Scenario revision conflict: request has {revision}, current revision is "
                f"{current}. Refresh resources and retry.",
            )
        _scenario_row(db, dataset, row_id)
        db.execute(
            "DELETE FROM scenario_overrides WHERE dataset=? AND row_index=?",
            (dataset, row_id),
        )
        db.execute("UPDATE scenario_state SET revision=revision+1 WHERE id=1")
        source_stock_index.cache_clear()
        return _scenario_mutation_result(db, dataset, row_id)


def reset_scenario(revision: int) -> dict[str, Any]:
    with db_transaction() as db:
        _active_order_guard(db)
        current = _scenario_revision(db)
        if revision != current:
            raise HTTPException(
                409,
                f"Scenario revision conflict: request has {revision}, current revision is "
                f"{current}. Refresh resources and retry.",
            )
        db.execute("DELETE FROM scenario_overrides")
        db.execute("UPDATE scenario_state SET revision=revision+1 WHERE id=1")
        source_stock_index.cache_clear()
        details = _scenario_details(db)
        return {
            "revision": details["revision"],
            "scenario_modified_count": details["modified_count"],
            "reset": True,
            "message": (
                "All source overlays reset. Consumed POC stock remains consumed; "
                "reset restores imported source values only and does not reverse "
                "completed fulfillment effects."
            ),
        }


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock:
        with sqlite3.connect(DB_PATH) as db:
            db.row_factory = sqlite3.Row
            db.executescript(
                """
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                warehouse_id TEXT NOT NULL,
                priority TEXT NOT NULL,
                ship_by TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                issues_json TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS order_lines (
                order_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                PRIMARY KEY(order_id, sku),
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                warehouse_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                consumed_qty INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                resource_id TEXT,
                resource_type TEXT,
                started_at TEXT,
                due_at TEXT,
                completed_at TEXT,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE TABLE IF NOT EXISTS task_resources (
                task_id TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                PRIMARY KEY(task_id, resource_id),
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                at TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE TABLE IF NOT EXISTS stock_effects (
                task_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS retired_order_requests (
                request_digest TEXT PRIMARY KEY
            );
            CREATE INDEX IF NOT EXISTS task_order_stage ON tasks(order_id, stage);
            CREATE INDEX IF NOT EXISTS orders_newest ON orders(created_at DESC,id DESC);
            CREATE INDEX IF NOT EXISTS orders_status_newest ON orders(status,created_at DESC,id DESC);
            CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS task_resource_status ON tasks(resource_id, status);
            CREATE INDEX IF NOT EXISTS reservation_stock ON reservations(warehouse_id, sku, status);
            CREATE TABLE IF NOT EXISTS scenario_state (
                id INTEGER PRIMARY KEY CHECK(id=1),
                revision INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS scenario_overrides (
                dataset TEXT NOT NULL,
                row_index INTEGER NOT NULL CHECK(row_index >= 0),
                values_json TEXT NOT NULL,
                PRIMARY KEY(dataset, row_index)
            )
            """
            )
            # Additive, nullable provenance fields keep every pre-existing POC
            # order readable while allowing external intake systems to retain
            # their own identity and service semantics.
            order_columns = {
                row[1] for row in db.execute("PRAGMA table_info(orders)").fetchall()
            }
            for column in (
                "source_order_id",
                "order_service",
                "order_source",
                "request_fingerprint",
            ):
                if column not in order_columns:
                    db.execute(f"ALTER TABLE orders ADD COLUMN {column} TEXT")
            for key, value in DEFAULT_CONFIG.items():
                db.execute(
                    "INSERT OR IGNORE INTO config(key, value) VALUES (?, ?)",
                    (key, str(value)),
                )
            db.execute("INSERT OR IGNORE INTO scenario_state(id, revision) VALUES (1, 0)")
            fulfillment_v2.ensure_schema(db, _raw_source_rows("inventory"), utc_now())
            demand_forecast.ensure_schema(db)
            robot_lifecycle.ensure_schema(db)
            order_progress.ensure_schema(db)
    # The index is process-local, while the database path is deliberately
    # replaceable by isolated tests. Initialization is therefore a safe cache
    # boundary as well as the schema migration point.
    source_stock_index.cache_clear()


def ensure_inventory(db: sqlite3.Connection) -> None:
    """Public idempotent v2 inventory/schema migration helper."""

    fulfillment_v2.ensure_schema(db, _raw_source_rows("inventory"), utc_now())


def inventory_rows(
    db: sqlite3.Connection, warehouse_id: str | None = None, sku: str | None = None
) -> list[dict[str, Any]]:
    ensure_inventory(db)
    return fulfillment_v2.inventory_rows(db, warehouse_id, sku)


def correct_inventory(
    db: sqlite3.Connection,
    row_id: int,
    values: dict[str, Any],
    basis: str,
    revision: int,
    reason: str,
    actor: str,
) -> dict[str, Any]:
    ensure_inventory(db)
    return fulfillment_v2.correct_inventory(
        db, row_id, values, basis, revision, reason, actor, utc_now()
    )


def reevaluate_held(db: sqlite3.Connection) -> int:
    ensure_inventory(db)
    # Stock corrections may reserve newly available stock, but never claim work.
    return fulfillment_v2.reevaluate_held(db, utc_now())


def v2_robot_eligibility(
    db: sqlite3.Connection,
    robot: dict[str, Any],
    warehouse_id: str,
    stage: str,
    payload_kg: float,
    used: set[str] | None = None,
) -> tuple[bool, list[str]]:
    return fulfillment_v2.robot_eligibility(
        db,
        robot,
        warehouse_id,
        stage,
        payload_kg,
        used or set(),
        source_rows("maintenance"),
        utc_now(),
    )


def v2_asset_eligibility(
    asset: dict[str, Any],
    warehouse_id: str,
    stage: str,
    used: set[str] | None = None,
    db: sqlite3.Connection | None = None,
) -> tuple[bool, list[str]]:
    return fulfillment_v2.asset_eligibility(
        asset, warehouse_id, stage, used or set(), db or _active_db.get()
    )


@contextmanager
def db_transaction(now: datetime | None = None):
    """Serialize local writes and use BEGIN IMMEDIATE for reservation safety."""

    _init_db()
    with _db_lock:
        db = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        token = _active_db.set(db)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            order_progress.sync(db, now or utc_now())
            robot_lifecycle.reconcile(db, now or utc_now(), source_rows)
            db.execute("COMMIT")
            try:
                export_path = DB_PATH.parent / "exports" / "orders.csv"
                if db.execute("SELECT 1 FROM order_export_dirty LIMIT 1").fetchone() or not export_path.exists():
                    order_progress.export_orders(db, export_path)
                    db.execute("DELETE FROM order_export_dirty")
            except Exception:
                logging.getLogger(__name__).exception("Orders CSV export failed; next transaction retries")
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            _active_db.reset(token)
            db.close()


@contextmanager
def _read_db():
    _init_db()
    db = sqlite3.connect(DB_PATH, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    token = _active_db.set(db)
    try:
        yield db
    finally:
        _active_db.reset(token)
        db.close()


def config_values(db: sqlite3.Connection) -> dict[str, Any]:
    values = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM config")}
    return {
        "min_stock_threshold": _int(values.get("min_stock_threshold"), 10),
        "unit_weight_kg": _float(values.get("unit_weight_kg"), 1.0),
        "staging_capacity": _int(values.get("staging_capacity"), 10),
        "shift": values.get("shift", DEFAULT_CONFIG["shift"]),
        "manual_payload_limit_kg": _float(
            values.get("manual_payload_limit_kg"), MANUAL_PAYLOAD_LIMIT_KG
        ),
        "task_duration_seconds": _int(
            values.get("task_duration_seconds"),
            DEFAULT_CONFIG["task_duration_seconds"],
        ),
    }


def source_shift_values() -> set[str]:
    return {str(row.get("shift", "")) for row in source_rows("labor_capacity") if row.get("shift")}


def _stock_commitments(
    db: sqlite3.Connection, warehouse_id: str | None = None, sku: str | None = None
) -> dict[tuple[str, str], dict[str, int]]:
    clauses = ["status IN ('active', 'consumed')"]
    params: list[Any] = []
    if warehouse_id:
        clauses.append("warehouse_id=?")
        params.append(warehouse_id)
    if sku:
        clauses.append("sku=?")
        params.append(sku)
    sql = (
        "SELECT warehouse_id,sku,"
        "SUM(CASE WHEN status='active' THEN quantity-consumed_qty ELSE 0 END) AS reserved,"
        "SUM(consumed_qty) AS consumed FROM reservations WHERE "
        + " AND ".join(clauses)
        + " GROUP BY warehouse_id,sku"
    )
    return {
        (row["warehouse_id"], row["sku"]): {
            "reserved": _int(row["reserved"]),
            "consumed": _int(row["consumed"]),
        }
        for row in db.execute(sql, params)
    }


def _raw_stock(warehouse_id: str, sku: str) -> dict[str, int]:
    totals = source_stock_index().get(
        (warehouse_id, sku), {"wms": 0, "source_reserved": 0}
    )
    return {
        "wms": totals["wms"],
        "source_reserved": totals["source_reserved"],
    }


def available_to_promise(
    db: sqlite3.Connection, warehouse_id: str, sku: str
) -> dict[str, int]:
    rows = inventory_rows(db, warehouse_id, sku)
    available = sum(row["allocatable_qty"] for row in rows)
    return {
        "wms_qty": sum(row["wms_qty"] for row in rows),
        "source_reserved_qty": sum(row["external_reserved_qty"] for row in rows),
        "poc_reserved": sum(row["reserved_qty"] for row in rows),
        "poc_consumed": sum(row["picked_qty"] + row["completed_qty"] for row in rows),
        "available_to_promise": available,
    }


def _available_from_totals(
    source: dict[str, int] | None,
    commitment: dict[str, int] | None,
) -> dict[str, int]:
    source = source or {"wms": 0, "source_reserved": 0}
    commitment = commitment or {"reserved": 0, "consumed": 0}
    return {
        "wms_qty": source["wms"],
        "source_reserved_qty": source["source_reserved"],
        "poc_reserved": commitment["reserved"],
        "poc_consumed": commitment["consumed"],
        "available_to_promise": max(
            0,
            source["wms"]
            - source["source_reserved"]
            - commitment["reserved"]
            - commitment["consumed"],
        ),
    }


def inventory_rows_with_metrics(db: sqlite3.Connection, warehouse_id: str | None = None):
    """Expose source-shaped rows with V2 location-free metrics."""
    effective = {
        row["source_row_index"]: row for row in inventory_rows(db, warehouse_id)
    }
    for source_row, row_id, modified in _source_rows_with_meta("inventory"):
        row = dict(source_row)
        row["_scenario_row_id"] = row_id
        row["_scenario_modified"] = modified
        if row_id in effective:
            current = effective[row_id]
            row.update(
                {
                    "inventory_row_id": current["inventory_row_id"],
                    "revision": current["revision"],
                    "effective_wms_qty": current["wms_qty"],
                    "effective_erp_qty": current["erp_qty"],
                    "effective_vision_qty": current["vision_qty"],
                    "effective_reserved_qty": current["reserved_qty"],
                    "picked_qty": current["picked_qty"],
                    "allocatable_qty": current["allocatable_qty"],
                    "blocked_allocation": bool(current["blocked_allocation"]),
                    "opening_discrepancy": current["opening_discrepancy"],
                }
            )
        if warehouse_id and row.get("warehouse_id") != warehouse_id:
            continue
        current = effective.get(row_id)
        row.update({
            "poc_reserved": current["reserved_qty"] if current else 0,
            "poc_consumed": (
                current["picked_qty"] + current["completed_qty"] if current else 0
            ),
            "available_to_promise": current["allocatable_qty"] if current else 0,
        })
        yield row


def maintenance_exclusions(warehouse_id: str) -> tuple[dict[str, Any], ...]:
    """Compatibility seam returning all site maintenance readiness evidence."""

    return tuple(
        row
        for row in source_rows("maintenance")
        if row.get("warehouse_id") == warehouse_id
    )


def robot_eligibility(
    robot: dict[str, Any],
    maintenance: tuple[dict[str, Any], ...],
) -> tuple[bool, list[str]]:
    return robot_readiness(robot, maintenance)


def _resource_usage(db: sqlite3.Connection, warehouse_id: str) -> set[str]:
    rows = db.execute(
        """
        SELECT resource_id FROM tasks
        JOIN orders ON orders.id=tasks.order_id
        WHERE orders.warehouse_id=? AND tasks.status IN ('pending','queued','running','paused')
          AND resource_id IS NOT NULL
        UNION
        SELECT task_resources.resource_id FROM task_resources
        JOIN tasks ON tasks.id=task_resources.task_id
        JOIN orders ON orders.id=tasks.order_id
        WHERE orders.warehouse_id=? AND tasks.status IN ('pending','queued','running','paused')
        """,
        (warehouse_id, warehouse_id),
    )
    used = {row["resource_id"] for row in rows}
    try:
        used.update(
            row["resource_id"]
            for row in db.execute(
                """SELECT tasks.resource_id FROM tasks
                   JOIN sub_orders ON sub_orders.id=tasks.sub_order_id
                   WHERE sub_orders.warehouse_id=?
                     AND tasks.status IN ('queued','running','paused')
                     AND tasks.resource_id IS NOT NULL""",
                (warehouse_id,),
            )
        )
    except sqlite3.OperationalError:
        pass
    return used


def _labor(warehouse_id: str, shift: str) -> dict[str, int] | None:
    for row in source_rows("labor_capacity"):
        if row.get("warehouse_id") == warehouse_id and str(row.get("shift")) == str(shift):
            return {
                "actual_workers": _int(row.get("actual_workers")),
                "certified_robot_operators": _int(row.get("certified_robot_operators")),
                "pack_staff": _int(row.get("pack_staff")),
            }
    return None


def _worker_assignment(
    warehouse_id: str, stage: str, used: set[str], labor: dict[str, int]
) -> tuple[str | None, str | None, list[dict[str, str]], str]:
    """Reserve one shared worker and any required certified/sub-pool slot."""

    if stage in {"pick", "transfer"}:
        # A robot task still consumes a certified operator in this POC model.
        # The operator pool is a subset of actual_workers by source definition.
        limit = min(labor["actual_workers"], labor["certified_robot_operators"])
        for slot in range(1, limit + 1):
            worker = f"WORKER-{warehouse_id}-{slot}"
            operator = f"ROBOT-OP-{warehouse_id}-{slot}"
            if worker not in used and operator not in used:
                return (
                    worker,
                    operator,
                    [
                        {"resource_id": worker, "resource_type": "worker"},
                        {"resource_id": operator, "resource_type": "certified_operator"},
                    ],
                    "Shared actual-worker and certified-operator slots reserved",
                )
        return (
            None,
            None,
            [],
            "Shared actual_workers/certified_robot_operators pool is fully claimed",
        )

    if stage == "pack":
        # pack_staff is a supplied subset pool and is also bounded by actual workers.
        limit = min(labor["actual_workers"], labor["pack_staff"])
        for slot in range(1, limit + 1):
            worker = f"WORKER-{warehouse_id}-{slot}"
            pack_staff = f"PACK-STAFF-{warehouse_id}-{slot}"
            if worker not in used and pack_staff not in used:
                return (
                    worker,
                    pack_staff,
                    [
                        {"resource_id": worker, "resource_type": "worker"},
                        {"resource_id": pack_staff, "resource_type": "pack_staff"},
                    ],
                    "Shared actual-worker and supplied pack-staff slots reserved",
                )
        return None, None, [], "Shared actual_workers/pack_staff pool is fully claimed"

    for slot in range(1, labor["actual_workers"] + 1):
        worker = f"WORKER-{warehouse_id}-{slot}"
        if worker not in used:
            return worker, None, [{"resource_id": worker, "resource_type": "worker"}], (
                "Shared actual-worker slot reserved for dispatch"
            )
    return None, None, [], "Supplied actual_workers pool is fully claimed"


def _choose_resource(
    db: sqlite3.Connection,
    warehouse_id: str,
    stage: str,
    used: set[str],
    labor: dict[str, int],
    payload_kg: float,
) -> tuple[str | None, str | None, str, list[dict[str, str]], list[str]]:
    """Reserve a whole-path resource slot, preferring every safe source resource."""
    raise HTTPException(410, "Policy V1 resource planning is retired")

    if not math.isfinite(payload_kg) or payload_kg <= 0:
        return None, None, "Order payload must be a positive finite weight", [], []

    if stage in {"pick", "transfer"}:
        maintenance = maintenance_exclusions(warehouse_id)
        candidates = []
        exclusions: list[str] = []
        compatible_types = ROBOT_STAGE_TYPES[stage]
        for robot in source_rows("robots"):
            if robot.get("warehouse_id") != warehouse_id:
                continue
            safe, reasons = robot_eligibility(robot, maintenance)
            robot_id = robot.get("robot_id", "")
            if robot.get("robot_type") not in compatible_types:
                reasons = reasons + [
                    f"{stage} compatibility assumption excludes robot_type {robot.get('robot_type')}"
                ]
            capacity = _float(robot.get("payload_kg"))
            if not math.isfinite(capacity) or capacity <= 0:
                reasons = reasons + ["Payload capacity is missing or invalid"]
            elif capacity < payload_kg:
                reasons = reasons + [
                    f"Payload capacity {capacity:g}kg is below planned {payload_kg:g}kg"
                ]
            if robot_id in used:
                reasons = reasons + ["Resource is already claimed by a POC planned/running task"]
            worker, operator, auxiliary, worker_reason = _worker_assignment(
                warehouse_id, stage, used, labor
            )
            if not worker:
                reasons = reasons + [worker_reason]
            if safe and not reasons:
                candidates.append((robot, auxiliary))
            else:
                exclusions.append(f"{robot_id}: {'; '.join(reasons) or worker_reason}")
        if candidates:
            # Stable, explainable choice across all eligible resources.
            selected, auxiliary = sorted(
                candidates,
                key=lambda pair: (
                    -_int(pair[0].get("battery_soc")),
                    pair[0].get("robot_id", ""),
                ),
            )[0]
            return (
                selected["robot_id"],
                "robot",
                "Safe eligible compatible robot selected from the full site registry; "
                f"payload capacity meets planned {payload_kg:g}kg (synthetic demo SKU weights)",
                auxiliary,
                exclusions,
            )
        # Explicit human fallback, bounded by the same shared certified operator
        # and actual worker pools. A human is not an unlimited-capacity bypass.
        if payload_kg <= config_values(db)["manual_payload_limit_kg"]:
            worker, operator, auxiliary, worker_reason = _worker_assignment(
                warehouse_id, stage, used, labor
            )
            if operator:
                return (
                    operator,
                    "manual",
                    "Manual fallback: no safe compatible unclaimed robot; "
                    f"planned payload is within explicit {config_values(db)['manual_payload_limit_kg']:g}kg "
                    f"demo human-handling limit using synthetic SKU weights ({worker_reason})",
                    [{"resource_id": worker, "resource_type": "worker"}],
                    exclusions,
                )
        else:
            worker_reason = (
                f"planned payload {payload_kg:g}kg exceeds explicit manual payload limit "
                f"{config_values(db)['manual_payload_limit_kg']:g}kg"
            )
        return (
            None,
            None,
            "No safe compatible unclaimed robot or feasible bounded manual fallback; "
            + worker_reason,
            [],
            exclusions,
        )

    if stage == "pack":
        worker, pack_staff, auxiliary, worker_reason = _worker_assignment(
            warehouse_id, stage, used, labor
        )
        if not worker:
            return None, None, worker_reason, [], []
        assets = [
            row
            for row in source_rows("control_assets")
            if row.get("warehouse_id") == warehouse_id
            and row.get("asset_type") == "PACK_STATION"
            and row.get("state") == "AVAILABLE"
            and row.get("maintenance_state") == "CLEAR"
            and row.get("asset_id") not in used
        ]
        if assets:
            selected = sorted(assets, key=lambda row: row.get("asset_id", ""))[0]
            return (
                selected["asset_id"],
                "pack_station",
                "Available clear PACK_STATION selected and pack staff reserved from "
                "the full site asset/staff registries",
                auxiliary,
                [],
            )
        # Explicit human fallback only after the pack staff slot is reserved.
        return (
            pack_staff,
            "manual_pack",
            "Manual pack fallback: no available clear pack station; "
            "bounded by supplied pack_staff and shared actual_workers",
            [{"resource_id": worker, "resource_type": "worker"}],
            [],
        )

    # Dispatch has an explicit staging reservation to prevent blocked downstream work.
    capacity = config_values(db)["staging_capacity"]
    used_staging = {
        row["resource_id"]
        for row in db.execute(
            """
            SELECT tasks.resource_id FROM tasks JOIN orders ON orders.id=tasks.order_id
            WHERE orders.warehouse_id=? AND tasks.stage='dispatch'
              AND tasks.status IN ('pending','queued','running')
            """,
            (warehouse_id,),
        )
        if row["resource_id"]
    }
    for slot in range(1, capacity + 1):
        resource = f"STAGING-{warehouse_id}-{slot}"
        if resource not in used and resource not in used_staging:
            worker, _, auxiliary, worker_reason = _worker_assignment(
                warehouse_id, stage, used, labor
            )
            if not worker:
                return None, None, worker_reason, [], []
            return (
                resource,
                "staging",
                "Staging slot reserved ahead of queueing; " + worker_reason,
                auxiliary,
                [],
            )
    return None, None, f"Configured staging capacity ({capacity}) is fully reserved", [], []


def _plan_resources(
    db: sqlite3.Connection, warehouse_id: str, ship_by: datetime, payload_kg: float
) -> tuple[dict[str, Any] | None, list[str]]:
    raise HTTPException(410, "Policy V1 resource planning is retired")
    config = config_values(db)
    labor = _labor(warehouse_id, config["shift"])
    if not labor:
        return None, [
            f"No supplied labor_capacity row for warehouse {warehouse_id} and shift {config['shift']}"
        ]
    now = utc_now()
    task_seconds = fulfillment_v2.task_duration_seconds(db)
    expected = now + timedelta(seconds=task_seconds * len(STAGES))
    issues: list[str] = []
    if expected > ship_by:
        issues.append(
            "Ship-by is earlier than the four-stage minimum simulator estimate "
            f"({iso(expected)}); expected finish is not a live performance guarantee"
        )
    used = _resource_usage(db, warehouse_id)
    resources: list[dict[str, Any]] = []
    exclusions: dict[str, list[str]] = {}
    for stage in STAGES:
        resource_id, resource_type, rationale, auxiliary, stage_exclusions = _choose_resource(
            db, warehouse_id, stage, used, labor, payload_kg
        )
        exclusions[stage] = stage_exclusions
        if not resource_id:
            issues.append(f"{stage}: {rationale}")
            issues.extend(f"{stage}: {reason}" for reason in stage_exclusions)
            continue
        used.add(resource_id)
        used.update(item["resource_id"] for item in auxiliary)
        resources.append(
            {
                "stage": stage,
                "resource_id": resource_id,
                "resource_type": resource_type,
                "rationale": rationale,
                "auxiliary_resources": auxiliary,
            }
        )
    if issues:
        return None, issues
    return {
        "stages": resources,
        "expected_finish_at": iso(expected),
        "expected_duration_seconds": task_seconds * len(STAGES),
        "expected_finish_label": "simulator estimate only; not live feasibility certification",
        "labor": labor,
        "payload_kg": payload_kg,
        "robot_stage_compatibility_assumption": {
            stage: sorted(types) for stage, types in ROBOT_STAGE_TYPES.items()
        },
        "robot_exclusions": exclusions,
        "resource_policy": "All source resources were considered; only unsafe/unavailable/claimed resources were excluded with rationale.",
    }, []


def _line_rows(db: sqlite3.Connection, order_id: str):
    return db.execute(
        "SELECT sku,quantity FROM order_lines WHERE order_id=? ORDER BY rowid", (order_id,)
    ).fetchall()


def order_weight_details(
    db: sqlite3.Connection, order_id: str
) -> tuple[dict[str, Any], list[str]]:
    """Resolve current per-SKU weights without changing any persisted work.

    A SKU denotes the same item across sites/bins, so validate every matching
    inventory row, including non-available stock. Never choose an arbitrary row
    or substitute the deprecated global weight when the source is ambiguous.
    """

    lines = _line_rows(db, order_id)
    rows_by_sku: dict[str, list[dict[str, Any]]] = {line["sku"]: [] for line in lines}
    for row in source_rows("inventory"):
        if row.get("sku") in rows_by_sku:
            rows_by_sku[row["sku"]].append(row)
    issues: list[str] = []
    weights: dict[str, Decimal] = {}
    for sku, rows in rows_by_sku.items():
        if not rows:
            issues.append(f"{sku}: missing inventory weight_kg; supply a synthetic demo per-unit weight before replanning")
            continue
        valid: set[Decimal] = set()
        invalid_locations: list[str] = []
        for row in rows:
            raw = row.get("weight_kg")
            try:
                weight = Decimal(str(raw).strip())
                usable = weight.is_finite() and weight > 0 and math.isfinite(float(weight)) and float(weight) > 0
            except (InvalidOperation, ValueError, TypeError, OverflowError):
                usable = False
            if not usable:
                invalid_locations.append(f"{row.get('warehouse_id', '?')}/{row.get('location', '?')}")
            else:
                valid.add(weight)
        if invalid_locations:
            issues.append(
                f"{sku}: missing or invalid weight_kg at {', '.join(invalid_locations)}; "
                "every inventory row needs a positive finite synthetic demo per-unit weight (no default fallback)"
            )
        if len(valid) > 1:
            issues.append(
                f"{sku}: inconsistent weight_kg values ({', '.join(str(w) for w in sorted(valid))} kg); "
                "make the synthetic demo per-unit weight consistent across all inventory rows before replanning"
            )
        if not invalid_locations and len(valid) == 1:
            weights[sku] = next(iter(valid))
    if issues:
        return {}, issues
    total = Decimal(0)
    weight_lines: list[dict[str, Any]] = []
    for line in lines:
        line_weight = weights[line["sku"]] * line["quantity"]
        total += line_weight
        if not math.isfinite(float(line_weight)) or not math.isfinite(float(total)):
            return {}, [f"{line['sku']}: quantity × weight_kg exceeds the supported finite order payload; reduce quantity or correct the synthetic weight"]
        weight_lines.append({
            "sku": line["sku"],
            "quantity": line["quantity"],
            "unit_weight_kg": float(weights[line["sku"]]),
            "line_weight_kg": float(line_weight),
        })
    if total <= 0:
        return {}, ["Order payload must contain positive quantities and valid SKU weights"]
    return {
        "payload_kg": float(total),
        "total_expected_weight_kg": float(total),
        "weight_source": "inventory.weight_kg",
        "weight_label": "Synthetic demo SKU weights; not measured physical weights",
        "weight_lines": weight_lines,
    }, []


def _order_json(db: sqlite3.Connection, order_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Unknown fulfillment order: {order_id}")
    result = {
        "id": row["id"],
        "warehouse_id": row["warehouse_id"],
        "priority": row["priority"],
        "ship_by": row["ship_by"],
        "status": row["status"],
        "created_at": row["created_at"],
        "lines": [
            {"sku": item["sku"], "quantity": item["quantity"]} for item in _line_rows(db, order_id)
        ],
        "plan": json.loads(row["plan_json"]),
        "issues": json.loads(row["issues_json"]),
        "source_order_id": row["source_order_id"],
        "order_service": row["order_service"],
        "order_source": row["order_source"],
    }
    if db.in_transaction:
        order_progress.sync(db, utc_now())
    return order_progress.enrich_order(db, fulfillment_v2.enrich_order(db, result, utc_now()))


def _task_json(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "order_id": row["order_id"],
        "stage": row["stage"],
        "status": row["status"],
        "resource_id": row["resource_id"],
        "resource_type": row["resource_type"],
        "started_at": row["started_at"],
        "due_at": row["due_at"],
        "completed_at": row["completed_at"],
    }
    result["auxiliary_resources"] = [
        {"resource_id": item["resource_id"], "resource_type": item["resource_type"]}
        for item in db.execute(
            "SELECT resource_id,resource_type FROM task_resources WHERE task_id=?",
            (row["id"],),
        )
    ]
    keys = set(row.keys())
    if "sub_order_id" in keys and row["sub_order_id"]:
        result.update(
            {
                "sub_order_id": row["sub_order_id"],
                "allocation_id": row["allocation_id"],
                "duration_seconds": row["duration_seconds"],
                "payload_kg": row["payload_kg"],
                "wait_reason": row["wait_reason"],
            }
        )
    return result


def _append_event(db: sqlite3.Connection, order_id: str, message: str, at: datetime | None = None):
    db.execute(
        "INSERT INTO events(order_id,at,message) VALUES (?,?,?)",
        (order_id, iso(at or utc_now()), message),
    )


def _reserve_and_plan(
    db: sqlite3.Connection, order_id: str, warehouse_id: str, ship_by: datetime
) -> tuple[str, dict[str, Any], list[str]]:
    """Plan and reserve atomically; no reservation is left on any failure."""
    raise HTTPException(410, "Policy V1 reservation planning is retired")

    line_rows = _line_rows(db, order_id)
    # Compute the complete order payload before selecting any robot or human
    # resource; no resource may be selected against an unknown/partial weight.
    weight_details, weight_issues = order_weight_details(db, order_id)
    if weight_issues:
        return "held", {}, weight_issues
    plan, plan_issues = _plan_resources(db, warehouse_id, ship_by, weight_details["payload_kg"])
    shortfalls: list[str] = []
    for line in line_rows:
        stock = available_to_promise(db, warehouse_id, line["sku"])
        if stock["available_to_promise"] < line["quantity"]:
            shortfalls.append(
                f"{line['sku']}: requested {line['quantity']}, available_to_promise "
                f"{stock['available_to_promise']} (WMS authority after source reserved_qty and POC commitments)"
            )
    issues = shortfalls + plan_issues
    if issues:
        return "held", {}, issues
    plan.update(weight_details)
    now = utc_now()
    for line in line_rows:
        reservation_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO reservations(id,order_id,warehouse_id,sku,quantity,consumed_qty,status,created_at)
            VALUES (?,?,?,?,?,0,'active',?)
            """,
            (reservation_id, order_id, warehouse_id, line["sku"], line["quantity"], iso(now)),
        )
    for item in plan["stages"]:
        task_id = f"TS-{uuid.uuid4()}"
        db.execute(
            """
            INSERT INTO tasks(id,order_id,stage,status,resource_id,resource_type)
            VALUES (?,?,?,'pending',?,?)
            """,
            (
                task_id,
                order_id,
                item["stage"],
                item["resource_id"],
                item["resource_type"],
            ),
        )
        db.executemany(
            "INSERT INTO task_resources(task_id,resource_id,resource_type) VALUES (?,?,?)",
            [
                (task_id, resource["resource_id"], resource["resource_type"])
                for resource in item.get("auxiliary_resources", [])
            ],
        )
    return "planned", plan, []


def _validate_order_input(payload: "OrderInput") -> tuple[datetime, list[dict[str, Any]]]:
    try:
        ship_by = parse_utc(payload.ship_by)
    except ValueError as exc:
        raise HTTPException(422, f"ship_by {exc}") from exc
    if ship_by <= utc_now():
        raise HTTPException(422, "ship_by must be a future UTC ISO-8601 timestamp")
    if len(payload.lines) == 0:
        raise HTTPException(422, "lines must contain at least one SKU quantity")
    warehouses = {row.get("warehouse_id") for row in source_rows("warehouses")}
    if payload.warehouse_id not in warehouses:
        raise HTTPException(422, f"Unknown warehouse_id {payload.warehouse_id}")
    known_skus = {row.get("sku") for row in source_rows("skus")}
    seen: set[str] = set()
    lines = []
    for line in payload.lines:
        if line.sku in seen:
            raise HTTPException(422, f"Duplicate SKU {line.sku}; combine quantities before submitting")
        if line.sku not in known_skus:
            raise HTTPException(422, f"Unknown SKU {line.sku}")
        seen.add(line.sku)
        lines.append({"sku": line.sku, "quantity": line.quantity})
    return ship_by, lines


def _order_request_fingerprint(payload: "OrderInput") -> str:
    """Canonical immutable create input, independent of later order edits."""

    try:
        ship_by = iso(parse_utc(payload.ship_by))
    except ValueError as exc:
        raise HTTPException(422, f"ship_by {exc}") from exc
    canonical = {
        "warehouse_id": payload.warehouse_id,
        "priority": payload.priority,
        "ship_by": ship_by,
        "lines": sorted(
            (
                {"sku": line.sku, "quantity": line.quantity}
                for line in payload.lines
            ),
            key=lambda line: line["sku"],
        ),
        "source_order_id": payload.source_order_id,
        "order_service": payload.order_service,
        "order_source": payload.order_source,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def create_order(payload: "OrderInput") -> dict[str, Any]:
    with db_transaction() as db:
        request_digest = hashlib.sha256(
            str(payload.request_id).encode("utf-8")
        ).hexdigest()
        if db.execute(
            "SELECT 1 FROM retired_order_requests WHERE request_digest=?",
            (request_digest,),
        ).fetchone():
            raise HTTPException(
                409,
                "request_id belongs to an order retired by the operational reset",
            )
        return fulfillment_v2.create_order(
            db,
            payload,
            parse_utc=parse_utc,
            now=utc_now(),
            known_skus={row.get("sku") for row in source_rows("skus")},
            known_warehouses={
                row.get("warehouse_id") for row in source_rows("warehouses")
            },
            order_json=_order_json,
            append_event=_append_event,
        )


def command_order(order_id: str, command: Literal["start", "retry", "cancel"]) -> dict[str, Any]:
    with db_transaction() as db:
        row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Unknown fulfillment order: {order_id}")
        if command == "cancel":
            fulfillment_v2.cancel(db, order_id, utc_now(), _append_event)
        elif command == "retry":
            fulfillment_v2.trigger_planner(
                db, order_id, utc_now(), source_rows, _append_event
            )
        # V2 is released automatically; start is an idempotent compatibility no-op.
        return _order_json(db, order_id)


def _complete_task(db: sqlite3.Connection, row: sqlite3.Row, now: datetime) -> None:
    """Idempotent dummy completion; stock effect is guarded by task_id."""
    raise HTTPException(410, "Policy V1 task completion is retired")

    updated = db.execute(
        """
        UPDATE tasks SET status='completed',completed_at=?
        WHERE id=? AND status='running' AND due_at<=?
        """,
        (iso(now), row["id"], iso(now)),
    ).rowcount
    if not updated:
        return
    if row["stage"] == "pick":
        if not db.execute(
            "SELECT 1 FROM stock_effects WHERE task_id=?", (row["id"],)
        ).fetchone():
            for reservation in db.execute(
                "SELECT id,quantity,consumed_qty FROM reservations WHERE order_id=? AND status='active'",
                (row["order_id"],),
            ):
                remaining = reservation["quantity"] - reservation["consumed_qty"]
                if remaining > 0:
                    db.execute(
                        "UPDATE reservations SET consumed_qty=consumed_qty+?,status='consumed' WHERE id=?",
                        (remaining, reservation["id"]),
                    )
            db.execute(
                "INSERT INTO stock_effects(task_id,applied_at) VALUES (?,?)",
                (row["id"], iso(now)),
            )
    next_task = db.execute(
        """
        SELECT id FROM tasks WHERE order_id=? AND status='pending'
        ORDER BY CASE stage WHEN 'pick' THEN 1 WHEN 'transfer' THEN 2 WHEN 'pack' THEN 3 WHEN 'dispatch' THEN 4 END
        LIMIT 1
        """,
        (row["order_id"],),
    ).fetchone()
    if next_task:
        db.execute("UPDATE tasks SET status='queued' WHERE id=?", (next_task["id"],))
    else:
        db.execute("UPDATE orders SET status='completed' WHERE id=?", (row["order_id"],))
    _append_event(db, row["order_id"], f"Simulated {row['stage']} task completed", now)


def run_executor_once(now: datetime | None = None) -> int:
    """Run one restart-safe executor tick; exposed as the fake-clock test seam."""

    now = (now or utc_now()).astimezone(timezone.utc)
    completed = 0
    with db_transaction(now=now) as db:
        completed += fulfillment_v2.executor_once(db, now, source_rows, _append_event)
    return completed


def _executor_loop() -> None:
    while not _executor_stop.wait(1.0):
        try:
            run_executor_once()
        except Exception:
            # A later tick retries persisted work. No task is marked complete
            # outside a transaction, and the exception remains observable.
            logger.exception("fulfillment simulator tick failed; persisted work will be retried")
            continue


def start_executor() -> None:
    global _executor_thread
    _init_db()
    if _executor_thread and _executor_thread.is_alive():
        return
    _executor_stop.clear()
    _executor_thread = threading.Thread(
        target=_executor_loop, name="fulfillment-simulator", daemon=True
    )
    _executor_thread.start()


def stop_executor() -> None:
    global _executor_thread
    _executor_stop.set()
    if _executor_thread and _executor_thread.is_alive():
        _executor_thread.join(timeout=2)
    _executor_thread = None


class OrderLineInput(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    quantity: conint(gt=0)  # type: ignore[valid-type]


class OrderInput(BaseModel):
    warehouse_id: str | None = Field(None, min_length=1, max_length=64)
    priority: Literal["standard", "high", "urgent"]
    ship_by: str | None = Field(None, min_length=10, max_length=80)
    lines: list[OrderLineInput] = Field(..., min_items=1)
    request_id: str = Field(..., min_length=1, max_length=100)
    source_order_id: str | None = Field(None, min_length=1, max_length=100)
    order_service: str | None = Field(None, min_length=1, max_length=64)
    order_source: str | None = Field(None, min_length=1, max_length=64)
    order_created_at: str | None = Field(None, min_length=10, max_length=80)

    @validator("request_id")
    def valid_request_id(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("request_id must be a UUID") from exc
        return value


class ConfigInput(BaseModel):
    min_stock_threshold: int | None = Field(None, ge=0, le=1_000_000)
    unit_weight_kg: float | None = Field(
        None, gt=0, le=100_000,
        description="Deprecated compatibility setting; new plans and replans require inventory.weight_kg.",
    )
    staging_capacity: int | None = Field(None, ge=1, le=100_000)
    shift: str | None = Field(None, min_length=1, max_length=32)
    manual_payload_limit_kg: float | None = Field(None, gt=0, le=100_000)
    task_duration_seconds: conint(strict=True, ge=1, le=86_400) | None = None  # type: ignore[valid-type]


class ScenarioPatch(BaseModel):
    values: dict[str, Any]
    revision: conint(strict=True, ge=0)  # type: ignore[valid-type]


router = APIRouter(prefix="/api/fulfillment", tags=["fulfillment-poc"])


@router.get("/catalog")
def catalog():
    counts = {name: len(source_rows(name)) for name in DATASETS}
    counts.update(
        {
            "inventory_rows": counts["inventory"],
            "telemetry_rows": counts["telemetry"],
            "vision_observations": counts["vision_observations"],
            "safety_events": counts["safety_events"],
            "maintenance_records": counts["maintenance"],
            "events": counts["events"],
        }
    )
    datasets = []
    for name, count in ((name, counts[name]) for name in DATASETS):
        fields = source_fields(name)
        datasets.append(
            {
                "name": name,
                "count": count,
                "fields": fields,
                "planning_impact": _planning_impact(name),
                "source_field_count": len(fields),
                "api_field_count": len(fields),
                "missing_columns": [],
            }
        )
    with _read_db() as db:
        details = _scenario_details(db)
        task_seconds = fulfillment_v2.task_duration_seconds(db)
    scenario = {
        "revision": details["revision"],
        "modified_count": details["modified_count"],
    }
    return {
        "warehouses": list(source_rows("warehouses")),
        "skus": list(source_rows("skus")),
        "datasets": datasets,
        "counts": counts,
        "scenario": scenario,
        "scenario_revision": details["revision"],
        "scenario_modified_count": details["modified_count"],
        "source_audit": [
            {
                "dataset": item["name"],
                "source_row_count": item["count"],
                "source_fields": item["fields"],
                "api_fields": item["fields"],
                "missing_columns": item["missing_columns"],
            }
            for item in datasets
        ],
        "assumptions": ASSUMPTIONS,
        "fulfillment_policies": {
            "default": 2,
            "v2_services": dict(fulfillment_v2.SERVICES),
            "v2_stages": list(fulfillment_v2.STAGES),
            "stage_duration_seconds": task_seconds,
        },
    }


def _resource_rows(
    db: sqlite3.Connection, dataset: str, warehouse_id: str | None = None
) -> list[dict[str, Any]]:
    if dataset == "inventory":
        return list(inventory_rows_with_metrics(db, warehouse_id))
    rows: list[dict[str, Any]] = []
    for source_row, row_id, modified in _source_rows_with_meta(dataset):
        if warehouse_id and source_row.get("warehouse_id") not in {warehouse_id, None}:
            continue
        row = dict(source_row)
        row["_scenario_row_id"] = row_id
        row["_scenario_modified"] = modified
        if dataset == "robots":
            # Keep every raw robot row while making safety decisions explicit
            # for the browser. These are snapshot annotations, not a live
            # certification or busy claim.
            site = row.get("warehouse_id", "")
            eligible, reasons = robot_eligibility(
                row, maintenance_exclusions(site)
            )
            row["poc_eligible"] = eligible
            stage_type_exclusions = {
                stage: (
                    []
                    if row.get("robot_type") in compatible
                    else [
                        f"robot_type {row.get('robot_type')} is outside the "
                        f"POC {stage} compatibility assumption"
                    ]
                )
                for stage, compatible in ROBOT_STAGE_TYPES.items()
            }
            row["poc_stage_type_exclusions"] = stage_type_exclusions
            row["poc_exclusion_reasons"] = reasons + [
                reason
                for stage_reasons in stage_type_exclusions.values()
                for reason in stage_reasons
            ]
        rows.append(row)
    return rows


@router.get("/resources/{dataset}")
def resources(dataset: str, warehouse_id: str | None = Query(None, max_length=64)):
    if dataset not in DATASETS:
        raise HTTPException(404, f"Unknown dataset {dataset}; see /api/fulfillment/catalog")
    # Direct Python callers (including focused regression tests) do not pass
    # FastAPI's Query default through dependency injection.
    if not isinstance(warehouse_id, str):
        warehouse_id = None
    with _read_db() as db:
        rows = _resource_rows(db, dataset, warehouse_id)
        result = _resource_contract(db, dataset)
    result.update({"rows": rows, "total": len(rows)})
    return result


@router.patch("/resources/{dataset}/{row_id}")
def patch_resource(dataset: str, row_id: int, payload: ScenarioPatch):
    return patch_scenario_resource(dataset, row_id, payload.values, payload.revision)


@router.delete("/resources/{dataset}/{row_id}")
def delete_resource(
    dataset: str, row_id: int, revision: int = Query(..., ge=0)
):
    return reset_scenario_resource(dataset, row_id, revision)


@router.delete("/scenario")
def delete_scenario(revision: int = Query(..., ge=0)):
    return reset_scenario(revision)


def stock_alerts(
    db: sqlite3.Connection, config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Return the current state endpoint's exact warehouse/SKU stock alerts."""

    # Forecast demand replaces the retired fixed min_stock_threshold for alerts.
    alerts = []
    run, forecasts = demand_forecast.current_thresholds(db)
    if run is None:
        logger.error("Low-stock detection unavailable: no valid demand forecast run")
        return alerts
    v2_free: dict[tuple[str, str], int] = {}
    for item in inventory_rows(db):
        key = (item["warehouse_id"], item["sku"])
        v2_free[key] = v2_free.get(key, 0) + max(
            0, min(int(item["wms_qty"]), int(item["erp_qty"]), int(item["vision_qty"]))
        )
    for (warehouse_id, sku), available in v2_free.items():
        forecast = forecasts.get((warehouse_id, sku))
        if forecast is None:
            continue
        threshold = int(forecast["forecast_7d"])
        if available >= threshold:
            continue
        alerts.append({
            "warehouse_id": warehouse_id,
            "sku": sku,
            "available": available,
            "threshold": threshold,
            "forecast_7d": threshold,
            "forecast_30d": int(forecast["forecast_30d"]),
            "forecast_date": run["forecast_date"],
            "history_days": int(forecast["history_days"]),
            "history_status": forecast["history_status"],
            "inventory_policy": "free_source_min_sum",
            "forecast_method": run["method"],
        })
    return alerts


def _forecast_run_metadata(run):
    expected = demand_forecast.expected_forecast_date(datetime.now(timezone.utc))
    return {
        "id": run["id"],
        "forecast_date": run["forecast_date"],
        "generated_at": run["generated_at"],
        "window_start": run["window_start"],
        "window_end": run["window_end"],
        "method": run["method"],
        "lookback_days": demand_forecast.run_lookback_days(run),
        "coverage_verified": False,
        "coverage_note": "Calendar-day denominator within the explicit lookback; absence of orders is not proof of source coverage.",
        "scheduled_time": demand_forecast.SCHEDULED_TIME,
        "timezone": demand_forecast.TIMEZONE,
        "excluded_unassigned_units": int(run["excluded_unassigned_units"]),
        "stale": run["forecast_date"] < expected.isoformat(),
    }


@router.get("/demand-forecasts/detail")
def demand_forecast_detail(
    warehouse_id: str = Query(..., min_length=1, max_length=64),
    sku: str = Query(..., min_length=1, max_length=100),
    run_id: str | None = Query(None, min_length=1, max_length=100),
):
    with _read_db() as db:
        detail = demand_forecast.saved_detail(db, warehouse_id, sku, run_id)
        if detail is None:
            raise HTTPException(404, "No saved forecast matches this warehouse, SKU and run")
        available = sum(
            max(0, min(int(row["wms_qty"]), int(row["erp_qty"]), int(row["vision_qty"])))
            for row in inventory_rows(db, warehouse_id, sku)
        )
        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item = detail["item"]
        item.pop("run_id")
        item.update(available_qty=available, low_stock=available < item["forecast_7d"])
        detail.update(
            run=_forecast_run_metadata(detail["run"]),
            stock_checked_at=checked_at,
            minimum_replenishment=max(0, item["forecast_7d"] - available),
        )
        return detail


@router.get("/demand-forecasts")
def demand_forecasts(
    warehouse_id: str | None = Query(None, max_length=64),
    search: str | None = Query(None, max_length=100),
):
    with _read_db() as db:
        run, forecasts = demand_forecast.current_thresholds(db)
        if run is None:
            raise HTTPException(503, "No valid demand forecast run is available")
        availability: dict[tuple[str, str], int] = {}
        for row in inventory_rows(db):
            key = (str(row["warehouse_id"]), str(row["sku"]))
            availability[key] = availability.get(key, 0) + max(
                0, min(int(row["wms_qty"]), int(row["erp_qty"]), int(row["vision_qty"]))
            )
        needle = (search or "").strip().casefold()
        items = []
        for key in sorted(availability):
            site, sku = key
            if warehouse_id and site != warehouse_id:
                continue
            if needle and needle not in site.casefold() and needle not in sku.casefold():
                continue
            forecast = forecasts.get(key)
            if forecast is None:
                continue
            available = availability[key]
            threshold = int(forecast["forecast_7d"])
            items.append({
                "warehouse_id": site,
                "sku": sku,
                "available_qty": available,
                "forecast_7d": threshold,
                "forecast_30d": int(forecast["forecast_30d"]),
                "daily_demand": float(forecast["daily_demand"]),
                "history_units": int(forecast["history_units"]),
                "history_days": int(forecast["history_days"]),
                "history_status": forecast["history_status"],
                "low_stock": available < threshold,
            })
        return {
            "items": items,
            "run": _forecast_run_metadata(run),
        }


def _order_page(db, limit=25, offset=0, search="", status=None, warehouse=None):
    """Page first, then batch-load only lightweight line and status summaries."""
    clauses, params = [], []
    if search:
        pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append("(o.id LIKE ? ESCAPE '\\' OR o.source_order_id LIKE ? ESCAPE '\\' OR EXISTS "
                       "(SELECT 1 FROM order_lines l WHERE l.order_id=o.id AND l.sku LIKE ? ESCAPE '\\'))")
        params.extend([pattern] * 3)
    if status:
        clauses.append("o.status=?")
        params.append(status)
    if warehouse:
        clauses.append("(o.warehouse_id=? OR EXISTS (SELECT 1 FROM sub_orders s WHERE s.order_id=o.id AND s.warehouse_id=?))")
        params.extend([warehouse, warehouse])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = db.execute("SELECT count(*) FROM orders o" + where, params).fetchone()[0]
    rows = list(db.execute(
        "SELECT o.*,p.fulfillment_status FROM orders o LEFT JOIN order_fulfillment_progress p "
        "ON p.entity_type='order' AND p.entity_id=o.id" + where +
        " ORDER BY o.created_at DESC,o.id DESC LIMIT ? OFFSET ?", [*params, limit, offset]
    ))
    items = []
    if rows:
        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" for _ in ids)
        lines, subs, locations = {}, {}, {}
        for row in db.execute(
            f"SELECT DISTINCT s.order_id,i.warehouse_id,i.zone FROM sub_orders s "
            f"JOIN sub_order_allocations a ON a.sub_order_id=s.id "
            f"JOIN inventory_snapshot i ON i.id=a.inventory_row_id "
            f"WHERE s.order_id IN ({placeholders})", ids
        ):
            locations.setdefault(row["order_id"], []).append(row)
        for row in db.execute(f"SELECT order_id,sku,quantity FROM order_lines WHERE order_id IN ({placeholders}) ORDER BY rowid", ids):
            lines.setdefault(row["order_id"], []).append({"sku": row["sku"], "quantity": row["quantity"]})
        for row in db.execute(
            f"SELECT s.*,p.fulfillment_status FROM sub_orders s LEFT JOIN order_fulfillment_progress p "
            f"ON p.entity_type='sub_order' AND p.entity_id=s.id WHERE s.order_id IN ({placeholders}) ORDER BY s.rowid", ids
        ):
            sub = dict(row)
            sub["fulfillment_status"] = "Rejected" if sub["status"] == "rejected" else sub["fulfillment_status"] or "Order Accepted"
            subs.setdefault(sub["order_id"], []).append(sub)
        for row in rows:
            item = {key: row[key] for key in (
                "id", "warehouse_id", "priority", "ship_by", "status", "created_at",
                "source_order_id", "order_service", "order_source", "policy_version",
                "cutoff_at", "order_created_at",
            )}
            item["lines"] = lines.get(row["id"], [])
            item["sub_orders"] = subs.get(row["id"], [])
            item["issues"] = json.loads(row["issues_json"] or "[]")
            item["hold_reason"] = "; ".join(dict.fromkeys(
                sub["hold_reason"] for sub in item["sub_orders"] if sub.get("hold_reason")
            )) or None
            item["fulfillment_status"] = "Rejected" if row["status"] == "rejected" else row["fulfillment_status"] or "Order Accepted"
            item["warehouses"] = sorted(
                {loc["warehouse_id"] for loc in locations.get(row["id"], []) if loc["warehouse_id"]}
                | {sub["warehouse_id"] for sub in item["sub_orders"] if sub.get("warehouse_id")}
                or ({row["warehouse_id"]} if row["warehouse_id"] else set())
            )
            item["zones"] = sorted({loc["zone"] for loc in locations.get(row["id"], []) if loc["zone"]})
            item["overdue"] = bool(row["cutoff_at"] and row["cutoff_at"] < iso(utc_now()) and row["status"] not in {"completed", "cancelled", "rejected"})
            items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/orders")
def list_orders(
    search: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[str | None, Query(max_length=64)] = None,
    warehouse: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with _read_db() as db:
        return _order_page(db, limit, offset, search, status, warehouse)


@router.get("/state")
def state(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[str | None, Query(max_length=64)] = None,
):
    with _read_db() as db:
        page = _order_page(db, limit, offset, search, status)
        orders = page["items"]
        tasks = [
            _task_json(db, row)
            for row in db.execute(
                "SELECT * FROM tasks WHERE status NOT IN ('completed','cancelled') ORDER BY rowid DESC LIMIT 200"
            )
        ]
        config = config_values(db)
        alerts = stock_alerts(db, config)
        summary = {
            "completed": 0,
            "on_hold": 0,
            "cancelled": 0,
            "active": 0,
            "partially_fulfilled": 0,
            "recovery_required": 0,
            "rejected": 0,
        }
        for order in db.execute("SELECT status,count(*) AS n FROM orders GROUP BY status"):
            status = order["status"]
            if status in {"held", "planned"}:
                summary["on_hold"] += order["n"]
            elif status in summary:
                summary[status] += order["n"]
            elif status in {"queued", "running"}:
                summary["active"] += order["n"]
        return {
            "orders": orders,
            "tasks": tasks,
            "alerts": alerts,
            "config": config,
            "scenario_revision": _scenario_revision(db),
            "scenario_modified_count": _scenario_modified_count(db),
            "server_time": iso(utc_now()),
            "assumptions": ASSUMPTIONS,
            "summary": summary,
            "total_orders": db.execute("SELECT count(*) FROM orders").fetchone()[0],
            "filtered_total": page["total"],
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(orders) < page["total"],
            "total_tasks": db.execute("SELECT count(*) FROM tasks").fetchone()[0],
            "tasks_limit": 200,
        }


@router.post("/orders")
def post_order(payload: OrderInput):
    return create_order(payload)


@router.get("/orders.csv")
def orders_csv():
    from fastapi.responses import FileResponse
    with db_transaction() as db:
        order_progress.sync(db, utc_now())
    path = DB_PATH.parent / "exports" / "orders.csv"
    # Explicit downloads surface export errors rather than serving stale data.
    with _read_db() as db:
        order_progress.export_orders(db, path)
    return FileResponse(path, media_type="text/csv", filename="orders.csv")


@router.get("/orders/{order_id}")
def get_order(order_id: str):
    with _read_db() as db:
        result = _order_json(db, order_id)
        result["events"] = [
            {"at": row["at"], "message": row["message"]}
            for row in db.execute(
                "SELECT at,message FROM events WHERE order_id=? ORDER BY id", (order_id,)
            )
        ]
        result["tasks"] = [
            _task_json(db, row)
            for row in db.execute(
                "SELECT * FROM tasks WHERE order_id=? ORDER BY rowid", (order_id,)
            )
        ]
        return result


@router.post("/orders/{order_id}/{command}")
def order_command(order_id: str, command: Literal["start", "retry", "cancel"]):
    return command_order(order_id, command)


@router.put("/config")
def put_config(
    payload: ConfigInput,
    x_demo_persona: str | None = Header(None, alias="X-Demo-Persona"),
):
    # Reuse the demo-persona contract; this is role simulation, not authentication.
    from persona_api import _role

    if _role(x_demo_persona) != "admin":
        raise HTTPException(403, "System configuration is admin-only")
    values = payload.dict(exclude_none=True)
    if not values:
        raise HTTPException(422, "At least one config field is required")
    if "shift" in values and values["shift"] not in source_shift_values():
        raise HTTPException(
            422,
            f"shift must match a supplied labor_capacity shift: {sorted(source_shift_values())}",
        )
    with db_transaction() as db:
        for key, value in values.items():
            db.execute("UPDATE config SET value=? WHERE key=?", (str(value), key))
        return config_values(db)


@router.get("/healthz")
def fulfillment_health():
    return {"status": "ok", "simulation": True, "database": str(DB_PATH)}


from lifecycle_api import router as lifecycle_router
router.include_router(lifecycle_router)

_init_db()
