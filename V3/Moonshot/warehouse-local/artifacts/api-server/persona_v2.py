"""Authoritative v2 correction and workspace helpers.

This module has no routes.  It keeps the intervention state machine in
``persona_api`` while isolating fulfillment-v2 feature detection and effective
modeled fleet-source overrides.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from fastapi import HTTPException

import fulfillment_api as fulfillment
import fleet_readiness


INVENTORY_SOURCES = {"wms", "erp", "vision"}
ROBOT_FIELDS = {
    "health_status",
    "safety_cert_status",
    "calibration_status",
    "connectivity",
    "battery_soc",
    "payload_kg",
}
MAINTENANCE_FIELDS = {"cmms_status", "fleet_availability"}
ASSET_FIELDS = {"state", "maintenance_state"}
FIELD_VALUES = {
    "health_status": {"HEALTHY", "DEGRADED", "FAILED", "UNKNOWN"},
    "safety_cert_status": {"VALID", "EXPIRED", "INVALID", "UNKNOWN"},
    "calibration_status": {"VALID", "INVALID", "EXPIRED", "UNKNOWN"},
    "connectivity": {"ONLINE", "INTERMITTENT", "OFFLINE", "UNKNOWN"},
    "cmms_status": {"OPEN", "IN_PROGRESS", "PLANNED", "CLOSED", "COMPLETE"},
    "fleet_availability": {"AVAILABLE", "UNAVAILABLE", "OUT_OF_SERVICE", "UNKNOWN"},
    "state": {"AVAILABLE", "UNAVAILABLE", "OFFLINE", "BLOCKED", "UNKNOWN"},
    "maintenance_state": {"CLEAR", "DUE", "BLOCKED", "UNKNOWN"},
}
FLEET_KINDS = {"fleet_readiness", "resource_failure", "control_asset_readiness"}
INVENTORY_KINDS = {"inventory_mismatch", "replenishment_alert"}


def ensure_schema(db: sqlite3.Connection) -> None:
    # Do not use executescript: persona actions call this while inside the
    # fulfillment BEGIN IMMEDIATE seam, and sqlite3.executescript implicitly
    # commits the caller's transaction.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS persona_source_corrections (
            dataset TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field TEXT NOT NULL,
            value_json TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            intervention_id TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(dataset,entity_id,field)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS persona_v2_detection_state (
            id INTEGER PRIMARY KEY CHECK(id=1),
            fingerprint TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS persona_source_correction_entity
            ON persona_source_corrections(dataset,entity_id)
        """
    )


def inventory_v2_available() -> bool:
    return all(
        hasattr(fulfillment, name)
        for name in ("ensure_inventory", "inventory_rows", "correct_inventory", "reevaluate_held")
    )


def effective_source_rows(
    db: sqlite3.Connection | None, dataset: str, rows: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], ...]:
    if dataset == "maintenance":
        # Imported rows with a missing work-order identity still need a stable,
        # explicitly repairable application identity. Source order is immutable.
        rows = tuple(
            row
            if str(row.get("work_order_id") or "").strip()
            else {
                **row,
                "work_order_id": (
                    f"MAINT-{row.get('robot_id') or 'UNKNOWN'}-ROW-{index + 1}"
                ),
            }
            for index, row in enumerate(rows)
        )
    if db is None or dataset not in {"robots", "maintenance", "control_assets"}:
        return rows
    identity = {
        "robots": "robot_id",
        "maintenance": "work_order_id",
        "control_assets": "asset_id",
    }[dataset]
    try:
        changes: dict[str, dict[str, Any]] = {}
        for item in db.execute(
            "SELECT entity_id,field,value_json FROM persona_source_corrections WHERE dataset=?",
            (dataset,),
        ):
            changes.setdefault(item["entity_id"], {})[item["field"]] = json.loads(
                item["value_json"]
            )
    except sqlite3.OperationalError:
        return rows
    return tuple({**row, **changes.get(str(row.get(identity, "")), {})} for row in rows)


def correction_capabilities(role: str) -> dict[str, Any]:
    if role == "supervisor":
        return {
            "inventory": {
                "sources": sorted(INVENTORY_SOURCES),
                "bases": ["free", "total"],
                "basis_api_translation": {"total": "total_on_hand"},
                "quantity": {"type": "integer", "minimum": 0},
                "revision_required": True,
                "proposal_evidence_required": [
                    "count_method",
                    "verified_by",
                    "units",
                ],
                "verify_evidence_required": [
                    "verified_by",
                    "current_observations",
                ],
            },
            "fleet_review": {
                "approve_evidence_required": [],
                "verify_evidence_required": [
                    "verified_by",
                    "observed_entity_id",
                    "observation_source",
                ],
            },
        }
    if role == "fleet":
        return {
            "fleet": {
                "robot_fields": sorted(ROBOT_FIELDS),
                "maintenance_fields": sorted(MAINTENANCE_FIELDS),
                "control_asset_fields": sorted(ASSET_FIELDS),
                "revision_required": True,
                "proposal_evidence_required": ["source", "verified_by"],
                "verify_evidence_required": [
                    "verified_by",
                    "observed_entity_id",
                    "observation_source",
                ],
            }
        }
    return {}


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}


def linked_held_work(
    db: sqlite3.Connection, warehouse_id: str, sku: str
) -> list[dict[str, Any]]:
    columns = _columns(db, "sub_orders")
    if not columns:
        return []
    where = ["sku=?", "status IN ('held','waiting_for_stock','on_hold')"]
    params: list[Any] = [sku]
    # A shortage can have no selected warehouse.  Such work is linked by SKU,
    # not incorrectly discarded by an equality comparison with NULL.
    if "warehouse_id" in columns:
        where.append("(warehouse_id=? OR warehouse_id IS NULL)")
        params.append(warehouse_id)
    selected = [
        name
        for name in ("id", "order_id", "sku", "warehouse_id", "status", "hold_reason", "cutoff_at")
        if name in columns
    ]
    return [
        dict(row)
        for row in db.execute(
            f"SELECT {','.join(selected)} FROM sub_orders WHERE {' AND '.join(where)} "
            + ("ORDER BY cutoff_at,id" if "cutoff_at" in columns else "ORDER BY id"),
            params,
        )
    ]


def held_work_index(db: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Load held work once for a full-catalog detection pass."""

    columns = _columns(db, "sub_orders")
    if not columns:
        return {}
    selected = [
        name
        for name in ("id", "order_id", "sku", "warehouse_id", "status", "hold_reason", "cutoff_at")
        if name in columns
    ]
    rows = db.execute(
        f"SELECT {','.join(selected)} FROM sub_orders "
        "WHERE status IN ('held','waiting_for_stock','on_hold') "
        + ("ORDER BY cutoff_at,id" if "cutoff_at" in columns else "ORDER BY id")
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(str(row["sku"]), []).append(dict(row))
    return result


def detection_fingerprint(db: sqlite3.Connection, threshold: int | None = None) -> str:
    inventory = db.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(revision),0) AS revisions,"
        "COALESCE(SUM(wms_qty+erp_qty+vision_qty+reserved_qty+picked_qty),0) AS quantities,"
        "COALESCE(MAX(updated_at),'') AS latest FROM inventory_snapshot"
    ).fetchone()
    held = [
        tuple(row)
        for row in db.execute(
            "SELECT id,COALESCE(warehouse_id,''),status,COALESCE(hold_reason,'') "
            "FROM sub_orders WHERE status IN ('held','waiting_for_stock','on_hold') "
            "ORDER BY id"
        )
    ]
    corrections = db.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(revision),0) AS revisions,"
        "COALESCE(MAX(updated_at),'') AS latest FROM persona_source_corrections"
    ).fetchone()
    import demand_forecast
    forecast_run, forecasts = demand_forecast.current_thresholds(db)
    forecast_state = {
        "method": forecast_run["method"] if forecast_run else None,
        # Refresh evidence for a new business snapshot even when predictions
        # are unchanged. Alert condition fingerprints intentionally omit this.
        "forecast_date": forecast_run["forecast_date"] if forecast_run else None,
        "values": sorted(
            (warehouse, sku, int(value["forecast_7d"]))
            for (warehouse, sku), value in forecasts.items()
        ),
    }
    return json.dumps(
        {
            "format_version": 6,
            "inventory": tuple(inventory),
            "held": held,
            "source_corrections": tuple(corrections),
            "scenario_revision": fulfillment._scenario_revision(db),
            "forecast": forecast_state,
        },
        separators=(",", ":"),
    )


def strict_robot_readiness(
    db: sqlite3.Connection,
    robot: dict[str, Any],
    maintenance_rows: tuple[dict[str, Any], ...],
) -> tuple[bool, list[str]]:
    return fleet_readiness.robot_readiness(robot, maintenance_rows)


def inventory_context(
    db: sqlite3.Connection, warehouse_id: str, sku: str, location: str | None
) -> dict[str, Any]:
    if not inventory_v2_available():
        raise HTTPException(409, "Authoritative inventory correction requires fulfillment policy v2")
    fulfillment.ensure_inventory(db)
    rows = list(fulfillment.inventory_rows(db, warehouse_id=warehouse_id, sku=sku))
    if location:
        rows = [row for row in rows if str(row.get("location")) == location]
    if not rows:
        raise HTTPException(409, "Inventory correction target no longer exists")
    if len(rows) != 1:
        raise HTTPException(422, "location or inventory_row_id is required for a source correction")
    return dict(rows[0])


def sync_inventory_mismatch_for_close(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    comment: str,
    intervention_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | list[dict[str, Any]]]:
    """Synchronize only the inventory row(s) identified by a mismatch issue."""
    if not inventory_v2_available():
        raise HTTPException(409, "Manual inventory synchronization requires fulfillment policy v2")
    fulfillment.ensure_inventory(db)
    evidence = json.loads(row["evidence_json"] or "{}")
    warehouse_id = str(evidence.get("warehouse_id") or row["warehouse_id"] or "")
    entity = str(row["entity_id"] or "")
    sku = str(evidence.get("sku") or entity.split("@", 1)[0])
    location = evidence.get("location")
    if location is None and "@" in entity:
        location = entity.split("@", 1)[1]
    inventory_row_id = evidence.get("inventory_row_id")
    candidates = [
        dict(item)
        for item in fulfillment.inventory_rows(db, warehouse_id=warehouse_id, sku=sku)
    ]
    if inventory_row_id is not None:
        candidates = [
            item
            for item in candidates
            if str(item.get("inventory_row_id")) == str(inventory_row_id)
            and (
                not location
                or str(item.get("location") or "") == str(location)
            )
        ]
    elif location:
        candidates = [
            item for item in candidates if str(item.get("location") or "") == str(location)
        ]
        if len(candidates) > 1:
            raise HTTPException(
                422, "Inventory mismatch location is ambiguous; inventory_row_id is required"
            )
    # Historical locationless SKU issues intentionally synchronize every
    # matching row independently. A high count from one location is never
    # propagated to another location.
    if not candidates:
        raise HTTPException(409, "Inventory synchronization target no longer exists")

    implementation = getattr(fulfillment, "fulfillment_v2", None)
    helper = getattr(implementation, "sync_inventory_sources_to_current_max", None)
    if helper is None:
        raise HTTPException(409, "Manual inventory synchronization is unavailable")
    at = fulfillment.utc_now()
    sync: list[dict[str, Any]] = []
    current_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        before, after = helper(
            db,
            int(candidate["inventory_row_id"]),
            f"Manual close of persona intervention {intervention_id}: {comment}",
            "persona-supervisor",
            at,
        )
        quantity_fields = ("wms_qty", "erp_qty", "vision_qty")
        sync.append(
            {
                "inventory_row_id": after["id"],
                "location": after["location"],
                "before": {field: before[field] for field in quantity_fields},
                "after": {field: after[field] for field in quantity_fields},
            }
        )
        current_rows.append(
            next(
                dict(item)
                for item in fulfillment.inventory_rows(
                    db, warehouse_id=after["warehouse_id"], sku=after["sku"]
                )
                if item["inventory_row_id"] == after["id"]
            )
        )
    return sync, current_rows[0] if len(current_rows) == 1 else current_rows


def apply_inventory(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    proposed: dict[str, Any],
    intervention_id: str,
) -> dict[str, Any]:
    current = inventory_context(
        db, row["warehouse_id"], proposed["sku"], proposed.get("location")
    )
    row_id = proposed.get("inventory_row_id") or current.get("inventory_row_id")
    if not row_id:
        raise HTTPException(409, "Authoritative inventory row has no stable identifier")
    corrected = fulfillment.correct_inventory(
        db,
        row_id,
        {f"{proposed['source']}_qty": proposed["quantity"]},
        proposed["basis"],
        proposed["revision"],
        f"Approved persona intervention {intervention_id}",
        "persona-supervisor",
    )
    return dict(corrected)


def verify_inventory_observations(
    db: sqlite3.Connection,
    current: dict[str, Any],
    evidence: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    observations = evidence.get("current_observations")
    required = {
        "revision",
        "basis",
        "wms_qty",
        "erp_qty",
        "vision_qty",
        "attestation",
    }
    if not evidence.get("verified_by") or not isinstance(observations, dict):
        raise HTTPException(
            422, "verification evidence requires verified_by and current_observations"
        )
    if set(observations) != required:
        raise HTTPException(
            422,
            "current_observations must contain exactly revision, basis, wms_qty, "
            "erp_qty, vision_qty, and attestation",
        )
    if observations["basis"] not in {"free", "total_on_hand"}:
        raise HTTPException(422, "observation basis must be free or total_on_hand")
    if observations["revision"] != current.get("revision"):
        raise HTTPException(409, "Inventory verification observations are stale")
    if not isinstance(observations["attestation"], str) or not observations[
        "attestation"
    ].strip():
        raise HTTPException(422, "current observation attestation is required")
    protected = int(current.get("reserved_qty") or 0) + int(
        current.get("picked_qty") or 0
    )
    for field in ("wms_qty", "erp_qty", "vision_qty"):
        value = observations[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HTTPException(422, f"current observation {field} must be non-negative")
        expected = int(current.get(field) or 0)
        if observations["basis"] == "total_on_hand":
            expected += protected
        if value != expected:
            raise HTTPException(
                409, f"current observation {field} does not match effective inventory"
            )
    if current.get("blocked_allocation") or current.get("opening_discrepancy"):
        if observations["basis"] != "total_on_hand":
            raise HTTPException(
                422, "opening block verification requires total_on_hand observations"
            )
        implementation = getattr(fulfillment, "fulfillment_v2", None)
        helper = getattr(implementation, "verify_opening_inventory", None)
        if helper is None:
            raise HTTPException(
                409, "Audited opening inventory verification is unavailable"
            )
        return dict(
            helper(
                db,
                int(current["inventory_row_id"]),
                reason,
                f"persona-supervisor:{evidence['verified_by']}",
                observations,
            )
        )
    return current


def source_revision(db: sqlite3.Connection, dataset: str, entity_id: str) -> int:
    ensure_schema(db)
    row = db.execute(
        "SELECT MAX(revision) AS revision FROM persona_source_corrections "
        "WHERE dataset=? AND entity_id=?",
        (dataset, entity_id),
    ).fetchone()
    return int(row["revision"] or 0)


def validate_fleet_value(db: sqlite3.Connection, entity_id: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(422, "fleet correction value must be a source-specific object")
    entity_type = value.get("entity_type")
    dataset = {
        "robot": "robots",
        "maintenance": "maintenance",
        "control_asset": "control_assets",
    }.get(entity_type)
    fields = {
        "robots": ROBOT_FIELDS,
        "maintenance": MAINTENANCE_FIELDS,
        "control_assets": ASSET_FIELDS,
    }.get(dataset or "", set())
    field = value.get("field")
    if field not in fields:
        raise HTTPException(422, "fleet correction field is not allowed for that source")
    target = str(value.get("entity_id") or entity_id)
    id_field = {
        "robots": "robot_id",
        "maintenance": "work_order_id",
        "control_assets": "asset_id",
    }[dataset]
    if not any(str(item.get(id_field, "")) == target for item in fulfillment.source_rows(dataset)):
        raise HTTPException(409, "Fleet correction target is not a known modeled source entity")
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise HTTPException(422, "fleet correction revision must be a non-negative integer")
    if revision != source_revision(db, dataset, target):
        raise HTTPException(409, "Fleet correction revision is stale")
    corrected = value.get("value")
    if field in {"battery_soc", "payload_kg"}:
        if isinstance(corrected, bool) or not isinstance(corrected, (int, float)):
            raise HTTPException(422, f"{field} must be numeric")
        if not math.isfinite(float(corrected)) or float(corrected) < 0:
            raise HTTPException(422, f"{field} must be finite and non-negative")
        if field == "battery_soc" and float(corrected) > 100:
            raise HTTPException(422, "battery_soc must be between 0 and 100")
        if field == "payload_kg" and float(corrected) == 0:
            raise HTTPException(422, "payload_kg must be greater than zero")
    elif not isinstance(corrected, str) or not corrected.strip():
        raise HTTPException(422, f"{field} must be a non-empty source value")
    elif corrected.strip().upper() not in FIELD_VALUES[field]:
        raise HTTPException(
            422,
            f"{field} must be one of {', '.join(sorted(FIELD_VALUES[field]))}",
        )
    if isinstance(corrected, str):
        corrected = corrected.strip().upper()
    return {
        "type": "fleet_source_correction",
        "dataset": dataset,
        "entity_type": entity_type,
        "entity_id": target,
        "field": field,
        "value": corrected,
        "revision": revision,
    }


def apply_fleet(
    db: sqlite3.Connection, proposed: dict[str, Any], intervention_id: str, now: str
) -> None:
    current = source_revision(db, proposed["dataset"], proposed["entity_id"])
    if current != proposed["revision"]:
        raise HTTPException(409, "Fleet correction revision is stale")
    db.execute(
        "INSERT INTO persona_source_corrections"
        "(dataset,entity_id,field,value_json,revision,intervention_id,updated_at) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(dataset,entity_id,field) DO UPDATE SET "
        "value_json=excluded.value_json,revision=excluded.revision,"
        "intervention_id=excluded.intervention_id,updated_at=excluded.updated_at",
        (
            proposed["dataset"],
            proposed["entity_id"],
            proposed["field"],
            json.dumps(proposed["value"], allow_nan=False),
            current + 1,
            intervention_id,
            now,
        ),
    )


def resource_readiness(db: sqlite3.Connection, row: sqlite3.Row) -> tuple[bool, list[str]]:
    if row["kind"] == "control_asset_readiness":
        asset = next(
            (
                item
                for item in fulfillment.source_rows("control_assets")
                if item.get("asset_id") == row["entity_id"]
            ),
            None,
        )
        if not asset:
            return False, ["unknown control asset"]
        return fleet_readiness.asset_readiness(asset)
    robot = next(
        (
            item
            for item in fulfillment.source_rows("robots")
            if item.get("robot_id") == row["entity_id"]
        ),
        None,
    )
    if not robot:
        return False, ["unknown robot"]
    return fleet_readiness.robot_readiness(
        robot, fulfillment.source_rows("maintenance")
    )