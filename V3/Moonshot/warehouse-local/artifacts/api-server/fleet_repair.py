"""Focused fleet issue projection and atomic source repair helpers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Iterable

from fastapi import HTTPException

import fleet_readiness
import fulfillment_api as fulfillment
import fulfillment_v2
import persona_v2


READINESS_FIELDS = {
    "robot": ("health_status", "safety_cert_status", "connectivity"),
    "maintenance": ("cmms_status", "fleet_availability"),
    "control_asset": ("state", "maintenance_state"),
}
DATASETS = {
    "robot": "robots",
    "maintenance": "maintenance",
    "control_asset": "control_assets",
}
IDENTITIES = {
    "robot": "robot_id",
    "maintenance": "work_order_id",
    "control_asset": "asset_id",
}


def allowed_values(entity_type: str) -> dict[str, list[str]]:
    return {
        field: sorted(persona_v2.FIELD_VALUES[field])
        for field in READINESS_FIELDS[entity_type]
    }


def missing_maintenance_id(robot_id: str) -> str:
    return f"MAINT-{robot_id}"


def _registration_count(db: sqlite3.Connection) -> int:
    return int(
        db.execute("SELECT COUNT(*) FROM registered_resources").fetchone()[0]
    )


def context_revision(
    db: sqlite3.Connection, entity_type: str, entity_id: str
) -> int:
    """Revision includes overlays and membership, not just corrected fields."""

    dataset = DATASETS[entity_type]
    source = persona_v2.source_revision(db, dataset, entity_id)
    scenario = int(fulfillment._scenario_revision(db))
    registrations = _registration_count(db)
    # Integers are convenient for clients while the hash makes unrelated
    # scenario/membership changes conservatively stale rather than unsafe.
    token = f"{scenario}:{registrations}:{source}".encode()
    # Six bytes stay exactly representable by JavaScript's Number.
    return int.from_bytes(hashlib.sha256(token).digest()[:6], "big")


def _context(
    db: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    row: dict[str, Any] | None,
    *,
    missing: bool = False,
) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "revision": context_revision(db, entity_type, entity_id),
        "values": {
            field: (row.get(field) if row is not None else None)
            for field in READINESS_FIELDS[entity_type]
        },
        "allowed_values": allowed_values(entity_type),
        **({"missing": True} if missing else {}),
    }


def fingerprint(spec: dict[str, Any]) -> str:
    snapshot = {
        "kind": spec["kind"],
        "entity_id": spec["entity_id"],
        "warehouse_id": spec["warehouse_id"],
        "blockers": spec["blockers"],
        "contexts": [
            {
                "entity_type": item["entity_type"],
                "entity_id": item["entity_id"],
                "revision": item["revision"],
                "values": item["values"],
                "missing": bool(item.get("missing")),
            }
            for item in spec["contexts"]
        ],
    }
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def resource_snapshot(
    db: sqlite3.Connection, kind: str, entity_id: str
) -> dict[str, Any] | None:
    if kind == "control_asset_readiness":
        asset = next(
            (
                row
                for row in fulfillment.source_rows("control_assets")
                if str(row.get("asset_id") or "") == entity_id
            ),
            None,
        )
        if asset is None:
            return None
        _, blockers = fleet_readiness.asset_readiness(asset)
        return {
            "kind": kind,
            "entity_id": entity_id,
            "warehouse_id": str(asset.get("warehouse_id") or "unknown"),
            "blockers": blockers,
            "contexts": [_context(db, "control_asset", entity_id, asset)],
        }
    robot = next(
        (
            row
            for row in fulfillment.source_rows("robots")
            if str(row.get("robot_id") or "") == entity_id
        ),
        None,
    )
    if robot is None:
        return None
    maintenance = tuple(fulfillment.source_rows("maintenance"))
    _, blockers = fleet_readiness.robot_readiness(robot, maintenance)
    linked = sorted(
        (
            row
            for row in maintenance
            if str(row.get("robot_id") or "") == entity_id
        ),
        key=lambda row: str(row.get("work_order_id") or ""),
    )
    contexts = [_context(db, "robot", entity_id, robot)]
    if linked:
        contexts.extend(
            _context(db, "maintenance", str(row.get("work_order_id")), row)
            for row in linked
            if row.get("work_order_id")
        )
    else:
        contexts.append(
            _context(
                db,
                "maintenance",
                missing_maintenance_id(entity_id),
                None,
                missing=True,
            )
        )
    return {
        "kind": kind,
        "entity_id": entity_id,
        "warehouse_id": str(robot.get("warehouse_id") or "unknown"),
        "blockers": blockers,
        "contexts": contexts,
    }


def issue_specs(db: sqlite3.Connection) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for robot in fulfillment.source_rows("robots"):
        robot_id = str(robot.get("robot_id") or "")
        if not robot_id:
            continue
        snapshot = resource_snapshot(db, "fleet_readiness", robot_id)
        if snapshot is None or (
            not snapshot["blockers"] and not assignment_blockers(db, robot_id)
        ):
            continue
        specs.append(
            {
                **snapshot,
                "dedupe_key": f"fleet_readiness:{robot.get('warehouse_id')}:{robot_id}",
                "title": f"Fleet readiness: {robot_id}",
            }
        )
    for asset in fulfillment.source_rows("control_assets"):
        asset_id = str(asset.get("asset_id") or "")
        if not asset_id:
            continue
        snapshot = resource_snapshot(db, "control_asset_readiness", asset_id)
        if snapshot is None or (
            not snapshot["blockers"] and not assignment_blockers(db, asset_id)
        ):
            continue
        warehouse_id = str(asset.get("warehouse_id") or "unknown")
        specs.append(
            {
                **snapshot,
                "dedupe_key": f"v2:control_asset:{warehouse_id}:{asset_id}",
                "title": f"Control asset readiness: {asset_id}",
            }
        )
    return specs


def readiness_impacts(
    db: sqlite3.Connection,
) -> dict[str, list[dict[str, Any]]]:
    """Bulk-project active work blocked by each readiness context.

    Assigned queued/paused work belongs only to its actual owner.  An
    unassigned queued task can be blocked by every statically compatible
    resource; source readiness itself is intentionally not part of that
    compatibility check because the resource's readiness issue is the thing
    being projected.
    """

    impacts: dict[str, dict[str, set[str]]] = {}

    def add(resource_id: str, order_id: str, task_id: str) -> None:
        if not resource_id:
            return
        impacts.setdefault(resource_id, {}).setdefault(order_id, set()).add(task_id)

    tasks = db.execute(
        """
        SELECT t.id AS task_id,t.order_id,t.stage,t.status,t.resource_id,
               t.resource_type,t.payload_kg,
               COALESCE(s.warehouse_id,o.warehouse_id) AS warehouse_id
          FROM tasks t
          JOIN orders o ON o.id=t.order_id
          LEFT JOIN sub_orders s ON s.id=t.sub_order_id
         WHERE t.status IN ('queued','paused')
           AND o.status NOT IN ('held','completed','cancelled','recovery_required')
           AND (t.sub_order_id IS NULL OR (
                 s.id IS NOT NULL
             AND s.status NOT IN ('held','completed','cancelled','recovery_required')
           ))
        """
    ).fetchall()
    robots = tuple(fulfillment.source_rows("robots"))
    assets = tuple(fulfillment.source_rows("control_assets"))

    for task in tasks:
        task_id = str(task["task_id"])
        order_id = str(task["order_id"])
        owner = str(task["resource_id"] or "").strip()
        if owner:
            add(owner, order_id, task_id)
            continue
        # Paused work without an owner does not identify a resource whose
        # readiness is blocking it.
        if task["status"] != "queued":
            continue
        warehouse_id = str(task["warehouse_id"] or "")
        stage = str(task["stage"] or "")
        payload = fulfillment_v2._f(task["payload_kg"])
        if stage in fulfillment_v2.ROBOT_TYPES:
            for robot in robots:
                if (
                    str(robot.get("warehouse_id") or "") == warehouse_id
                    and robot.get("robot_type") in fulfillment_v2.ROBOT_TYPES[stage]
                    and fulfillment_v2._f(robot.get("payload_kg")) >= payload
                ):
                    add(str(robot.get("robot_id") or ""), order_id, task_id)
        elif stage in fulfillment_v2.ASSET_TYPES:
            for asset in assets:
                if (
                    str(asset.get("warehouse_id") or "") == warehouse_id
                    and asset.get("asset_type") in fulfillment_v2.ASSET_TYPES[stage]
                ):
                    add(str(asset.get("asset_id") or ""), order_id, task_id)

    return {
        resource_id: [
            {"order_id": order_id, "task_ids": sorted(task_ids)}
            for order_id, task_ids in sorted(orders.items())
        ]
        for resource_id, orders in impacts.items()
    }


def assignment_blockers(
    db: sqlite3.Connection, entity_id: str
) -> list[str]:
    blockers: list[str] = []
    hold = db.execute(
        "SELECT reason FROM persona_safety_holds "
        "WHERE robot_id=? AND released_at IS NULL",
        (entity_id,),
    ).fetchone()
    if hold:
        blockers.append(f"Explicit safety hold: {hold['reason']}")
    block = db.execute(
        "SELECT reason FROM persona_resource_blocks WHERE resource_id=?",
        (entity_id,),
    ).fetchone()
    if block:
        blockers.append(f"Explicit resource block: {block['reason']}")
    try:
        simulator = db.execute(
            """SELECT reason FROM lifecycle_failed_resources
               WHERE resource_id=? AND recovered_at IS NULL""",
            (entity_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        simulator = None
    if simulator:
        blockers.append(f"Simulator failure block: {simulator['reason']}")
    return blockers


def validate_snapshot(
    db: sqlite3.Connection,
    expected: list[dict[str, Any]],
    submitted: Iterable[Any],
) -> list[dict[str, Any]]:
    supplied: list[dict[str, Any]] = []
    for raw in submitted:
        item = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        supplied.append(item)
    expected_keys = {
        (item["entity_type"], item["entity_id"]): item for item in expected
    }
    supplied_keys = {
        (str(item.get("entity_type")), str(item.get("entity_id"))): item
        for item in supplied
    }
    if len(supplied_keys) != len(supplied) or set(expected_keys) != set(supplied_keys):
        raise HTTPException(
            409, "Fleet issue membership changed; refresh the complete issue and retry"
        )
    for key, current in expected_keys.items():
        item = supplied_keys[key]
        if item.get("revision") != current["revision"]:
            raise HTTPException(
                409, f"Fleet context {key[1]} is stale; refresh and retry"
            )
        values = item.get("values")
        if not isinstance(values, dict):
            raise HTTPException(422, f"Fleet context {key[1]} values must be an object")
        if not values:
            continue
        unknown = set(values) - set(READINESS_FIELDS[key[0]])
        if unknown:
            raise HTTPException(
                422, f"Fields are not editable for {key[0]}: {', '.join(sorted(unknown))}"
            )
        if current.get("missing") and set(values) != set(READINESS_FIELDS["maintenance"]):
            raise HTTPException(
                422, "A missing maintenance record requires both readiness fields"
            )
        for field, value in values.items():
            if value is None or not isinstance(value, str) or not value.strip():
                raise HTTPException(422, f"{field} must be a non-empty source value")
            normalized = value.strip().upper()
            if normalized not in persona_v2.FIELD_VALUES[field]:
                raise HTTPException(
                    422,
                    f"{field} must be one of "
                    + ", ".join(sorted(persona_v2.FIELD_VALUES[field])),
                )
            values[field] = normalized
    return supplied


def apply_repairs(
    db: sqlite3.Connection,
    contexts: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    intervention_id: str,
    now: str,
) -> list[dict[str, Any]]:
    before_by_key = {
        (item["entity_type"], item["entity_id"]): item["values"] for item in expected
    }
    changes: list[dict[str, Any]] = []
    for context in contexts:
        if not context["values"]:
            continue
        entity_type = context["entity_type"]
        entity_id = context["entity_id"]
        dataset = DATASETS[entity_type]
        if entity_type == "maintenance" and next(
            item for item in expected
            if item["entity_type"] == entity_type and item["entity_id"] == entity_id
        ).get("missing"):
            robot_id = entity_id.removeprefix("MAINT-")
            robot = next(
                (
                    row
                    for row in fulfillment.source_rows("robots")
                    if str(row.get("robot_id") or "") == robot_id
                ),
                None,
            )
            if robot is None:
                raise HTTPException(
                    409, "Robot for missing maintenance record no longer exists"
                )
            row = {
                "work_order_id": entity_id,
                "robot_id": robot_id,
                "warehouse_id": robot.get("warehouse_id"),
                **context["values"],
            }
            db.execute(
                "INSERT INTO registered_resources(dataset,row_id,values_json,registered_at) "
                "VALUES ('maintenance',?,?,?)",
                (entity_id, json.dumps(row, sort_keys=True), now),
            )
        current_revision = persona_v2.source_revision(db, dataset, entity_id)
        next_revision = current_revision + 1
        for field, value in context["values"].items():
            before = before_by_key[(entity_type, entity_id)].get(field)
            if before == value:
                continue
            db.execute(
                "INSERT INTO persona_source_corrections"
                "(dataset,entity_id,field,value_json,revision,intervention_id,updated_at) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(dataset,entity_id,field) DO UPDATE SET "
                "value_json=excluded.value_json,revision=excluded.revision,"
                "intervention_id=excluded.intervention_id,updated_at=excluded.updated_at",
                (
                    dataset,
                    entity_id,
                    field,
                    json.dumps(value),
                    next_revision,
                    intervention_id,
                    now,
                ),
            )
            changes.append(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "field": field,
                    "before": before,
                    "after": value,
                }
            )
    if not changes:
        raise HTTPException(422, "Repair does not change any fleet readiness value")
    return changes