"""Persona workspaces and intervention workflows for the demo control tower.

This module is deliberately separate from the legacy review API and from the
fulfillment implementation.  It uses the fulfillment POC's SQLite transaction
seam, while source snapshots remain read-only.  The ``X-Demo-Persona`` header
is a demo role switcher, not authentication.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

import fulfillment_api as fulfillment
import fulfillment_v2
import fleet_repair
import persona_v2


router = APIRouter(prefix="/api/personas", tags=["persona-workspaces"])

PERSONAS = {"fleet", "supervisor", "admin"}
KINDS = {
    "inventory_mismatch",
    "replenishment_alert",
    "priority_override",
    "fleet_readiness",
    "control_asset_readiness",
    "task_completion_conflict",
    "resource_failure",
}
STATUSES = {"open", "investigating", "awaiting_approval", "resolved"}
OPERATIONAL_KINDS = {
    "fleet": {"fleet_readiness", "control_asset_readiness", "resource_failure"},
    "supervisor": {
        "inventory_mismatch",
        "replenishment_alert",
        "priority_override",
        "task_completion_conflict",
        "resource_failure",
    },
    "admin": set(),
}
RETIRED_FLEET_MANUAL_REPORT_KINDS = {
    "fleet_readiness",
    "control_asset_readiness",
    "resource_failure",
}
POLICY = {
    "fleet": {
        "label": "Fleet lead",
        "views": ["fleet_readiness", "control_asset_readiness", "resource_failure"],
        "actions": ["investigate", "propose", "verify", "handoff"],
    },
    "supervisor": {
        "label": "Operations supervisor",
        "views": [
            "inventory_mismatch",
            "replenishment_alert",
            "priority_override",
            "fleet_readiness",
            "control_asset_readiness",
            "task_completion_conflict",
            "resource_failure",
        ],
        "actions": ["investigate", "propose", "approve", "verify", "handoff"],
    },
    "admin": {
        "label": "Platform administrator",
        "views": ["inventory_mismatch", "replenishment_alert", "priority_override", "fleet_readiness",
                  "control_asset_readiness",
                  "task_completion_conflict", "resource_failure"],
        "actions": [],
    },
}
ASSUMPTIONS = [
    "The demo persona header is a role switcher and is not secure authentication.",
    "Supplied CSV/JSONL snapshots remain immutable source evidence; interventions add POC decisions and overlays only.",
    "Cross-source disagreement does not establish physical ground truth without a recorded physical verification.",
    "Approvals are operational POC decisions; no action dispatches equipment or changes the legacy database.",
    "POC task stages use the shared configurable simulator duration (45 seconds by default) and retain the restart-safe stock-effect guard.",
]

_ORIGINAL_RAW_SOURCE_ROWS = fulfillment._raw_source_rows
_ORIGINAL_SOURCE_ROWS = fulfillment.source_rows


def _ensure_schema() -> None:
    """Create persona tables in the same SQLite file, without changing source data."""

    fulfillment._init_db()
    with fulfillment._db_lock:
        with sqlite3.connect(fulfillment.DB_PATH, timeout=5) as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA busy_timeout=5000;
                CREATE TABLE IF NOT EXISTS persona_interventions (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT UNIQUE,
                    kind TEXT NOT NULL,
                    warehouse_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    proposed_action_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS persona_intervention_scope
                    ON persona_interventions(owner, kind, status);
                CREATE TABLE IF NOT EXISTS persona_intervention_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intervention_id TEXT NOT NULL,
                    at TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    FOREIGN KEY(intervention_id) REFERENCES persona_interventions(id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS persona_events_intervention
                    ON persona_intervention_events(intervention_id, id);
                CREATE TABLE IF NOT EXISTS persona_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS persona_audit_at
                    ON persona_audit_events(id, at);
                CREATE TABLE IF NOT EXISTS persona_safety_holds (
                    robot_id TEXT PRIMARY KEY,
                    warehouse_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    intervention_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    released_at TEXT
                );
                CREATE TABLE IF NOT EXISTS persona_task_pauses (
                    task_id TEXT PRIMARY KEY,
                    remaining_seconds INTEGER NOT NULL,
                    resource_id TEXT,
                    reason TEXT NOT NULL,
                    intervention_id TEXT NOT NULL,
                    paused_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS persona_resource_blocks (
                    resource_id TEXT PRIMARY KEY,
                    warehouse_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    intervention_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS registered_resources (
                    dataset TEXT NOT NULL,
                    row_id TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    PRIMARY KEY(dataset, row_id)
                );
                CREATE TABLE IF NOT EXISTS persona_detection_state (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    source_revision INTEGER NOT NULL,
                    registration_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS persona_inventory_overlays (
                    warehouse_id TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    physical_qty REAL NOT NULL,
                    intervention_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(warehouse_id, sku)
                );
                """
            )
            persona_v2.ensure_schema(db)
            columns = {
                row[1] for row in db.execute("PRAGMA table_info(persona_interventions)")
            }
            if "recurrence_count" not in columns:
                db.execute(
                    "ALTER TABLE persona_interventions ADD COLUMN recurrence_count "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            detection_columns = {
                row[1] for row in db.execute("PRAGMA table_info(persona_detection_state)")
            }
            if "format_version" not in detection_columns:
                db.execute(
                    "ALTER TABLE persona_detection_state ADD COLUMN format_version "
                    "INTEGER NOT NULL DEFAULT 1"
                )
            if "correction_fingerprint" not in detection_columns:
                db.execute(
                    "ALTER TABLE persona_detection_state ADD COLUMN correction_fingerprint "
                    "TEXT NOT NULL DEFAULT ''"
                )


def _registered_rows(dataset: str) -> tuple[dict[str, Any], ...]:
    active = fulfillment._active_db.get()
    if active is not None:
        try:
            rows = active.execute(
                "SELECT values_json FROM registered_resources WHERE dataset=? ORDER BY registered_at,row_id",
                (dataset,),
            )
            return tuple(json.loads(row["values_json"]) for row in rows)
        except sqlite3.OperationalError:
            return ()
    try:
        with sqlite3.connect(fulfillment.DB_PATH, timeout=5) as db:
            rows = db.execute(
                "SELECT values_json FROM registered_resources WHERE dataset=? ORDER BY registered_at,row_id",
                (dataset,),
            )
            return tuple(json.loads(row[0]) for row in rows)
    except sqlite3.OperationalError:
        return ()


def _raw_source_rows_with_registered(dataset: str) -> tuple[dict[str, Any], ...]:
    rows = _ORIGINAL_RAW_SOURCE_ROWS(dataset) + _registered_rows(dataset)
    active = fulfillment._active_db.get()
    return persona_v2.effective_source_rows(active, dataset, rows)


# Existing fulfillment resource/catalog functions resolve this global at call
# time.  Appending here makes registrations visible to planner inputs and
# resource rows while preserving stable original row indices.
fulfillment._raw_source_rows = _raw_source_rows_with_registered  # type: ignore[assignment]
# Keep the cache invalidation seam used by the original resource browser.
fulfillment._raw_source_rows.cache_clear = _ORIGINAL_RAW_SOURCE_ROWS.cache_clear  # type: ignore[attr-defined]


def _source_rows_with_corrections(dataset: str) -> tuple[dict[str, Any], ...]:
    """Apply durable corrections after scenario overlays, inside or outside a tx."""

    rows = _ORIGINAL_SOURCE_ROWS(dataset)
    active = fulfillment._active_db.get()
    if active is not None:
        return persona_v2.effective_source_rows(active, dataset, rows)
    if dataset not in {"robots", "maintenance", "control_assets"}:
        return rows
    try:
        with sqlite3.connect(fulfillment.DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            return persona_v2.effective_source_rows(db, dataset, rows)
    except sqlite3.OperationalError:
        return rows


fulfillment.source_rows = _source_rows_with_corrections  # type: ignore[assignment]

_ORIGINAL_ROBOT_ELIGIBILITY = fulfillment.robot_eligibility


def _robot_eligibility_with_holds(
    robot: dict[str, Any], maintenance: dict[str, str]
) -> tuple[bool, list[str]]:
    safe, reasons = _ORIGINAL_ROBOT_ELIGIBILITY(robot, maintenance)
    try:
        active = fulfillment._active_db.get()
        if active is not None:
            held = active.execute(
                "SELECT reason FROM persona_safety_holds "
                "WHERE robot_id=? AND released_at IS NULL",
                (robot.get("robot_id"),),
            ).fetchone()
        else:
            held = None
    except sqlite3.OperationalError:
        held = None
    if held:
        reasons = reasons + [held["reason"]]
        safe = False
    return safe, reasons


fulfillment.robot_eligibility = _robot_eligibility_with_holds  # type: ignore[assignment]
# V1 treated persona physical counts as a WMS overlay and subtracted POC
# commitments.  V2 inventory is already free stock and owns its correction
# transaction; wrapping it would double-subtract reservations.


def _tx():
    _ensure_schema()
    return fulfillment.db_transaction()


def _read_tx():
    _ensure_schema()
    return fulfillment._read_db()


def _role(value: str | None) -> str:
    # FastAPI replaces Header defaults during request handling; direct Python
    # callers/tests see the Header marker itself, which means the documented
    # supervisor default must also work outside ASGI.
    raw = value if isinstance(value, str) else "supervisor"
    role = raw.strip().lower()
    if role not in PERSONAS:
        raise HTTPException(403, "Unknown demo persona; use fleet, supervisor, or admin")
    return role


def _json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True)


def _object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    return json.loads(value)


def _event_json(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "at": row["at"],
        "persona": row["persona"],
        "action": row["action"],
        "reason": row["reason"],
        "details": _object(row["details_json"]),
    }


def _visible(role: str, row: sqlite3.Row) -> bool:
    if role == "admin":
        return True
    if row["kind"] not in POLICY[role]["views"]:
        return False
    if row["owner"] == role:
        return True
    # Supervisors are the independent approver for fleet proposals.  Requiring
    # an extra ownership handoff made an awaiting proposal undiscoverable in
    # their workspace.  Visibility is limited to the approval/verification
    # phase and does not grant fleet creation/proposal capability.
    if role == "supervisor" and row["kind"] in persona_v2.FLEET_KINDS:
        proposed = _object(row["proposed_action_json"])
        return row["status"] == "awaiting_approval" or bool(proposed.get("approved"))
    return False


def _allowed_actions(role: str, row: sqlite3.Row) -> list[str]:
    if role == "admin" or not _visible(role, row) or row["status"] == "resolved":
        return []
    if role == "supervisor" and row["kind"] == "inventory_mismatch":
        manual_close = ["manual_close"]
    elif role == "supervisor" and row["kind"] == "replenishment_alert":
        evidence = _object(row["evidence_json"])
        token = evidence.get("condition_fingerprint")
        manual_close = ["manual_close"] if isinstance(token, str) and token else []
    else:
        manual_close = []
    action_set = set(POLICY[role]["actions"])
    status = row["status"]
    if status == "open":
        wanted = ["investigate"]
    elif status == "investigating":
        proposed = _object(row["proposed_action_json"])
        if proposed.get("approved"):
            wanted = ["verify", "handoff"]
        elif proposed and role == "supervisor":
            wanted = ["approve", "handoff"]
        else:
            wanted = ["propose", "handoff"]
    else:  # awaiting_approval; approval is separate from verification
        wanted = ["approve", "handoff"]
    return manual_close + [action for action in wanted if action in action_set]


def _intervention_json(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    role: str,
    events_by_id: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    events = (
        events_by_id.get(row["id"], [])
        if events_by_id is not None
        else [
            _event_json(item)
            for item in db.execute(
                "SELECT at,persona,action,reason,details_json "
                "FROM persona_intervention_events WHERE intervention_id=? ORDER BY id",
                (row["id"],),
            )
        ]
    )
    evidence = _object(row["evidence_json"])
    linked_work = evidence.get("linked_work") or []
    priority = "P1" if linked_work else "P2"
    return {
        "id": row["id"],
        "kind": row["kind"],
        "warehouse_id": row["warehouse_id"],
        "entity_id": row["entity_id"],
        "title": row["title"],
        "description": row["description"],
        "owner": row["owner"],
        "status": row["status"],
        "evidence": evidence,
        "priority": priority,
        "linked_work": linked_work,
        "current_state": evidence.get("current_state"),
        "proposed_action": _object(row["proposed_action_json"])
        if row["proposed_action_json"]
        else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "events": events,
        "recurrence_count": int(row["recurrence_count"] or 0)
        if "recurrence_count" in row.keys()
        else 0,
        "allowed_actions": _allowed_actions(role, row),
    }


def _audit(
    db: sqlite3.Connection,
    persona: str,
    action: str,
    entity_id: str,
    reason: str,
    details: dict[str, Any],
) -> None:
    db.execute(
        "INSERT INTO persona_audit_events(at,persona,action,entity_id,reason,details_json) "
        "VALUES (?,?,?,?,?,?)",
        (fulfillment.iso(fulfillment.utc_now()), persona, action, entity_id, reason, _json(details)),
    )


def _add_event(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    persona: str,
    action: str,
    reason: str,
    details: dict[str, Any] | None = None,
) -> None:
    now = fulfillment.iso(fulfillment.utc_now())
    detail = details or {}
    db.execute(
        "INSERT INTO persona_intervention_events(intervention_id,at,persona,action,reason,details_json) "
        "VALUES (?,?,?,?,?,?)",
        (row["id"], now, persona, action, reason, _json(detail)),
    )
    db.execute(
        "UPDATE persona_interventions SET updated_at=? WHERE id=?", (now, row["id"])
    )
    _audit(db, persona, action, row["id"], reason, {"kind": row["kind"], **detail})


def _fetch(db: sqlite3.Connection, intervention_id: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM persona_interventions WHERE id=?", (intervention_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Unknown intervention: {intervention_id}")
    return row


def _require_visible(role: str, row: sqlite3.Row) -> None:
    if not _visible(role, row):
        raise HTTPException(403, "This persona cannot operate this intervention")


_INVENTORY_FINGERPRINT_FIELDS = (
    "warehouse_id",
    "sku",
    "inventory_row_id",
    "location",
    "zone",
    "wms_qty",
    "erp_qty",
    "vision_qty",
    "reserved_qty",
    "picked_qty",
    "allocatable_qty",
    "revision",
    "blocked_allocation",
    "opening_discrepancy",
)


def _fingerprint_inventory_rows(rows: list[dict[str, Any]]) -> str:
    """Fingerprint exact source state; any later state change is a recurrence."""

    normalized = [
        {field: row.get(field) for field in _INVENTORY_FINGERPRINT_FIELDS}
        for row in rows
    ]
    normalized.sort(
        key=lambda item: (
            str(item.get("inventory_row_id") or ""),
            str(item.get("location") or ""),
        )
    )
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _location_low_stock_fingerprint(
    rows: list[dict[str, Any]], threshold: int, inventory_policy: str,
    forecast_method: str | None = None,
) -> str:
    normalized = [
        {field: row.get(field) for field in _INVENTORY_FINGERPRINT_FIELDS}
        for row in rows
    ]
    normalized.sort(
        key=lambda item: (
            str(item.get("inventory_row_id") or ""),
            str(item.get("location") or ""),
        )
    )
    encoded = json.dumps(
        {
            "scope": "location",
            "threshold": threshold,
            "inventory_policy": inventory_policy,
            "forecast_method": forecast_method,
            "inventory_rows": normalized,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _current_inventory_rows(
    db: sqlite3.Connection, row: sqlite3.Row
) -> list[dict[str, Any]]:
    evidence = _object(row["evidence_json"])
    warehouse_id = str(evidence.get("warehouse_id") or row["warehouse_id"] or "")
    entity = str(row["entity_id"] or "")
    sku = str(evidence.get("sku") or entity.split("@", 1)[0])
    location = evidence.get("location")
    if location is None and "@" in entity:
        location = entity.split("@", 1)[1]
    inventory_row_id = evidence.get("inventory_row_id")

    if persona_v2.inventory_v2_available():
        fulfillment.ensure_inventory(db)
        candidates = [
            dict(item)
            for item in fulfillment.inventory_rows(db, warehouse_id=warehouse_id, sku=sku)
        ]
        if inventory_row_id is not None:
            candidates = [
                item
                for item in candidates
                if str(item.get("inventory_row_id")) == str(inventory_row_id)
            ]
        elif location:
            candidates = [
                item for item in candidates if str(item.get("location") or "") == str(location)
            ]
    else:
        candidates = [
            dict(item)
            for item in fulfillment.source_rows("inventory")
            if str(item.get("warehouse_id") or "") == warehouse_id
            and str(item.get("sku") or "") == sku
            and (not location or str(item.get("location") or "") == str(location))
        ]
    if not candidates:
        raise HTTPException(409, "Inventory source condition is no longer available")
    return candidates


def _current_inventory_fingerprint(db: sqlite3.Connection, row: sqlite3.Row) -> str:
    candidates = _current_inventory_rows(db, row)
    # Historical manually-created SKU issues may not identify a location.  In
    # that case the exact state of every matching SKU row defines recurrence.
    return _fingerprint_inventory_rows(candidates)


def _current_location_low_stock_evidence(
    db: sqlite3.Connection, row: sqlite3.Row
) -> dict[str, Any]:
    contextual_rows = _current_inventory_rows(db, row)
    import demand_forecast
    run, forecasts = demand_forecast.current_thresholds(db)
    evidence = _object(row["evidence_json"])
    warehouse_id = str(evidence.get("warehouse_id") or row["warehouse_id"] or "")
    sku = str(evidence.get("sku") or str(row["entity_id"]).split("@", 1)[0])
    forecast = forecasts.get((warehouse_id, sku))
    if run is None or forecast is None:
        raise HTTPException(409, "Low-stock forecast condition is no longer available")
    threshold = int(forecast["forecast_7d"])
    policy = "free_source_min_sum"
    aggregate_rows = [
        dict(item)
        for item in fulfillment.inventory_rows(
            db, warehouse_id=warehouse_id, sku=sku
        )
    ]
    available = sum(
        max(0, min(
            int(item.get("wms_qty") or 0),
            int(item.get("erp_qty") or 0),
            int(item.get("vision_qty") or 0),
        ))
        for item in aggregate_rows
    )
    if available >= threshold:
        raise HTTPException(409, "Low-stock alert condition is no longer active")
    return {
        "threshold": threshold,
        "forecast_7d": threshold,
        "forecast_30d": int(forecast["forecast_30d"]),
        "forecast_date": run["forecast_date"],
        "history_days": int(forecast["history_days"]),
        "history_status": forecast["history_status"],
        "forecast_method": run["method"],
        "inventory_policy": policy,
        "available": available,
        "current_state": contextual_rows[0] if len(contextual_rows) == 1 else contextual_rows,
        "inventory_state": aggregate_rows,
        "condition_fingerprint": _location_low_stock_fingerprint(
            aggregate_rows, threshold, policy, run["method"]
        ),
    }


def _aggregate_low_stock_evidence(
    db: sqlite3.Connection,
    alert: dict[str, Any],
    inventory_by_key: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
    held_by_sku: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    warehouse_id = str(alert["warehouse_id"])
    sku = str(alert["sku"])
    if inventory_by_key is not None:
        source_rows = inventory_by_key.get((warehouse_id, sku), [])
    elif persona_v2.inventory_v2_available():
        source_rows = [
            dict(item)
            for item in fulfillment.inventory_rows(
                db, warehouse_id=warehouse_id, sku=sku
            )
        ]
    else:
        source_rows = []
    inventory_rows = [
        {
            field: item.get(field)
            for field in _INVENTORY_FINGERPRINT_FIELDS
        }
        for item in source_rows
    ]
    inventory_rows.sort(
        key=lambda item: (
            str(item.get("inventory_row_id") or ""),
            str(item.get("location") or ""),
        )
    )
    condition = {
        key: alert[key]
        for key in (
            "available", "threshold", "inventory_policy", "forecast_7d",
            "forecast_30d", "forecast_date", "history_days", "history_status",
            "forecast_method",
        )
        if key in alert
    }
    fingerprint_condition = {
        key: condition[key]
        for key in (
            "available",
            "threshold",
            "inventory_policy",
            "forecast_7d",
            "forecast_30d",
            "forecast_method",
        )
        if key in condition
    }
    encoded = json.dumps(
        {
            "warehouse_id": warehouse_id,
            "sku": sku,
            # A newly generated run with unchanged predictions is the same
            # condition. Forecast date/history remain visible evidence, but do
            # not gratuitously reopen an acknowledged shortage.
            "condition": fingerprint_condition,
            "inventory_rows": inventory_rows,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return {
        "source": "effective_low_stock",
        "alert_scope": "warehouse_sku",
        "warehouse_id": warehouse_id,
        "sku": sku,
        "current_state": condition,
        "inventory_state": inventory_rows,
        "condition_fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "linked_work": (
            [
                item
                for item in held_by_sku.get(sku, [])
                if item.get("warehouse_id") in {None, warehouse_id}
            ]
            if held_by_sku is not None
            else persona_v2.linked_held_work(db, warehouse_id, sku)
        ),
    }


def _current_aggregate_low_stock_evidence(
    db: sqlite3.Connection, row: sqlite3.Row
) -> dict[str, Any]:
    sku = _replenishment_sku(row)
    current = next(
        (
            dict(alert)
            for alert in fulfillment.stock_alerts(db)
            if str(alert.get("warehouse_id")) == str(row["warehouse_id"])
            and str(alert.get("sku")) == sku
        ),
        None,
    )
    if current is None:
        raise HTTPException(409, "Low-stock alert condition is no longer active")
    return _aggregate_low_stock_evidence(db, current)


def _insert_detected(
    db: sqlite3.Connection,
    kind: str,
    warehouse_id: str,
    entity_id: str,
    title: str,
    description: str,
    evidence: dict[str, Any],
    dedupe_key: str,
    existing_by_key: dict[str, sqlite3.Row] | None = None,
) -> None:
    owner = "fleet" if kind in persona_v2.FLEET_KINDS else "supervisor"
    now = fulfillment.iso(fulfillment.utc_now())
    existing = existing_by_key.get(dedupe_key) if existing_by_key is not None else None
    try:
        if existing is not None:
            raise sqlite3.IntegrityError
        db.execute(
            "INSERT INTO persona_interventions "
            "(id,dedupe_key,kind,warehouse_id,entity_id,title,description,owner,status,"
            "evidence_json,proposed_action_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"INT-{uuid.uuid4()}",
                dedupe_key,
                kind,
                warehouse_id or "unknown",
                entity_id,
                title,
                description,
                owner,
                "open",
                _json(evidence),
                None,
                now,
                now,
            ),
        )
        row = db.execute(
            "SELECT * FROM persona_interventions WHERE dedupe_key=?", (dedupe_key,)
        ).fetchone()
        _add_event(db, row, "system", "detected", "Source discrepancy detected", evidence)
        if existing_by_key is not None:
            existing_by_key[dedupe_key] = row
    except sqlite3.IntegrityError:
        existing = existing or db.execute(
            "SELECT * FROM persona_interventions WHERE dedupe_key=?", (dedupe_key,)
        ).fetchone()
        if not existing:
            return
        # A recurring effective condition is actionable again.  Updating the
        # evidence also keeps linked-work priority current without fabricating
        # a new source identity.
        recurrence = int(existing["recurrence_count"] or 0)
        existing_evidence = _object(existing["evidence_json"])
        manual_closure = existing_evidence.get("manual_closure")
        if existing["kind"] == "inventory_mismatch" and isinstance(manual_closure, dict):
            current_fingerprint = _current_inventory_fingerprint(db, existing)
        elif existing["kind"] == "replenishment_alert" and isinstance(manual_closure, dict):
            current_fingerprint = evidence.get("condition_fingerprint")
        else:
            current_fingerprint = None
        same_manual_condition = (
            isinstance(manual_closure, dict)
            and manual_closure.get("fingerprint") == current_fingerprint
            and not existing_evidence.get("condition_recovered")
        )
        reopened = existing["status"] == "resolved" and not same_manual_condition
        if same_manual_condition:
            evidence = {**evidence, "manual_closure": manual_closure}
        encoded_evidence = _json(evidence)
        if reopened or existing["owner"] != owner or existing["evidence_json"] != encoded_evidence:
            db.execute(
                "UPDATE persona_interventions SET status=?,owner=?,evidence_json=?,"
                "recurrence_count=?,updated_at=? WHERE id=?",
                (
                    "open" if reopened else existing["status"],
                    owner,
                    encoded_evidence,
                    recurrence + (1 if reopened else 0),
                    now,
                    existing["id"],
                ),
            )
        if reopened:
            _add_event(
                db,
                existing,
                "system",
                "reopened",
                "Underlying source condition recurred",
                evidence,
            )


def _detect_all(db: sqlite3.Connection) -> None:
    """Inspect every supplied row; no sampling or synthetic outages."""

    revision = fulfillment._scenario_revision(db)
    registered_count = db.execute(
        "SELECT COUNT(*) AS count FROM registered_resources"
    ).fetchone()["count"]
    correction_fingerprint = db.execute(
        "SELECT COUNT(*) || ':' || COALESCE(MAX(updated_at),'') "
        "FROM persona_source_corrections"
    ).fetchone()[0]
    previous = db.execute(
        "SELECT source_revision,registration_count,format_version,correction_fingerprint "
        "FROM persona_detection_state WHERE id=1"
    ).fetchone()
    if previous and (
        int(previous["source_revision"]) == revision
        and int(previous["registration_count"]) == int(registered_count)
        and int(previous["format_version"]) == 3
        and previous["correction_fingerprint"] == correction_fingerprint
    ):
        return

    robots = {row.get("robot_id"): row for row in fulfillment.source_rows("robots")}
    maintenance_rows = fulfillment.source_rows("maintenance")
    maintenance_by_robot: dict[str, list[dict[str, Any]]] = {}
    for item in maintenance_rows:
        maintenance_by_robot.setdefault(item.get("robot_id", ""), []).append(item)

    # V2 effective inventory has its own location revisions and free-stock
    # semantics below; inspecting the immutable opening CSV here would create
    # stale duplicate issues after an authoritative correction.
    inventory_detection_rows = (
        () if persona_v2.inventory_v2_available() else fulfillment.source_rows("inventory")
    )
    for row in inventory_detection_rows:
        values = {row.get("wms_qty"), row.get("erp_qty"), row.get("vision_qty")}
        if len(values) > 1:
            entity = f"{row.get('sku')}@{row.get('location')}"
            evidence = {
                "source": "inventory_snapshot",
                "warehouse_id": row.get("warehouse_id"),
                "sku": row.get("sku"),
                "location": row.get("location"),
                "wms_qty": row.get("wms_qty"),
                "erp_qty": row.get("erp_qty"),
                "vision_qty": row.get("vision_qty"),
                "reserved_qty": row.get("reserved_qty"),
                "physical_truth": "unresolved",
            }
            _insert_detected(
                db,
                "inventory_mismatch",
                row.get("warehouse_id", ""),
                entity,
                f"Inventory mismatch: {row.get('sku')} at {row.get('location')}",
                "WMS, ERP, and/or vision quantities disagree. Physical truth is unresolved.",
                evidence,
                f"inventory_mismatch:{row.get('warehouse_id')}:{entity}",
            )

    for row in fulfillment.source_rows("tasks"):
        assigned = robots.get(row.get("assigned_robot"))
        mismatch = row.get("wes_status") != row.get("fleet_status")
        if assigned and assigned.get("warehouse_id") != row.get("warehouse_id"):
            mismatch = True
        if not assigned:
            mismatch = True
        if mismatch:
            evidence = {
                "source": "tasks",
                "task_id": row.get("task_id"),
                "order_id": row.get("order_id"),
                "wes_status": row.get("wes_status"),
                "fleet_status": row.get("fleet_status"),
                "assigned_robot": row.get("assigned_robot"),
                "robot_registry_warehouse": assigned.get("warehouse_id") if assigned else None,
                "physical_outcome": "unresolved",
            }
            _insert_detected(
                db,
                "task_completion_conflict",
                row.get("warehouse_id", ""),
                row.get("task_id", ""),
                f"Task completion conflict: {row.get('task_id')}",
                "WES and fleet completion state or assigned-robot site disagrees; no replay is performed.",
                evidence,
                f"task_completion_conflict:{row.get('task_id')}",
            )

    for robot_id, robot in robots.items():
        maintenance = maintenance_by_robot.get(robot_id or "", [])
        active_maintenance = [
            item
            for item in maintenance
            if item.get("cmms_status") in {"OPEN", "IN_PROGRESS"}
        ]
        if hasattr(fulfillment, "v2_robot_eligibility"):
            safe, reasons = persona_v2.strict_robot_readiness(
                db, robot, maintenance_rows
            )
        else:
            safe, reasons = fulfillment.robot_eligibility(
                robot, fulfillment.maintenance_exclusions(robot.get("warehouse_id", ""))
            )
        claimed_available = bool(active_maintenance) or not safe
        if claimed_available:
            robot_revision = persona_v2.source_revision(db, "robots", robot_id or "")
            maintenance_contexts = [
                {
                    "entity_type": "maintenance",
                    "entity_id": item.get("work_order_id"),
                    "revision": persona_v2.source_revision(
                        db, "maintenance", str(item.get("work_order_id") or "")
                    ),
                    "current_state": {
                        "cmms_status": item.get("cmms_status"),
                        "fleet_availability": item.get("fleet_availability"),
                    },
                    "blocking": item.get("cmms_status") in {"OPEN", "IN_PROGRESS"}
                    or item.get("fleet_availability") != "AVAILABLE",
                }
                for item in maintenance
                if item.get("work_order_id")
            ]
            evidence = {
                "source": "robots+maintenance",
                "robot_id": robot_id,
                "warehouse_id": robot.get("warehouse_id"),
                "health_status": robot.get("health_status"),
                "safety_cert_status": robot.get("safety_cert_status"),
                "calibration_status": robot.get("calibration_status"),
                "connectivity": robot.get("connectivity"),
                "maintenance": active_maintenance,
                "unsafe_reasons": reasons,
                "physical_outage": "not inferred",
                "revision": robot_revision,
                "current_state": dict(robot),
                "editable_contexts": [
                    {
                        "entity_type": "robot",
                        "entity_id": robot_id,
                        "revision": robot_revision,
                        "current_state": {
                            field: robot.get(field)
                            for field in sorted(persona_v2.ROBOT_FIELDS)
                        },
                        "blocking": not safe,
                    },
                    *maintenance_contexts,
                ],
            }
            _insert_detected(
                db,
                "fleet_readiness",
                robot.get("warehouse_id", ""),
                robot_id or "",
                f"Fleet readiness review: {robot_id}",
                "Source state claims a robot may be available while safety or maintenance evidence is not clear.",
                evidence,
                f"fleet_readiness:{robot.get('warehouse_id')}:{robot_id}",
            )
    db.execute(
        "INSERT INTO persona_detection_state"
        "(id,source_revision,registration_count,format_version,correction_fingerprint) "
        "VALUES (1,?,?,3,?) "
        "ON CONFLICT(id) DO UPDATE SET source_revision=excluded.source_revision,"
        "registration_count=excluded.registration_count,"
        "format_version=excluded.format_version,"
        "correction_fingerprint=excluded.correction_fingerprint",
        (revision, registered_count, correction_fingerprint),
    )


def _detect_v2(db: sqlite3.Connection) -> None:
    """Detect authoritative inventory alerts and control-asset blockers."""

    if not persona_v2.inventory_v2_available():
        return
    fulfillment.ensure_inventory(db)
    import demand_forecast
    forecast_run, forecasts = demand_forecast.current_thresholds(db)
    fingerprint = persona_v2.detection_fingerprint(db)
    previous = db.execute(
        "SELECT fingerprint FROM persona_v2_detection_state WHERE id=1"
    ).fetchone()
    if previous and previous["fingerprint"] == fingerprint:
        return
    held_by_sku = persona_v2.held_work_index(db)
    detected_replenishment_keys: set[str] = set()
    existing_by_key = {
        row["dedupe_key"]: row
        for row in db.execute(
            "SELECT * FROM persona_interventions WHERE dedupe_key LIKE 'v2:%'"
        )
    }
    inventory_rows = [dict(source) for source in fulfillment.inventory_rows(db)]
    inventory_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in inventory_rows:
        inventory_by_key.setdefault(
            (str(row.get("warehouse_id") or ""), str(row.get("sku") or "")), []
        ).append(row)
    for row in inventory_rows:
        warehouse_id = str(row.get("warehouse_id") or "")
        sku = str(row.get("sku") or "")
        location = str(row.get("location") or "")
        if not warehouse_id or not sku:
            continue
        # A null-warehouse shortage is relevant to every warehouse candidate
        # for this SKU; warehouse-bound held rows remain scoped to their site.
        linked = [
            item
            for item in held_by_sku.get(sku, [])
            if item.get("warehouse_id") in {None, warehouse_id}
        ]
        current = {
            key: row.get(key)
            for key in (
                "inventory_row_id",
                "location",
                "zone",
                "wms_qty",
                "erp_qty",
                "vision_qty",
                "reserved_qty",
                "picked_qty",
                "allocatable_qty",
                "revision",
                "blocked_allocation",
                "opening_discrepancy",
            )
        }
        evidence = {
            "source": "effective_inventory",
            "warehouse_id": warehouse_id,
            "sku": sku,
            "location": location,
            "inventory_row_id": row.get("inventory_row_id"),
            "linked_work": linked,
            "current_state": current,
        }
        values = {row.get("wms_qty"), row.get("erp_qty"), row.get("vision_qty")}
        if len(values) > 1 or row.get("opening_discrepancy"):
            entity = f"{sku}@{location}"
            _insert_detected(
                db,
                "inventory_mismatch",
                warehouse_id,
                entity,
                f"Inventory discrepancy: {sku} at {location}",
                "Effective WMS, ERP, and vision free quantities disagree.",
                evidence,
                f"v2:inventory_mismatch:{warehouse_id}:{entity}",
                existing_by_key,
            )
        forecast = forecasts.get((warehouse_id, sku))
        threshold = int(forecast["forecast_7d"]) if forecast else 0
        aggregate_rows = inventory_by_key.get((warehouse_id, sku), [])
        available = sum(
            max(
                0,
                min(
                    int(item.get("wms_qty") or 0),
                    int(item.get("erp_qty") or 0),
                    int(item.get("vision_qty") or 0),
                ),
            )
            for item in aggregate_rows
        )
        if forecast and available < threshold:
            entity = f"{sku}@{location}"
            dedupe_key = f"v2:replenishment:{warehouse_id}:{entity}"
            replenishment_evidence = {
                **evidence,
                "threshold": threshold,
                "forecast_7d": threshold,
                "forecast_30d": int(forecast["forecast_30d"]),
                "forecast_date": forecast_run["forecast_date"],
                "history_days": int(forecast["history_days"]),
                "history_status": forecast["history_status"],
                "forecast_method": forecast_run["method"],
                "inventory_policy": "free_source_min_sum",
                "available": available,
                "inventory_state": aggregate_rows,
                "condition_fingerprint": _location_low_stock_fingerprint(
                    aggregate_rows, threshold, "free_source_min_sum", forecast_run["method"]
                ),
            }
            _insert_detected(
                db,
                "replenishment_alert",
                warehouse_id,
                entity,
                f"Replenishment alert: {sku} at {location}",
                "Warehouse/SKU free availability is below predicted seven-day demand; "
                "this location is retained as inventory context.",
                replenishment_evidence,
                dedupe_key,
                existing_by_key,
            )
            detected_replenishment_keys.add(dedupe_key)

    for asset in fulfillment.source_rows("control_assets"):
        reasons: list[str] = []
        if asset.get("state") != "AVAILABLE":
            reasons.append(f"state is {asset.get('state') or 'unknown'}")
        if asset.get("maintenance_state") != "CLEAR":
            reasons.append(
                f"maintenance state is {asset.get('maintenance_state') or 'unknown'}"
            )
        if not reasons:
            continue
        asset_id = str(asset.get("asset_id") or "")
        warehouse_id = str(asset.get("warehouse_id") or "")
        _insert_detected(
            db,
            "control_asset_readiness",
            warehouse_id,
            asset_id,
            f"Control asset readiness: {asset_id}",
            "The effective control-asset source has readiness blockers.",
            {
                "source": "control_assets",
                "current_state": dict(asset),
                "unsafe_reasons": reasons,
                "revision": persona_v2.source_revision(db, "control_assets", asset_id),
                "editable_contexts": [
                    {
                        "entity_type": "control_asset",
                        "entity_id": asset_id,
                        "revision": persona_v2.source_revision(
                            db, "control_assets", asset_id
                        ),
                        "current_state": {
                            field: asset.get(field)
                            for field in sorted(persona_v2.ASSET_FIELDS)
                        },
                        "blocking": True,
                    }
                ],
            },
            f"v2:control_asset:{warehouse_id}:{asset_id}",
            existing_by_key,
        )
    # Absence of a valid forecast is detector unavailability, not evidence of
    # stock recovery. Preserve durable shortage history until a valid (possibly
    # stale) run can evaluate the condition.
    if forecast_run is not None:
        _reconcile_location_low_stock_recovery(db, detected_replenishment_keys)
    db.execute(
        "INSERT INTO persona_v2_detection_state(id,fingerprint) VALUES (1,?) "
        "ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint",
        (fingerprint,),
    )


class InterventionCreate(BaseModel):
    kind: Literal[
        "inventory_mismatch",
        "replenishment_alert",
        "priority_override",
        "fleet_readiness",
        "control_asset_readiness",
        "task_completion_conflict",
        "resource_failure",
    ]
    warehouse_id: str = Field(..., min_length=1, max_length=64)
    entity_id: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)
    evidence: dict[str, Any] | None = None


class InterventionAction(BaseModel):
    action: Literal["investigate", "propose", "approve", "verify", "handoff", "manual_close"]
    reason: str = Field(..., min_length=1, max_length=2000)
    evidence: dict[str, Any] | None = None
    value: Any = None
    assigned_to: str | None = Field(None, max_length=200)


class FleetRepairContext(BaseModel):
    entity_type: Literal["robot", "maintenance", "control_asset"]
    entity_id: str = Field(..., min_length=1, max_length=200)
    revision: int = Field(..., ge=0)
    values: dict[str, str | None]


class FleetRepairRequest(BaseModel):
    fingerprint: str = Field(..., min_length=64, max_length=64)
    contexts: list[FleetRepairContext] = Field(..., min_length=1)


def _new_intervention(
    role: str, payload: InterventionCreate, db: sqlite3.Connection
) -> dict[str, Any]:
    if role == "fleet" and payload.kind in RETIRED_FLEET_MANUAL_REPORT_KINDS:
        raise HTTPException(
            403,
            "Fleet manual reports are retired; use detected fleet issues and "
            "the supported repair or simulator workflows",
        )
    if role == "admin" or payload.kind not in OPERATIONAL_KINDS[role]:
        raise HTTPException(403, "This persona cannot create that intervention kind")
    now = fulfillment.iso(fulfillment.utc_now())
    intervention_id = f"INT-{uuid.uuid4()}"
    db.execute(
        "INSERT INTO persona_interventions "
        "(id,dedupe_key,kind,warehouse_id,entity_id,title,description,owner,status,"
        "evidence_json,proposed_action_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            intervention_id,
            None,
            payload.kind,
            payload.warehouse_id,
            payload.entity_id,
            f"{payload.kind.replace('_', ' ').title()}: {payload.entity_id}",
            payload.description,
            "fleet" if payload.kind in persona_v2.FLEET_KINDS and role == "fleet" else "supervisor",
            "open",
            _json(payload.evidence or {}),
            None,
            now,
            now,
        ),
    )
    row = _fetch(db, intervention_id)
    _add_event(db, row, role, "created", "Manual intervention scenario created", payload.evidence or {})
    return _intervention_json(db, _fetch(db, intervention_id), role)


def _order_payload_kg(db: sqlite3.Connection, order_id: str) -> float:
    details, issues = fulfillment.order_weight_details(db, order_id)
    if issues:
        raise HTTPException(409, "Cannot replan order payload: " + "; ".join(issues))
    return details["payload_kg"]


def _task_for_resource(
    db: sqlite3.Connection, entity_id: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT tasks.* FROM tasks "
        "WHERE tasks.id=? OR tasks.resource_id=? OR EXISTS ("
        "SELECT 1 FROM task_resources tr WHERE tr.task_id=tasks.id AND tr.resource_id=?"
        ") ORDER BY CASE tasks.status WHEN 'running' THEN 0 ELSE 1 END LIMIT 1",
        (entity_id, entity_id, entity_id),
    ).fetchone()


def _claimed_by_other_task(
    db: sqlite3.Connection, resource_id: str, task_id: str
) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM tasks WHERE resource_id=? "
            "AND status IN ('pending','queued','running','paused') AND id<>?"
            " UNION SELECT 1 FROM task_resources tr JOIN tasks ON tasks.id=tr.task_id "
            "WHERE tr.resource_id=? AND tasks.status IN ('pending','queued','running','paused') "
            "AND tasks.id<>? LIMIT 1",
            (resource_id, task_id, resource_id, task_id),
        ).fetchone()
    )


def _recovery_resource(
    db: sqlite3.Connection, task: sqlite3.Row, assigned_to: str, failed_resource: str
) -> dict[str, Any]:
    """Validate an assigned recovery resource against the complete source registry."""

    assigned = assigned_to.strip() if isinstance(assigned_to, str) else ""
    if not assigned:
        raise HTTPException(422, "assigned_to must be a non-empty resource identifier")
    if assigned == failed_resource:
        raise HTTPException(422, "A recovery resource must differ from the failed resource")
    if _claimed_by_other_task(db, assigned, task["id"]):
        raise HTTPException(409, "Recovery resource is already claimed by another POC task")
    blocked = db.execute(
        "SELECT 1 FROM persona_resource_blocks WHERE resource_id=?", (assigned,)
    ).fetchone()
    if blocked:
        raise HTTPException(409, "Recovery resource is blocked by an unresolved resource failure")
    task_keys = set(task.keys())
    if "sub_order_id" in task_keys and task["sub_order_id"]:
        scope = db.execute(
            "SELECT warehouse_id FROM sub_orders WHERE id=?", (task["sub_order_id"],)
        ).fetchone()
    else:
        scope = db.execute(
            "SELECT warehouse_id FROM orders WHERE id=?", (task["order_id"],)
        ).fetchone()
    if not scope or not scope["warehouse_id"]:
        raise HTTPException(409, "Recovery task has no selected sub-order warehouse")
    warehouse_id = scope["warehouse_id"]
    stage = task["stage"]
    if stage in fulfillment_v2.ROBOT_TYPES:
        robot = next(
            (item for item in fulfillment.source_rows("robots")
             if item.get("robot_id") == assigned),
            None,
        )
        if not robot or robot.get("warehouse_id") != warehouse_id:
            raise HTTPException(422, "Recovery robot must be registered at the task warehouse")
        if robot.get("robot_type") not in fulfillment_v2.ROBOT_TYPES[stage]:
            raise HTTPException(422, "Recovery robot is not compatible with the task stage")
        payload = (
            float(task["payload_kg"] or 0)
            if "payload_kg" in task_keys
            else _order_payload_kg(db, task["order_id"])
        )
        capacity = fulfillment._float(robot.get("payload_kg"))
        if not math.isfinite(capacity) or capacity < payload:
            raise HTTPException(
                422, f"Recovery robot payload capacity {capacity:g}kg cannot handle "
                f"order payload {payload:g}kg (synthetic demo SKU weights)",
            )
        safe, reasons = fulfillment_v2.robot_eligibility(
            db,
            robot,
            warehouse_id,
            stage,
            payload,
            set(),
            fulfillment.source_rows("maintenance"),
            fulfillment.utc_now(),
        )
        if not safe:
            raise HTTPException(409, "Recovery robot failed source safety validation: " + "; ".join(reasons))
        resource_type = "robot"
    elif stage in fulfillment_v2.ASSET_TYPES:
        asset = next(
            (item for item in fulfillment.source_rows("control_assets")
             if item.get("asset_id") == assigned),
            None,
        )
        if (
            not asset
            or asset.get("warehouse_id") != warehouse_id
            or asset.get("asset_type") not in fulfillment_v2.ASSET_TYPES[stage]
        ):
            raise HTTPException(422, "Recovery control asset is incompatible with the V2 task stage")
        safe, reasons = fulfillment_v2.asset_eligibility(
            asset, warehouse_id, stage, set()
        )
        if not safe:
            raise HTTPException(
                409,
                "Recovery control asset failed source readiness validation: "
                + "; ".join(reasons),
            )
        resource_type = "control_asset"
    else:
        raise HTTPException(422, f"Unsupported recovery task stage: {stage}")
    return {"resource_id": assigned, "resource_type": resource_type}


def _resources_for_other_orders(
    db: sqlite3.Connection, warehouse_id: str, order_id: str
) -> set[str]:
    rows = db.execute(
        "SELECT tasks.resource_id FROM tasks JOIN orders ON orders.id=tasks.order_id "
        "WHERE orders.warehouse_id=? AND orders.id<>? "
        "AND tasks.status IN ('pending','queued','running','paused') AND tasks.resource_id IS NOT NULL "
        "UNION SELECT tr.resource_id FROM task_resources tr JOIN tasks ON tasks.id=tr.task_id "
        "JOIN orders ON orders.id=tasks.order_id WHERE orders.warehouse_id=? AND orders.id<>? "
        "AND tasks.status IN ('pending','queued','running','paused')",
        (warehouse_id, order_id, warehouse_id, order_id),
    )
    return {row["resource_id"] for row in rows}


def _assignment_for_preferred(
    db: sqlite3.Connection,
    task: sqlite3.Row,
    preferred: dict[str, Any],
    used: set[str],
    payload_kg: float,
) -> dict[str, Any] | None:
    """Build the same primary/auxiliary shape as the real planner."""

    warehouse_id = db.execute(
        "SELECT warehouse_id FROM orders WHERE id=?", (task["order_id"],)
    ).fetchone()["warehouse_id"]
    labor = fulfillment._labor(warehouse_id, fulfillment.config_values(db)["shift"])
    if not labor:
        return None
    stage = task["stage"]
    if stage in {"pick", "transfer"}:
        worker, operator, auxiliary, _ = fulfillment._worker_assignment(
            warehouse_id, stage, used, labor
        )
        if not worker:
            return None
        used.update(item["resource_id"] for item in auxiliary)
        return {
            "resource_id": preferred["resource_id"],
            "resource_type": preferred["resource_type"],
            "auxiliary_resources": auxiliary,
        }
    worker, secondary, auxiliary, _ = fulfillment._worker_assignment(
        warehouse_id, stage, used, labor
    )
    if not worker:
        return None
    used.update(item["resource_id"] for item in auxiliary)
    return {
        "resource_id": preferred["resource_id"],
        "resource_type": preferred["resource_type"],
        "auxiliary_resources": auxiliary,
    }


def _replan_remaining(
    db: sqlite3.Connection,
    task: sqlite3.Row,
    failed_resource: str,
    preferred: dict[str, Any] | None,
) -> None:
    """Persist a recovery preference without acquiring a resource claim."""

    order_id = task["order_id"]
    if "sub_order_id" in task.keys() and task["sub_order_id"]:
        sub = db.execute(
            "SELECT warehouse_id FROM sub_orders WHERE id=?", (task["sub_order_id"],)
        ).fetchone()
        if not sub:
            raise HTTPException(409, "Current V2 sub-order is stale")
        if preferred is not None:
            resource_id = preferred["resource_id"]
            if task["stage"] in fulfillment_v2.ROBOT_TYPES:
                resource = next(
                    (
                        row for row in fulfillment.source_rows("robots")
                        if row.get("robot_id") == resource_id
                    ),
                    None,
                )
                if not resource:
                    raise HTTPException(422, "Preferred recovery robot is unknown")
                safe, reasons = fulfillment.v2_robot_eligibility(
                    db, resource, sub["warehouse_id"], task["stage"],
                    float(task["payload_kg"] or 0),
                )
                resource_type = "robot"
            else:
                resource = next(
                    (
                        row for row in fulfillment.source_rows("control_assets")
                        if row.get("asset_id") == resource_id
                    ),
                    None,
                )
                if not resource:
                    raise HTTPException(422, "Preferred recovery asset is unknown")
                safe, reasons = fulfillment.v2_asset_eligibility(
                    resource, sub["warehouse_id"], task["stage"]
                )
                resource_type = "control_asset"
            if not safe:
                raise HTTPException(
                    409, "Preferred V2 recovery resource is ineligible: " + "; ".join(reasons)
                )
            db.execute(
                """INSERT INTO task_recovery_preferences(task_id,resource_id,resource_type,created_at)
                   VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                   resource_id=excluded.resource_id,resource_type=excluded.resource_type,
                   created_at=excluded.created_at""",
                (task["id"], resource_id, resource_type, fulfillment.iso(fulfillment.utc_now())),
            )
            fulfillment._append_event(
                db, order_id, f"Recovery preference recorded for {task['id']}: {resource_id}; awaiting verified resume and assignment cadence",
                fulfillment.utc_now(),
            )
            db.execute(
                "UPDATE tasks SET resource_id=NULL,resource_type=NULL WHERE id=?",
                (task["id"],),
            )
        else:
            db.execute("DELETE FROM task_recovery_preferences WHERE task_id=?", (task["id"],))
            db.execute(
                "UPDATE tasks SET resource_id=NULL,resource_type=NULL WHERE id=?",
                (task["id"],),
            )
        return
    raise HTTPException(409, "Policy V1 recovery planning is retired")


def _invalidate_for_hold(
    db: sqlite3.Connection, robot_id: str, warehouse_id: str, intervention_id: str
) -> None:
    """Invalidate unstarted plans and pause a running claim before it can tick."""

    affected = db.execute(
        "SELECT DISTINCT tasks.* FROM tasks JOIN orders ON orders.id=tasks.order_id "
        "WHERE (orders.warehouse_id=? OR EXISTS (SELECT 1 FROM sub_orders so "
        "WHERE so.id=tasks.sub_order_id AND so.warehouse_id=?)) "
        "AND tasks.status IN ('pending','queued','running') "
        "AND (tasks.resource_id=? OR EXISTS (SELECT 1 FROM task_resources tr "
        "WHERE tr.task_id=tasks.id AND tr.resource_id=?))",
        (warehouse_id, warehouse_id, robot_id, robot_id),
    ).fetchall()
    for task in affected:
        if "sub_order_id" in task.keys() and task["sub_order_id"]:
            reason = "WAITING_FOR_RESOURCE: approved safety hold"
            if task["status"] == "running":
                db.execute(
                    "INSERT OR REPLACE INTO persona_task_pauses "
                    "(task_id,remaining_seconds,resource_id,reason,intervention_id,paused_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        task["id"],
                        45,
                        robot_id,
                        reason,
                        intervention_id,
                        fulfillment.iso(fulfillment.utc_now()),
                    ),
                )
                db.execute(
                    "UPDATE tasks SET status='paused',due_at=NULL,wait_reason=? WHERE id=?",
                    (reason, task["id"]),
                )
                db.execute(
                    "UPDATE sub_orders SET status='reserved',hold_reason=? WHERE id=?",
                    (reason, task["sub_order_id"]),
                )
                db.execute(
                    "UPDATE orders SET status='held' WHERE id=?", (task["order_id"],)
                )
            else:
                # V2 stock acceptance is a separate committed transaction.
                # Drop only the unsafe resource claim and let the v2 executor
                # select an eligible replacement; never release/re-reserve.
                db.execute(
                    "UPDATE tasks SET status='queued',resource_id=NULL,resource_type=NULL,"
                    "started_at=NULL,due_at=NULL,wait_reason=? WHERE id=?",
                    (reason, task["id"]),
                )
                db.execute(
                    "UPDATE sub_orders SET status='queued',hold_reason=? WHERE id=?",
                    (reason, task["sub_order_id"]),
                )
            continue


def _validate_proposal(
    db: sqlite3.Connection, row: sqlite3.Row, payload: InterventionAction
) -> dict[str, Any]:
    evidence = payload.evidence
    if not evidence:
        raise HTTPException(422, "evidence is required when proposing an action")
    kind = row["kind"]
    value = payload.value
    if kind in persona_v2.INVENTORY_KINDS:
        if isinstance(value, dict) and "source" in value:
            missing = [
                field
                for field in ("count_method", "verified_by", "units")
                if not evidence.get(field)
            ]
            if missing:
                raise HTTPException(
                    422,
                    "inventory proposal evidence requires "
                    + ", ".join(missing),
                )
            if not persona_v2.inventory_v2_available():
                raise HTTPException(409, "Source-specific correction requires fulfillment policy v2")
            source = value.get("source")
            quantity = value.get("quantity")
            basis = value.get("basis")
            revision = value.get("revision")
            if source not in persona_v2.INVENTORY_SOURCES:
                raise HTTPException(422, "inventory source must be wms, erp, or vision")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                raise HTTPException(422, "inventory quantity must be a non-negative integer")
            if basis not in {"free", "total", "total_on_hand"}:
                raise HTTPException(422, "inventory basis must be free or total")
            # Workspace language is `total`; fulfillment's authoritative seam
            # calls this `total_on_hand`.  It includes reserved and picked
            # units still onsite, which are subtracted exactly once there.
            basis = "total_on_hand" if basis == "total" else basis
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                raise HTTPException(422, "inventory revision must be a non-negative integer")
            sku, _, entity_location = row["entity_id"].partition("@")
            location = value.get("location") or entity_location or None
            current = persona_v2.inventory_context(db, row["warehouse_id"], sku, location)
            if revision != int(current.get("revision") or 0):
                raise HTTPException(409, "Inventory correction revision is stale")
            return {
                "type": "inventory_source_correction",
                "source": source,
                "quantity": quantity,
                "basis": basis,
                "revision": revision,
                "sku": sku,
                "location": location,
                "inventory_row_id": current.get("inventory_row_id"),
                "before": current,
                "evidence": evidence,
            }
        if kind == "replenishment_alert":
            raise HTTPException(422, "replenishment requires a source-specific value object")
        if persona_v2.inventory_v2_available():
            raise HTTPException(
                422,
                "Scalar physical_qty corrections are read-only legacy history under "
                "inventory policy v2; propose source, quantity, basis, revision, "
                "and location instead",
            )
        physical_qty = value.get("physical_qty") if isinstance(value, dict) else value
        if isinstance(physical_qty, bool) or not isinstance(physical_qty, (int, float)) or physical_qty < 0:
            raise HTTPException(422, "inventory proposal value must be a non-negative physical_qty")
        return {
            "type": "inventory_overlay",
            "physical_qty": physical_qty,
            "evidence": evidence,
            "source_unchanged": True,
        }
    if kind == "priority_override":
        if value not in {"standard", "high", "urgent"}:
            raise HTTPException(422, "priority proposal value must be standard, high, or urgent")
        order = db.execute(
            "SELECT id,status,priority,warehouse_id FROM orders WHERE id=?", (row["entity_id"],)
        ).fetchone()
        if not order or order["status"] not in {"held", "planned", "queued"}:
            raise HTTPException(409, "Priority override targets only an existing held, planned, or queued POC order")
        impacted = [
            dict(item)
            for item in db.execute(
                "SELECT id,priority,status,ship_by FROM orders "
                "WHERE warehouse_id=? AND status IN ('held','planned','queued') "
                "ORDER BY datetime(ship_by),id",
                (order["warehouse_id"],),
            )
        ]
        return {
            "type": "priority_override",
            "value": value,
            "target_order_id": order["id"],
            "previous_priority": order["priority"],
            "impacted_order_queue": impacted,
            "source_unchanged": True,
        }
    if kind in {"fleet_readiness", "control_asset_readiness"}:
        if isinstance(value, dict):
            missing = [
                field
                for field in ("source", "verified_by")
                if not evidence.get(field)
            ]
            if missing:
                raise HTTPException(
                    422, "fleet proposal evidence requires " + ", ".join(missing)
                )
            return persona_v2.validate_fleet_value(db, row["entity_id"], value)
        if kind == "control_asset_readiness":
            raise HTTPException(422, "control asset correction requires a source-specific value object")
        if value not in {"hold", "release"}:
            raise HTTPException(422, "fleet readiness proposal value must be hold or release")
        robot = next(
            (item for item in fulfillment.source_rows("robots") if item.get("robot_id") == row["entity_id"]),
            None,
        )
        if not robot:
            raise HTTPException(409, "Fleet readiness target is not a known robot")
        return {
            "type": "safety_hold",
            "value": value,
            "robot_id": row["entity_id"],
            "warehouse_id": row["warehouse_id"],
            "source_safety_validation_required": value == "release",
        }
    if kind == "resource_failure":
        task = _task_for_resource(db, row["entity_id"])
        existing_pause = (
            db.execute(
                """SELECT task_id,resource_id FROM persona_task_pauses
                   WHERE intervention_id=?""",
                (row["id"],),
            ).fetchone()
            if task
            else None
        )
        eligible = task and (
            task["status"] == "running"
            or (
                task["status"] == "paused"
                and existing_pause
                and existing_pause["task_id"] == task["id"]
            )
        )
        if not eligible:
            raise HTTPException(409, "Resource failure targets an existing running POC task or resource")
        failed_resource = (
            existing_pause["resource_id"]
            if existing_pause
            else task["resource_id"] if row["entity_id"] == task["id"] else row["entity_id"]
        )
        if not failed_resource:
            raise HTTPException(409, "Running task has no failed resource claim")
        assigned = payload.assigned_to.strip() if isinstance(payload.assigned_to, str) else ""
        if assigned:
            _recovery_resource(db, task, assigned, failed_resource)
        return {
            "type": "pause_task",
            "task_id": task["id"],
            "resource_id": failed_resource,
            "assigned_to": assigned or None,
            "remaining_seconds": 45,
            "source_unchanged": True,
        }
    # A task conflict never replays a task or consumes stock.
    return {
        "type": "record_verified_outcome",
        "task_id": row["entity_id"],
        "source_discrepancy_decision": value or "verified_physical_outcome",
        "source_unchanged": True,
        "replay": False,
        "stock_consumption": False,
    }


def _apply_approval(
    db: sqlite3.Connection, row: sqlite3.Row, proposed: dict[str, Any], intervention_id: str
) -> None:
    kind = row["kind"]
    if kind in persona_v2.INVENTORY_KINDS:
        if proposed.get("type") == "inventory_source_correction":
            corrected = persona_v2.apply_inventory(db, row, proposed, intervention_id)
            proposed["after"] = corrected
            return
        sku = row["entity_id"].split("@", 1)[0]
        requested_qty = float(proposed["physical_qty"])
        active = db.execute(
            "SELECT orders.id,orders.status,SUM(reservations.quantity-reservations.consumed_qty) AS remaining "
            "FROM reservations JOIN orders ON orders.id=reservations.order_id "
            "WHERE reservations.warehouse_id=? AND reservations.sku=? "
            "AND reservations.status='active' "
            "GROUP BY orders.id,orders.status",
            (row["warehouse_id"], sku),
        ).fetchall()
        reserved = sum(max(0, int(item["remaining"] or 0)) for item in active)
        if requested_qty < reserved:
            raise HTTPException(
                409,
                "Inventory correction is below active POC reservations; invalidate affected "
                "planned/queued/running/paused orders before approving",
            )
        db.execute(
            "INSERT INTO persona_inventory_overlays(warehouse_id,sku,physical_qty,intervention_id,created_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(warehouse_id,sku) DO UPDATE SET physical_qty=excluded.physical_qty,"
            "intervention_id=excluded.intervention_id,created_at=excluded.created_at",
            (
                row["warehouse_id"],
                sku,
                requested_qty,
                intervention_id,
                fulfillment.iso(fulfillment.utc_now()),
            ),
        )
        # The overlay is consulted by the fulfillment ATP seam only; source
        # CSV values and source row metadata remain unchanged.
        fulfillment.source_stock_index.cache_clear()
    elif kind == "priority_override":
        target = proposed["target_order_id"]
        current = db.execute("SELECT status FROM orders WHERE id=?", (target,)).fetchone()
        if not current or current["status"] not in {"held", "planned", "queued"}:
            raise HTTPException(409, "Order is no longer eligible for a priority override")
        db.execute("UPDATE orders SET priority=? WHERE id=?", (proposed["value"], target))
        fulfillment._append_event(db, target, f"POC intervention approved priority override to {proposed['value']}")
    elif kind in {"fleet_readiness", "control_asset_readiness"}:
        if proposed.get("type") == "fleet_source_correction":
            persona_v2.apply_fleet(
                db,
                proposed,
                intervention_id,
                fulfillment.iso(fulfillment.utc_now()),
            )
            # Force source-based detection to inspect the new effective row.
            db.execute("DELETE FROM persona_detection_state WHERE id=1")
            return
        if proposed["value"] == "hold":
            db.execute(
                "INSERT INTO persona_safety_holds(robot_id,warehouse_id,reason,intervention_id,created_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(robot_id) DO UPDATE SET reason=excluded.reason,"
                "intervention_id=excluded.intervention_id,released_at=NULL",
                (
                    proposed["robot_id"],
                    proposed["warehouse_id"],
                    "Approved durable POC safety hold",
                    intervention_id,
                    fulfillment.iso(fulfillment.utc_now()),
                ),
            )
            _invalidate_for_hold(
                db, proposed["robot_id"], proposed["warehouse_id"], intervention_id
            )
        else:
            robot = next(
                (item for item in fulfillment.source_rows("robots")
                 if item.get("robot_id") == proposed["robot_id"]),
                None,
            )
            if not robot:
                raise HTTPException(409, "Robot no longer exists in source or registered resources")
            # Ignore only the durable hold being released.  Underlying source
            # maintenance/certification/safety checks still run unchanged.
            safe, reasons = _ORIGINAL_ROBOT_ELIGIBILITY(
                robot, fulfillment.maintenance_exclusions(robot.get("warehouse_id", ""))
            )
            if not safe:
                raise HTTPException(409, "Release rejected by current safety validation: " + "; ".join(reasons))
            db.execute(
                "UPDATE persona_safety_holds SET released_at=? WHERE robot_id=? AND released_at IS NULL",
                (fulfillment.iso(fulfillment.utc_now()), proposed["robot_id"]),
            )
    elif kind == "resource_failure":
        task = db.execute("SELECT * FROM tasks WHERE id=?", (proposed["task_id"],)).fetchone()
        existing_pause = db.execute(
            """SELECT task_id,resource_id FROM persona_task_pauses
               WHERE intervention_id=? AND task_id=?""",
            (intervention_id, proposed["task_id"]),
        ).fetchone()
        if not task or (
            task["status"] != "running"
            and not (task["status"] == "paused" and existing_pause)
        ):
            raise HTTPException(409, "Running task is stale; resource failure was not applied")
        if existing_pause:
            # The lifecycle demo command already applied the authoritative
            # pause. Approval here governs only the recovery preference.
            preferred = None
            if proposed.get("assigned_to"):
                preferred = _recovery_resource(
                    db, task, proposed["assigned_to"], existing_pause["resource_id"]
                )
            if preferred is not None:
                _replan_remaining(
                    db, task, existing_pause["resource_id"], preferred
                )
            return
        remaining = 45  # inspection metadata; a newly assigned task always runs 45s.
        if task["due_at"] and task["started_at"]:
            try:
                remaining = max(
                    1,
                    int((fulfillment.parse_utc(task["due_at"]) - fulfillment.utc_now()).total_seconds()),
                )
            except ValueError:
                remaining = 45
        db.execute(
            "INSERT OR REPLACE INTO persona_task_pauses(task_id,remaining_seconds,resource_id,reason,intervention_id,paused_at) "
            "VALUES (?,?,?,?,?,?)",
            (task["id"], remaining, proposed["resource_id"], "Approved mid-task resource failure", intervention_id,
             fulfillment.iso(fulfillment.utc_now())),
        )
        db.execute(
            "INSERT INTO persona_resource_blocks(resource_id,warehouse_id,reason,intervention_id,created_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(resource_id) DO UPDATE SET reason=excluded.reason,"
            "intervention_id=excluded.intervention_id",
            (
                proposed["resource_id"],
                row["warehouse_id"],
                "Approved POC resource failure",
                intervention_id,
                fulfillment.iso(fulfillment.utc_now()),
            ),
        )
        # A failure must stop the current claim even when no replacement is
        # known yet.  Replanning is deferred to verified resume in that case.
        db.execute(
            "UPDATE tasks SET status='paused',due_at=NULL WHERE id=?", (task["id"],)
        )
        preferred = None
        if proposed.get("assigned_to"):
            preferred = _recovery_resource(
                db, task, proposed["assigned_to"], proposed["resource_id"]
            )
        if preferred is not None:
            _replan_remaining(db, task, proposed["resource_id"], preferred)
        db.execute("UPDATE orders SET status='held' WHERE id=?", (task["order_id"],))


def _apply_verify(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    evidence: dict[str, Any],
    reason: str,
) -> None:
    proposed = _object(row["proposed_action_json"])
    if row["kind"] in persona_v2.INVENTORY_KINDS and proposed.get("type") == "inventory_source_correction":
        current = persona_v2.inventory_context(
            db, row["warehouse_id"], proposed["sku"], proposed.get("location")
        )
        current = persona_v2.verify_inventory_observations(
            db, current, evidence, reason
        )
        values = {
            int(current.get("wms_qty") or 0),
            int(current.get("erp_qty") or 0),
            int(current.get("vision_qty") or 0),
        }
        if row["kind"] == "inventory_mismatch" and (
            len(values) > 1 or current.get("opening_discrepancy")
        ):
            raise HTTPException(409, "Inventory discrepancy remains in the effective source values")
        if row["kind"] == "replenishment_alert":
            import demand_forecast
            _, forecasts = demand_forecast.current_thresholds(db)
            forecast = forecasts.get((str(row["warehouse_id"]), str(proposed["sku"])))
            if forecast is None:
                raise HTTPException(409, "No valid replenishment forecast is available")
            threshold = int(forecast["forecast_7d"])
            available = sum(
                max(
                    0,
                    min(
                        int(item.get("wms_qty") or 0),
                        int(item.get("erp_qty") or 0),
                        int(item.get("vision_qty") or 0),
                    ),
                )
                for item in fulfillment.inventory_rows(
                    db, warehouse_id=str(row["warehouse_id"]), sku=str(proposed["sku"])
                )
            )
            if available < threshold:
                raise HTTPException(
                    409, "Warehouse/SKU free availability remains below predicted seven-day demand"
                )
    if row["kind"] in {"fleet_readiness", "control_asset_readiness"}:
        if proposed.get("type") == "fleet_source_correction":
            missing = [
                field
                for field in (
                    "verified_by",
                    "observed_entity_id",
                    "observation_source",
                )
                if not evidence.get(field)
            ]
            if missing:
                raise HTTPException(
                    422,
                    "fleet verification evidence requires " + ", ".join(missing),
                )
            if evidence["observed_entity_id"] != proposed["entity_id"]:
                raise HTTPException(
                    409, "Fleet observation does not identify the corrected source entity"
                )
        ready, reasons = persona_v2.resource_readiness(db, row)
        if not ready:
            raise HTTPException(
                409, "Resource still has effective eligibility blockers: " + "; ".join(reasons)
            )
    if row["kind"] == "resource_failure":
        pause = db.execute(
            "SELECT task_id,resource_id FROM persona_task_pauses WHERE intervention_id=?",
            (row["id"],),
        ).fetchone()
        if pause and evidence.get("resume") is not True:
            raise HTTPException(
                422, "Resource-failure verification requires explicit resume=true"
            )
        if pause:
            task = db.execute(
                "SELECT * FROM tasks WHERE id=?", (pause["task_id"],)
            ).fetchone()
            if task:
                # A failed resource must not silently be reused.  A replacement
                # can be supplied at proposal time or during verified resume.
                replacement = evidence.get("assigned_to")
                if replacement:
                    preferred = _recovery_resource(db, task, replacement, pause["resource_id"])
                    _replan_remaining(db, task, pause["resource_id"], preferred)
                elif not db.execute(
                    "SELECT 1 FROM task_recovery_preferences WHERE task_id=?", (task["id"],)
                ).fetchone():
                    raise HTTPException(
                        409, "Safe resume requires a replacement assigned_to resource",
                    )
                db.execute("UPDATE tasks SET status='queued' WHERE id=?", (pause["task_id"],))
                if "sub_order_id" in task.keys() and task["sub_order_id"]:
                    db.execute(
                        "UPDATE sub_orders SET status='queued',hold_reason=NULL WHERE id=?",
                        (task["sub_order_id"],),
                    )
                    fulfillment_v2._update_parent(db, task["order_id"])
                else:
                    db.execute("UPDATE orders SET status='queued' WHERE id=?", (task["order_id"],))
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='lifecycle_demo_failures'"
                ).fetchone():
                    db.execute(
                        """UPDATE lifecycle_demo_failures SET resolved_at=?
                           WHERE task_id=? AND intervention_id=? AND resolved_at IS NULL""",
                        (
                            fulfillment.iso(fulfillment.utc_now()),
                            task["id"],
                            row["id"],
                        ),
                    )
    # Verification records evidence only.  In particular, task conflicts do
    # not invoke executor completion and never consume stock.


def _action(
    role: str, intervention_id: str, payload: InterventionAction, db: sqlite3.Connection
) -> dict[str, Any]:
    row = _fetch(db, intervention_id)
    if role == "admin":
        raise HTTPException(403, "Admin cannot perform operational intervention actions")
    _require_visible(role, row)
    allowed = _allowed_actions(role, row)
    if payload.action not in allowed:
        raise HTTPException(409, f"Invalid or stale transition: {payload.action} is not allowed")
    event_evidence = payload.evidence or {}
    if payload.action == "manual_close":
        comment = payload.reason.strip()
        if not comment:
            raise HTTPException(422, "A manual upstream review/correction comment is required")
        now = fulfillment.iso(fulfillment.utc_now())
        evidence = _object(row["evidence_json"])
        if row["kind"] == "inventory_mismatch":
            inventory_sync, current_state = persona_v2.sync_inventory_mismatch_for_close(
                db, row, comment, intervention_id
            )
            evidence["current_state"] = current_state
            manual_closure = {
                "comment": comment,
                "closed_by": role,
                "at": now,
                "fingerprint": _current_inventory_fingerprint(db, row),
                "inventory_sync": inventory_sync,
            }
            event_evidence = {"inventory_sync": inventory_sync}
        else:
            if evidence.get("alert_scope") == "warehouse_sku":
                current = _current_aggregate_low_stock_evidence(db, row)
                fingerprint = current["condition_fingerprint"]
                current_state = current["current_state"]
                inventory_state = current["inventory_state"]
            else:
                current = _current_location_low_stock_evidence(db, row)
                inventory_state = current["inventory_state"]
                fingerprint = current["condition_fingerprint"]
                current_state = {
                    **(
                        evidence.get("current_state")
                        if isinstance(evidence.get("current_state"), dict)
                        else {}
                    ),
                    "threshold": current["threshold"],
                    "inventory_policy": current["inventory_policy"],
                }
            requested_fingerprint = event_evidence.get("condition_fingerprint")
            if not isinstance(requested_fingerprint, str) or not requested_fingerprint:
                raise HTTPException(
                    422, "Low-stock closure requires a condition_fingerprint"
                )
            if requested_fingerprint != fingerprint:
                raise HTTPException(409, "Low-stock alert condition changed; refresh before closing")
            manual_closure = {
                "comment": comment,
                "closed_by": role,
                "at": now,
                "fingerprint": fingerprint,
                "affected_alert": {
                    "warehouse_id": row["warehouse_id"],
                    "sku": _replenishment_sku(row),
                    **(
                        {}
                        if evidence.get("alert_scope") == "warehouse_sku"
                        else {"location": evidence.get("location")}
                    ),
                },
                "inventory_state": inventory_state,
            }
            event_evidence = {
                "condition_fingerprint": fingerprint,
                "affected_alert": manual_closure["affected_alert"],
                "inventory_state": inventory_state,
            }
        evidence["manual_closure"] = manual_closure
        db.execute(
            "UPDATE persona_interventions SET status='resolved',evidence_json=? WHERE id=?",
            (_json(evidence), intervention_id),
        )
        payload.reason = comment
    elif payload.action == "investigate":
        db.execute(
            "UPDATE persona_interventions SET status='investigating' WHERE id=?", (intervention_id,)
        )
    elif payload.action == "propose":
        proposed = _validate_proposal(db, row, payload)
        db.execute(
            "UPDATE persona_interventions SET status='awaiting_approval',proposed_action_json=? WHERE id=?",
            (_json(proposed), intervention_id),
        )
    elif payload.action == "approve":
        if not row["proposed_action_json"]:
            raise HTTPException(409, "No proposed action is awaiting approval")
        proposed = _object(row["proposed_action_json"])
        _apply_approval(db, row, proposed, intervention_id)
        # Keep the status investigating until a distinct verification action.
        proposed["approved"] = True
        db.execute(
            "UPDATE persona_interventions SET status='investigating',proposed_action_json=? WHERE id=?",
            (_json(proposed), intervention_id),
        )
    elif payload.action == "verify":
        if not payload.evidence:
            raise HTTPException(422, "evidence is required when verifying an intervention")
        proposed = _object(row["proposed_action_json"])
        if row["kind"] in {"inventory_mismatch", "replenishment_alert", "priority_override",
                           "fleet_readiness", "control_asset_readiness", "resource_failure"} \
                and not proposed.get("approved"):
            raise HTTPException(409, "Verification requires a separate approval first")
        _apply_verify(db, row, payload.evidence, payload.reason)
        evidence = _object(row["evidence_json"])
        evidence["verification"] = payload.evidence
        db.execute(
            "UPDATE persona_interventions SET status='resolved',evidence_json=? WHERE id=?",
            (_json(evidence), intervention_id),
        )
    elif payload.action == "handoff":
        next_status = "awaiting_approval" if row["status"] == "awaiting_approval" else "investigating"
        db.execute(
            "UPDATE persona_interventions SET owner='supervisor',status=? WHERE id=?",
            (next_status, intervention_id),
        )
    row = _fetch(db, intervention_id)
    _add_event(db, row, role, payload.action, payload.reason, event_evidence)
    return _intervention_json(db, _fetch(db, intervention_id), role)


def _workspace(
    role: str,
    limit: int = 250,
    offset: int = 0,
    kind: str | None = None,
    status: str | None = None,
    q: str = "",
    section: str | None = None,
) -> dict[str, Any]:
    with _tx() as db:
        _detect_all(db)
        _detect_v2(db)
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        if kind is not None and kind not in KINDS:
            raise HTTPException(422, "Unknown intervention kind filter")
        if status is not None and status not in STATUSES:
            raise HTTPException(422, "Unknown intervention status filter")
        if section == "fleet_reports":
            raise HTTPException(422, "The fleet_reports workspace section is retired")
        if section is not None and section != "discrepancies":
            raise HTTPException(422, "Unknown workspace section filter")
        clauses: list[str] = []
        params: list[Any] = []
        if role != "admin":
            views = POLICY[role]["views"]
            if role == "supervisor":
                fleet_kinds = sorted(persona_v2.FLEET_KINDS)
                clauses.append(
                    "(owner=? OR (kind IN ("
                    + ",".join("?" for _ in fleet_kinds)
                    + ") AND (status='awaiting_approval' OR "
                    "COALESCE(json_extract(proposed_action_json,'$.approved'),0)=1)))"
                )
                params.extend([role, *fleet_kinds])
            else:
                clauses.append("owner=?")
                params.append(role)
            clauses.append(f"kind IN ({','.join('?' for _ in views)})")
            params.extend(views)
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        summary_clauses = list(clauses)
        summary_params = list(params)
        if section == "discrepancies":
            clauses.append("kind<>'replenishment_alert'")
        if status:
            clauses.append("status=?")
            params.append(status)
        query = q.strip()
        if query:
            clauses.append(
                "(instr(lower(title),?)>0 OR instr(lower(description),?)>0 "
                "OR instr(lower(entity_id),?)>0 OR instr(lower(warehouse_id),?)>0)"
            )
            params.extend([query.lower()] * 4)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        intervention_total = int(
            db.execute(
                "SELECT COUNT(*) AS count FROM persona_interventions" + where, params
            ).fetchone()["count"]
        )
        rows = db.execute(
            "SELECT * FROM persona_interventions"
            + where
            + " ORDER BY created_at,id LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()

        issue_clauses = [*clauses, "status<>'resolved'"]
        issue_params = list(params)
        if role == "fleet":
            fleet_kinds = sorted(persona_v2.FLEET_KINDS)
            issue_clauses.append(
                f"kind IN ({','.join('?' for _ in fleet_kinds)})"
            )
            issue_params.extend(fleet_kinds)
        issue_where = " WHERE " + " AND ".join(issue_clauses)
        issue_total = int(
            db.execute(
                "SELECT COUNT(*) AS count FROM persona_interventions" + issue_where,
                issue_params,
            ).fetchone()["count"]
        )
        issue_rows = db.execute(
            "SELECT * FROM persona_interventions"
            + issue_where
            + " ORDER BY CASE WHEN "
            "COALESCE(json_array_length(json_extract(evidence_json,'$.linked_work')),0)>0 "
            "THEN 0 ELSE 1 END,created_at,id LIMIT ? OFFSET ?",
            (*issue_params, limit, offset),
        ).fetchall()

        page_ids = {row["id"] for row in [*rows, *issue_rows]}
        events_by_id: dict[str, list[dict[str, Any]]] = {
            item_id: [] for item_id in page_ids
        }
        if page_ids:
            placeholders = ",".join("?" for _ in page_ids)
            for event in db.execute(
                "SELECT intervention_id,at,persona,action,reason,details_json "
                f"FROM persona_intervention_events WHERE intervention_id IN ({placeholders}) "
                "ORDER BY id",
                tuple(page_ids),
            ):
                events_by_id[event["intervention_id"]].append(_event_json(event))
        serialized = {
            row["id"]: _intervention_json(db, row, role, events_by_id)
            for row in [*rows, *issue_rows]
        }
        interventions = [serialized[row["id"]] for row in rows]
        issues = [serialized[row["id"]] for row in issue_rows]

        # Summary remains global to the selected role/kind; a status filter
        # or text query narrows rows but does not make the status cards
        # self-referential.
        count_where = (
            " WHERE " + " AND ".join(summary_clauses) if summary_clauses else ""
        )
        all_counts = {
            row["status"]: int(row["count"])
            for row in db.execute(
                "SELECT status,COUNT(*) AS count FROM persona_interventions"
                + count_where
                + " GROUP BY status",
                summary_params,
            )
        }
        counts = {status: 0 for status in ("open", "awaiting_approval", "resolved")}
        counts.update({key: value for key, value in all_counts.items() if key in counts})
        return {
            "persona": role,
            "summary": {
                "open": counts["open"],
                "awaiting_approval": counts["awaiting_approval"],
                "resolved": counts["resolved"],
            },
            "interventions": interventions,
            "issues": issues,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "intervention_total": intervention_total,
                "issue_total": issue_total,
            },
            "capabilities": POLICY[role]["actions"],
            "correction_capabilities": persona_v2.correction_capabilities(role),
            "assumptions": ASSUMPTIONS,
        }


def _sync_fleet_issues(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    specs = {spec["dedupe_key"]: spec for spec in fleet_repair.issue_specs(db)}
    existing_by_key = {
        row["dedupe_key"]: row
        for row in db.execute(
            "SELECT * FROM persona_interventions WHERE "
            "dedupe_key LIKE 'fleet_readiness:%' "
            "OR dedupe_key LIKE 'v2:control_asset:%'"
        )
    }
    for key, spec in specs.items():
        evidence = {
            "source": (
                "robots+maintenance"
                if spec["kind"] == "fleet_readiness"
                else "control_assets"
            ),
            "unsafe_reasons": spec["blockers"],
            "editable_contexts": spec["contexts"],
            "current_state": {
                item["entity_type"]: item["values"] for item in spec["contexts"]
            },
        }
        # Fleet readiness is re-projected from source conditions, but legacy
        # linked-work evidence is an independent intrinsic priority signal and
        # must not be erased by synchronization.
        existing = existing_by_key.get(key)
        if existing is not None:
            linked_work = _object(existing["evidence_json"]).get("linked_work")
            if linked_work:
                evidence["linked_work"] = linked_work
        _insert_detected(
            db,
            spec["kind"],
            spec["warehouse_id"],
            spec["entity_id"],
            spec["title"],
            "Effective source readiness conditions require repair.",
            evidence,
            key,
            existing_by_key,
        )
    now = fulfillment.iso(fulfillment.utc_now())
    for key, row in existing_by_key.items():
        if key in specs or row["status"] == "resolved":
            continue
        db.execute(
            "UPDATE persona_interventions SET status='resolved',updated_at=? WHERE id=?",
            (now, row["id"]),
        )
        _add_event(
            db,
            row,
            "system",
            "recovered",
            "Fleet source readiness conditions are satisfied",
        )
    return specs


def _fleet_issue_json(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    spec: dict[str, Any] | None = None,
    impacts: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    snapshot = spec or fleet_repair.resource_snapshot(
        db, row["kind"], str(row["entity_id"])
    )
    evidence = _object(row["evidence_json"])
    if snapshot is None:
        snapshot = {
            "kind": row["kind"],
            "entity_id": row["entity_id"],
            "warehouse_id": row["warehouse_id"],
            "blockers": list(evidence.get("unsafe_reasons") or []),
            "contexts": list(evidence.get("editable_contexts") or []),
        }
    projected = {
        **snapshot,
        "title": row["title"],
    }
    impacted_orders = list((impacts or {}).get(str(row["entity_id"]), []))
    intrinsic_p1 = bool(evidence.get("linked_work"))
    dynamic_p1 = bool(impacted_orders) and row["status"] != "resolved"
    if dynamic_p1:
        priority_reason = "Readiness issue blocks active fulfillment work"
    elif intrinsic_p1:
        priority_reason = "Linked work marks this issue as operationally critical"
    else:
        priority_reason = None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "entity_id": row["entity_id"],
        "warehouse_id": row["warehouse_id"],
        "title": row["title"],
        "status": row["status"],
        "priority": "P1" if dynamic_p1 or intrinsic_p1 else "P2",
        "priority_reason": priority_reason,
        "impacted_orders": impacted_orders,
        "blockers": list(snapshot["blockers"]),
        "contexts": list(snapshot["contexts"]),
        "assignment_blockers": fleet_repair.assignment_blockers(
            db, str(row["entity_id"])
        ),
        "events": [
            _event_json(event)
            for event in db.execute(
                "SELECT at,persona,action,reason,details_json "
                "FROM persona_intervention_events WHERE intervention_id=? ORDER BY id",
                (row["id"],),
            )
        ],
        "fingerprint": fleet_repair.fingerprint(projected),
    }


def _fleet_role(role: str, *, repair: bool = False) -> None:
    if repair and role != "fleet":
        raise HTTPException(403, "Only the Fleet persona may repair fleet issues")
    if not repair and role not in {"fleet", "admin"}:
        raise HTTPException(403, "Fleet issues are visible only to Fleet and Admin")


def _fleet_issues(
    role: str, limit: int = 10, offset: int = 0, q: str = ""
) -> dict[str, Any]:
    _fleet_role(role)
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    query = q.strip().lower()
    with _tx() as db:
        specs = _sync_fleet_issues(db)
        impacts = fleet_repair.readiness_impacts(db)
        rows = db.execute(
            "SELECT * FROM persona_interventions WHERE status<>'resolved' "
            "AND kind IN ('fleet_readiness','control_asset_readiness') "
            "AND (dedupe_key LIKE 'fleet_readiness:%' "
            "OR dedupe_key LIKE 'v2:control_asset:%') ORDER BY created_at,id"
        ).fetchall()
        if query:
            rows = [
                row
                for row in rows
                if any(
                    query in str(value or "").lower()
                    for value in (
                        row["title"],
                        row["entity_id"],
                        row["warehouse_id"],
                        row["kind"],
                        " ".join(
                            specs.get(row["dedupe_key"], {}).get("blockers", [])
                        ),
                        " ".join(
                            item["order_id"]
                            for item in impacts.get(str(row["entity_id"]), [])
                        ),
                    )
                )
            ]
        rows = sorted(
            rows,
            key=lambda row: (
                not (
                    bool(impacts.get(str(row["entity_id"])))
                    or bool(_object(row["evidence_json"]).get("linked_work"))
                ),
                row["created_at"],
                row["id"],
            ),
        )
        total = len(rows)
        page = rows[offset : offset + limit]
        return {
            "items": [
                _fleet_issue_json(
                    db, row, specs.get(row["dedupe_key"]), impacts
                )
                for row in page
            ],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }


@router.get("/workspace")
def workspace(
    x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona"),
    limit: int = Query(250, ge=1, le=500),
    offset: int = Query(0, ge=0),
    kind: str | None = Query(None),
    status: str | None = Query(None),
    q: str = Query(""),
    section: str | None = Query(None),
):
    # Preserve direct Python callers used by focused tests.
    direct_limit = limit if isinstance(limit, int) else 250
    direct_offset = offset if isinstance(offset, int) else 0
    direct_kind = kind if isinstance(kind, str) else None
    direct_status = status if isinstance(status, str) else None
    direct_q = q if isinstance(q, str) else ""
    direct_section = section if isinstance(section, str) else None
    return _workspace(
        _role(x_demo_persona),
        direct_limit,
        direct_offset,
        direct_kind,
        direct_status,
        direct_q,
        direct_section,
    )


@router.get("/fleet/issues")
def fleet_issues(
    x_demo_persona: str = Header("fleet", alias="X-Demo-Persona"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query(""),
):
    return _fleet_issues(
        _role(x_demo_persona),
        limit if isinstance(limit, int) else 10,
        offset if isinstance(offset, int) else 0,
        q if isinstance(q, str) else "",
    )


@router.get("/fleet/issues/{issue_id}")
def fleet_issue(
    issue_id: str,
    x_demo_persona: str = Header("fleet", alias="X-Demo-Persona"),
):
    role = _role(x_demo_persona)
    _fleet_role(role)
    with _tx() as db:
        specs = _sync_fleet_issues(db)
        impacts = fleet_repair.readiness_impacts(db)
        row = _fetch(db, issue_id)
        if row["kind"] not in {"fleet_readiness", "control_asset_readiness"}:
            raise HTTPException(404, "Fleet issue not found")
        return _fleet_issue_json(
            db, row, specs.get(row["dedupe_key"]), impacts
        )


@router.post("/fleet/issues/{issue_id}/repair")
def repair_fleet_issue(
    issue_id: str,
    payload: FleetRepairRequest,
    x_demo_persona: str = Header("fleet", alias="X-Demo-Persona"),
):
    role = _role(x_demo_persona)
    _fleet_role(role, repair=True)
    with _tx() as db:
        specs = _sync_fleet_issues(db)
        row = _fetch(db, issue_id)
        spec = specs.get(row["dedupe_key"])
        if (
            row["kind"] not in {"fleet_readiness", "control_asset_readiness"}
            or spec is None
            or row["status"] == "resolved"
        ):
            raise HTTPException(409, "Fleet issue is no longer active")
        current_fingerprint = fleet_repair.fingerprint(spec)
        if payload.fingerprint != current_fingerprint:
            raise HTTPException(
                409, "Fleet issue snapshot is stale; refresh and retry"
            )
        contexts = fleet_repair.validate_snapshot(
            db, spec["contexts"], payload.contexts
        )
        now = fulfillment.iso(fulfillment.utc_now())
        changes = fleet_repair.apply_repairs(
            db, contexts, spec["contexts"], issue_id, now
        )
        _add_event(
            db,
            row,
            role,
            "repaired",
            "Fleet readiness source values repaired",
            {"changes": changes, "fingerprint": current_fingerprint},
        )
        _audit(
            db,
            role,
            "fleet_repair",
            row["entity_id"],
            "Fleet readiness source values repaired",
            {"intervention_id": issue_id, "changes": changes},
        )
        updated_specs = _sync_fleet_issues(db)
        updated = _fetch(db, issue_id)
        impacts = fleet_repair.readiness_impacts(db)
        return _fleet_issue_json(
            db, updated, updated_specs.get(updated["dedupe_key"]), impacts
        )


def _replenishment_sku(row: sqlite3.Row) -> str:
    evidence = _object(row["evidence_json"])
    sku = evidence.get("sku")
    if sku:
        return str(sku)
    return str(row["entity_id"]).split("@", 1)[0]


def _record_low_stock_recovery(
    db: sqlite3.Connection, row: sqlite3.Row, reason: str
) -> None:
    evidence = _object(row["evidence_json"])
    if evidence.get("condition_recovered"):
        return
    now = fulfillment.iso(fulfillment.utc_now())
    affected_alert = {
        "warehouse_id": row["warehouse_id"],
        "sku": _replenishment_sku(row),
    }
    location = evidence.get("location")
    if location:
        affected_alert["location"] = location
    recovery = {
        "at": now,
        "reason": reason,
        "condition_fingerprint": evidence.get("condition_fingerprint"),
        "affected_alert": affected_alert,
    }
    evidence["condition_recovered"] = recovery
    db.execute(
        "UPDATE persona_interventions SET status='resolved',evidence_json=?,"
        "updated_at=? WHERE id=?",
        (_json(evidence), now, row["id"]),
    )
    _add_event(
        db,
        row,
        "system",
        "recovered",
        reason,
        recovery,
    )


def _reconcile_location_low_stock_recovery(
    db: sqlite3.Connection, detected_keys: set[str]
) -> None:
    for row in db.execute(
        "SELECT * FROM persona_interventions "
        "WHERE kind='replenishment_alert' "
        "AND dedupe_key LIKE 'v2:replenishment:%'"
    ).fetchall():
        if row["dedupe_key"] not in detected_keys:
            _record_low_stock_recovery(
                db, row, "Location low-stock condition is no longer active"
            )


def _reconcile_aggregate_low_stock_recovery(
    db: sqlite3.Connection, active_keys: set[tuple[str, str]]
) -> None:
    for row in db.execute(
        "SELECT * FROM persona_interventions "
        "WHERE kind='replenishment_alert' "
        "AND dedupe_key LIKE 'low_stock_aggregate:%'"
    ).fetchall():
        key = (str(row["warehouse_id"]), _replenishment_sku(row))
        if key in active_keys:
            continue
        _record_low_stock_recovery(
            db,
            row,
            "Low-stock condition is no longer active",
        )


def _low_stock(
    role: str,
    limit: int = 10,
    offset: int = 0,
    q: str = "",
    status: str = "active",
) -> dict[str, Any]:
    if role == "fleet":
        raise HTTPException(403, "Low-stock workspace is supervisor/admin-only")
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    query = q.strip().lower()
    if status not in {"active", "closed"}:
        raise HTTPException(422, "Low-stock status must be active or closed")
    with _tx() as db:
        _detect_all(db)
        _detect_v2(db)
        import demand_forecast
        if demand_forecast.latest_run(db) is None:
            raise HTTPException(
                503,
                "Low-stock workspace unavailable: no valid demand forecast run",
            )
        alerts = [dict(alert) for alert in fulfillment.stock_alerts(db)]
        active_keys = {
            (str(alert["warehouse_id"]), str(alert["sku"])) for alert in alerts
        }
        _reconcile_aggregate_low_stock_recovery(db, active_keys)
        inventory_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        if persona_v2.inventory_v2_available():
            for source in fulfillment.inventory_rows(db):
                item = dict(source)
                inventory_by_key.setdefault(
                    (str(item.get("warehouse_id") or ""), str(item.get("sku") or "")),
                    [],
                ).append(item)
        held_by_sku = persona_v2.held_work_index(db)
        existing_by_key = {
            row["dedupe_key"]: row
            for row in db.execute(
                "SELECT * FROM persona_interventions "
                "WHERE dedupe_key LIKE 'low_stock_aggregate:%'"
            )
        }
        alert_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for alert in alerts:
            warehouse_id = str(alert["warehouse_id"])
            sku = str(alert["sku"])
            alert_by_key[(warehouse_id, sku)] = alert
            aggregate_evidence = _aggregate_low_stock_evidence(
                db, alert, inventory_by_key, held_by_sku
            )
            _insert_detected(
                db,
                "replenishment_alert",
                warehouse_id,
                sku,
                f"Low stock alert: {sku} at {warehouse_id}",
                "Warehouse/SKU free availability is below predicted seven-day demand.",
                aggregate_evidence,
                f"low_stock_aggregate:{warehouse_id}:{sku}",
                existing_by_key,
            )
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        status_clause = "='resolved'" if status == "closed" else "<>'resolved'"
        rows = db.execute(
            "SELECT * FROM persona_interventions "
            f"WHERE kind='replenishment_alert' AND status{status_clause} "
            "ORDER BY created_at,id"
        ).fetchall()
        for row in rows:
            if not _visible(role, row):
                continue
            warehouse_id = str(row["warehouse_id"])
            sku = _replenishment_sku(row)
            key = (warehouse_id, sku)
            group = groups.setdefault(
                key,
                {
                    "id": f"{warehouse_id}:{sku}",
                    "warehouse_id": warehouse_id,
                    "sku": sku,
                    "aggregate_alert": {
                        field: alert_by_key[key][field]
                        for field in (
                            "available",
                            "threshold",
                            "inventory_policy",
                            "forecast_7d",
                            "forecast_30d",
                            "forecast_date",
                            "history_days",
                            "history_status",
                            "forecast_method",
                        )
                        if key in alert_by_key and field in alert_by_key[key]
                    } if key in alert_by_key else None,
                    "alert": None,
                    "rows": [],
                    "priority": "P2",
                    "search": [warehouse_id, sku],
                },
            )
            evidence = _object(row["evidence_json"])
            if evidence.get("alert_scope") == "warehouse_sku":
                group["alert"] = row
            else:
                group["rows"].append(row)
            group["search"].extend(
                [
                    str(row["title"]),
                    str(row["entity_id"]),
                    str(evidence.get("location") or ""),
                ]
            )
            if evidence.get("linked_work"):
                group["priority"] = "P1"

        matching = [
            group
            for group in groups.values()
            if not query
            or any(query in candidate.lower() for candidate in group["search"])
        ]
        matching.sort(key=lambda group: (group["priority"] != "P1", group["id"]))
        total = len(matching)
        page = matching[offset : offset + limit]
        page_rows = [
            row
            for group in page
            for row in [group["alert"], *group["rows"]]
            if row is not None
        ]
        page_ids = [row["id"] for row in page_rows]
        events_by_id: dict[str, list[dict[str, Any]]] = {
            intervention_id: [] for intervention_id in page_ids
        }
        if page_ids:
            placeholders = ",".join("?" for _ in page_ids)
            for event in db.execute(
                "SELECT intervention_id,at,persona,action,reason,details_json "
                f"FROM persona_intervention_events WHERE intervention_id IN ({placeholders}) "
                "ORDER BY id",
                page_ids,
            ):
                events_by_id[event["intervention_id"]].append(_event_json(event))
        items = [
            {
                "id": group["id"],
                "warehouse_id": group["warehouse_id"],
                "sku": group["sku"],
                "aggregate_alert": group["aggregate_alert"],
                "alert": (
                    _intervention_json(db, group["alert"], role, events_by_id)
                    if group["alert"] is not None
                    else None
                ),
                "interventions": [
                    _intervention_json(db, row, role, events_by_id)
                    for row in group["rows"]
                ],
                "priority": group["priority"],
            }
            for group in page
        ]
        return {
            "items": items,
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }


@router.get("/low-stock")
def low_stock(
    x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona"),
    limit: int = Query(10, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str = Query(""),
    status: str = Query("active"),
):
    return _low_stock(
        _role(x_demo_persona),
        limit if isinstance(limit, int) else 10,
        offset if isinstance(offset, int) else 0,
        q if isinstance(q, str) else "",
        status if isinstance(status, str) else "active",
    )


@router.get("/interventions/{intervention_id}")
def get_intervention(
    intervention_id: str, x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")
):
    role = _role(x_demo_persona)
    with _read_tx() as db:
        row = _fetch(db, intervention_id)
        _require_visible(role, row)
        return _intervention_json(db, row, role)


@router.post("/interventions")
def create_intervention(
    payload: InterventionCreate,
    x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona"),
):
    role = _role(x_demo_persona)
    with _tx() as db:
        return _new_intervention(role, payload, db)


@router.post("/interventions/{intervention_id}/actions")
def intervention_action(
    intervention_id: str,
    payload: InterventionAction,
    x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona"),
):
    role = _role(x_demo_persona)
    with _tx() as db:
        return _action(role, intervention_id, payload, db)


@router.get("/audit")
def audit(x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")):
    if _role(x_demo_persona) != "admin":
        raise HTTPException(403, "Audit is admin-only")
    with _read_tx() as db:
        return {
            "events": [
                {
                    "id": row["id"],
                    "at": row["at"],
                    "persona": row["persona"],
                    "action": row["action"],
                    "entity_id": row["entity_id"],
                    "reason": row["reason"],
                    "details": _object(row["details_json"]),
                }
                for row in db.execute(
                    "SELECT id,at,persona,action,entity_id,reason,details_json "
                    "FROM persona_audit_events ORDER BY id"
                )
            ]
        }


@router.get("/policy")
def policy(x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")):
    if _role(x_demo_persona) != "admin":
        raise HTTPException(403, "Policy is admin-only")
    return {
        "roles": [
            {"id": key, "label": value["label"], "views": value["views"], "actions": value["actions"]}
            for key, value in POLICY.items()
        ]
    }


REGISTERABLE = {"warehouses", "skus", "robots", "control_assets"}
IDENTITY_FIELDS = {
    "warehouses": "warehouse_id",
    "skus": "sku",
    "robots": "robot_id",
    "control_assets": "asset_id",
}


class ResourceRegistration(BaseModel):
    values: dict[str, Any]


@router.post("/resources/{dataset}")
def register_resource(
    dataset: str,
    payload: ResourceRegistration,
    x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona"),
):
    if _role(x_demo_persona) != "admin":
        raise HTTPException(403, "Resource registration is admin-only")
    if dataset not in REGISTERABLE:
        raise HTTPException(422, "Only warehouses, skus, robots, and control_assets may be registered")
    _ensure_schema()
    with _tx() as db:
        if db.execute(
            "SELECT COUNT(*) FROM orders WHERE status IN ('planned','queued','running')"
        ).fetchone()[0]:
            raise HTTPException(409, "Resource registration is blocked while an active POC plan exists")
        fields = set(fulfillment.source_fields(dataset))
        unknown = set(payload.values) - fields
        if unknown:
            raise HTTPException(422, f"Unknown source field(s): {', '.join(sorted(unknown))}")
        identity = IDENTITY_FIELDS[dataset]
        value = payload.values.get(identity)
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(422, f"values.{identity} is required")
        normalized_identity = value.strip()
        existing = {
            str(row.get(identity, "")).strip() for row in fulfillment.source_rows(dataset)
        }
        if normalized_identity in existing:
            raise HTTPException(409, f"{identity} already exists")
        warehouse = payload.values.get("warehouse_id")
        normalized_warehouse = warehouse.strip() if isinstance(warehouse, str) else warehouse
        if dataset in {"robots", "control_assets"}:
            known = {
                str(row.get("warehouse_id", "")).strip()
                for row in fulfillment.source_rows("warehouses")
            }
            if normalized_warehouse not in known:
                raise HTTPException(422, f"Unknown warehouse_id {warehouse}")
        values = {field: payload.values.get(field, "") for field in fields}
        values[identity] = normalized_identity
        if "warehouse_id" in values and isinstance(values["warehouse_id"], str):
            values["warehouse_id"] = normalized_warehouse
        row_id = f"REG-{uuid.uuid4()}"
        db.execute(
            "INSERT INTO registered_resources(dataset,row_id,values_json,registered_at) VALUES (?,?,?,?)",
            (dataset, row_id, _json(values), fulfillment.iso(fulfillment.utc_now())),
        )
        fulfillment._raw_source_rows.cache_clear()
        fulfillment.source_stock_index.cache_clear()
        _audit(db, "admin", "register_resource", row_id, "Admin registered a POC resource", {
            "dataset": dataset, "identity": normalized_identity,
        })
        return {"dataset": dataset, "row_id": row_id, "values": values, "registered": True}


_ensure_schema()