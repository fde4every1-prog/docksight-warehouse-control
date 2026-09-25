"""Read-only review adapters; original brownfield files are never modified."""

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from warehouse_control.diagnostics import run
from warehouse_control.legacy.allocator import choose_robot, legacy_score
from warehouse_control.legacy.inventory import legacy_available_qty

ROOT = Path(__file__).resolve().parent / "brownfield" / (
    "AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2"
)
DATASETS = {
    "robots": "data/raw/robots.csv",
    "inventory": "data/raw/inventory_snapshot.csv",
    "tasks": "data/raw/tasks.csv",
    "maintenance": "data/raw/maintenance.csv",
    "priorities": "data/shadow/wave_priority_FINAL_v7.csv",
    "zones": "data/raw/zones.csv",
    "telemetry": "data/telemetry/robot_telemetry.csv",
}
Dataset = Literal[
    "robots", "inventory", "tasks", "maintenance", "priorities", "zones", "telemetry"
]
router = APIRouter(prefix="/api")


@lru_cache(maxsize=7)
def rows(dataset: str):
    with (ROOT / DATASETS[dataset]).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def robot_index():
    return {r["robot_id"]: r for r in rows("robots")}


def flags_for(dataset, row):
    flags = []
    if dataset == "robots":
        if row["safety_cert_status"] == "EXPIRED":
            flags.append("Expired safety certification")
        if row["connectivity"] != "ONLINE":
            flags.append(f"Connectivity: {row['connectivity']}")
        if row["health_status"] != "HEALTHY":
            flags.append(f"Health: {row['health_status']}")
        if row["calibration_status"] != "VALID":
            flags.append(f"Calibration: {row['calibration_status']}")
    elif dataset == "inventory":
        if len({row["wms_qty"], row["erp_qty"], row["vision_qty"]}) > 1:
            flags.append("Source quantities disagree; physical truth unresolved")
    elif dataset == "tasks":
        if row["wes_status"] != row["fleet_status"]:
            flags.append("WES / fleet state disagreement")
        robot = robot_index().get(row["assigned_robot"])
        if not robot:
            flags.append("Assigned robot not found in registry")
        elif robot["warehouse_id"] != row["warehouse_id"]:
            flags.append(f"Robot registered at {robot['warehouse_id']}; site/time validity unresolved")
    elif dataset == "maintenance":
        if row["cmms_status"] in {"OPEN", "IN_PROGRESS"} and row["fleet_availability"] == "AVAILABLE":
            flags.append("Active work order / fleet available")
        if row["safety_release_recorded"] == "N":
            flags.append("No recorded safety release")
    elif dataset == "priorities":
        flags.append("Manual priority in shadow spreadsheet")
    elif dataset == "zones" and row["physical_change_pending"] == "YES":
        flags.append("Physical change pending")
    elif dataset == "telemetry" and row["telemetry_quality"] != "GOOD":
        flags.append(f"Telemetry quality: {row['telemetry_quality']}")
    return flags


@router.get("/healthz")
def health():
    return {"status": "ok"}


@router.get("/review/overview")
def overview():
    return {
        "diagnostics": run(),
        "sites": sorted({r["warehouse_id"] for r in rows("robots")}),
        "counts": {key: len(rows(key)) for key in DATASETS},
        "notes": (ROOT / "data/shadow/ops_emails.txt").read_text(),
        "allocatorSource": (ROOT / "src/warehouse_control/legacy/allocator.py").read_text(),
        "inventorySource": (ROOT / "src/warehouse_control/legacy/inventory.py").read_text(),
        "snapshot": str(json.loads((ROOT / "data/manifest.json").read_text())["generated_at"]),
        "limitations": [
            "New read-only review UI over the original synthetic snapshot; not a live control center.",
            "Original code and data remain unchanged. Review flags are annotations, not legacy validations.",
            "alias_collisions counts repeated alias strings; it does not prove six distinct identity collisions.",
            "Cross-source differences may reflect scope, timing or semantics. No source establishes physical truth alone.",
            "Tasks lack payload requirements and orders lack order-line SKU quantities.",
            "No changes are saved and no missions, approvals or physical controls are executed.",
        ],
    }


@router.get("/review/records/{dataset}")
def records(
    dataset: Dataset,
    site: str = Query("", max_length=64),
    search: str = Query("", max_length=200),
    flagged: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    source = rows(dataset)
    result = []
    needle = search.casefold()
    for number, row in enumerate(source, start=2):
        if site and row.get("warehouse_id") != site:
            continue
        if needle and not any(needle in value.casefold() for value in row.values()):
            continue
        flags = flags_for(dataset, row)
        if flagged and not flags:
            continue
        record = {"rowNumber": number, "values": row, "flags": flags}
        if dataset == "inventory":
            record["legacyAvailable"] = legacy_available_qty(row)
        result.append(record)
    return {
        "dataset": dataset,
        "source": DATASETS[dataset],
        "columns": list(source[0]) if source else [],
        "records": result[offset:offset + limit],
        "total": len(result),
        "offset": offset,
        "limit": limit,
    }


class AllocationInput(BaseModel):
    site: str = Field("", max_length=64)
    payload_kg: float = Field(1000, ge=0, le=100000, allow_inf_nan=False)


@router.post("/review/allocator")
def allocator(request: AllocationInput):
    robots = rows("robots")
    if request.site:
        if request.site not in {r["warehouse_id"] for r in robots}:
            raise HTTPException(422, "Unknown warehouse")
        robots = [r for r in robots if r["warehouse_id"] == request.site]
    task = {"payload_kg": request.payload_kg}
    # This invokes the unchanged legacy function, not a corrected selector.
    selected = choose_robot(robots, task)
    eligible = [
        r for r in robots
        if r.get("health_status") != "MAINTENANCE" and r.get("connectivity") != "OFFLINE"
    ]

    def scored(robot):
        warnings = flags_for("robots", robot)
        if float(robot["payload_kg"]) < request.payload_kg:
            warnings.append("Payload capacity below hypothetical requirement; ignored by legacy rule")
        return {"robot": robot, "score": legacy_score(robot, task), "flags": warnings}

    ranked = sorted(eligible, key=lambda r: legacy_score(r, task), reverse=True)
    return {
        "selected": scored(selected) if selected else None,
        "candidates": [scored(r) for r in ranked[:10]],
        "eligibleCount": len(eligible),
        "inputCount": len(robots),
        "taskPayload": request.payload_kg,
        "explanation": (
            "Executed unchanged choose_robot: exclude MAINTENANCE and OFFLINE, then maximize "
            "battery_soc + 10 if ONLINE. Ties retain source order. Payload is a hypothetical "
            "input ignored by this legacy function. Site filtering only scopes this inspection's "
            "input set. Warning flags are new review annotations, not enforced safety rules. "
            "No mission was created or dispatched."
        ),
    }