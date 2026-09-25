"""Shared source-condition readiness predicates for fleet resources."""

from __future__ import annotations

from typing import Any, Iterable


def _value(row: dict[str, Any], field: str) -> Any:
    """Read the normalized field, tolerating an observed all-caps source header."""

    if field in row:
        return row.get(field)
    return row.get(field.upper())


def robot_readiness(
    robot: dict[str, Any],
    maintenance_rows: Iterable[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Return readiness based only on authoritative robot source conditions."""

    reasons: list[str] = []
    robot_id = str(_value(robot, "robot_id") or "")
    health = _value(robot, "health_status")
    certificate = str(_value(robot, "safety_cert_status") or "").strip()
    connectivity = _value(robot, "connectivity")

    if health != "HEALTHY":
        reasons.append("Health is not HEALTHY")
    if not certificate:
        reasons.append("Safety certification status is unknown")
    elif certificate == "EXPIRED":
        reasons.append("Safety certification is EXPIRED")
    if connectivity not in {"ONLINE", "INTERMITTENT"}:
        reasons.append("Connectivity is neither ONLINE nor INTERMITTENT")

    records = [
        row
        for row in maintenance_rows
        if str(_value(row, "robot_id") or "") == robot_id
    ]
    if not records:
        reasons.append("Maintenance/availability evidence is unknown")
    else:
        for row in records:
            record_id = str(_value(row, "work_order_id") or "").strip()
            label = f"Maintenance {record_id}" if record_id else "Maintenance record"
            cmms = str(_value(row, "cmms_status") or "").strip()
            availability = _value(row, "fleet_availability")
            if not cmms:
                reasons.append(f"{label} CMMS status evidence is unknown")
            elif cmms in {"OPEN", "IN_PROGRESS"}:
                reasons.append(f"{label} CMMS work is {cmms}")
            if availability != "AVAILABLE":
                reasons.append(f"{label} fleet availability is not AVAILABLE")

    return not reasons, reasons


def asset_readiness(asset: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return readiness based only on authoritative control-asset conditions."""

    reasons: list[str] = []
    if _value(asset, "state") != "AVAILABLE":
        reasons.append("Asset state is not AVAILABLE")
    if _value(asset, "maintenance_state") != "CLEAR":
        reasons.append("Asset maintenance is not CLEAR")
    return not reasons, reasons