"""Isolated HTTP fixture for Control Tower and robot-lifecycle UI checks.

Run directly; this module never starts the production executor or opens the
operational database after fixture installation.
"""

from __future__ import annotations

import atexit
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Keep this temporary directory alive for the complete server process. Import
# persona_api only after redirecting its schema initialization away from the
# operational database, but before replacing the fixture source seams.
_temporary = tempfile.TemporaryDirectory(prefix="lifecycle-ui-fixture-")
_patches = pytest.MonkeyPatch()
_fixture_db = Path(_temporary.name) / "fulfillment.sqlite"
_bazaar_db = Path(_temporary.name) / "bazaar.sqlite"
# Both modules may initialize storage during import: redirect BEFORE importing.
_patches.setenv("FULFILLMENT_DB_PATH", str(_fixture_db))
_patches.setenv("BAZAAR_DB_PATH", str(_bazaar_db))
storage_violations: list[str] = []


def guard_storage(event, args):
    """Fail closed before any fixture code can touch operational storage."""
    paths = ()
    if event in {"open", "sqlite3.connect", "os.mkdir", "os.remove", "os.rmdir",
                 "os.chmod", "os.truncate", "os.utime"}:
        paths = args[:1]
    elif event in {"os.rename", "os.link", "os.symlink"}:
        paths = args[:2]
    for value in paths:
        if not isinstance(value, (str, bytes, os.PathLike)):
            continue
        target = Path(os.fsdecode(value)).resolve()
        operational = target.is_relative_to(ROOT / ".local")
        unsafe_sqlite = event == "sqlite3.connect" and not target.is_relative_to(Path(_temporary.name))
        if operational or unsafe_sqlite:
            storage_violations.append(f"{event}: {target}")
            raise RuntimeError(f"Fixture attempted non-temporary storage: {event}: {target}")


sys.addaudithook(guard_storage)

import fulfillment_api as fulfillment  # noqa: E402
import bazaar_api as bazaar  # noqa: E402

import persona_api  # noqa: E402
import robot_lifecycle  # noqa: E402


clock = {"now": datetime(2030, 1, 1, tzinfo=timezone.utc)}
inventory = (
    {
        "warehouse_id": "W1",
        "sku": "A",
        "location": "W1-Z1-B1",
        "wms_qty": "100",
        "erp_qty": "100",
        "vision_qty": "100",
        "reserved_qty": "0",
        "inventory_status": "AVAILABLE",
        "weight_kg": "1",
    },
)
robots = tuple(
    {
        "robot_id": "R1",
        "warehouse_id": "W1",
        "robot_type": "AMR",
        "battery_soc": "90",
        "health_status": "HEALTHY",
        "payload_kg": payload,
        "safety_cert_status": "VALID",
        "calibration_status": "VALID",
        "connectivity": "ONLINE",
    }
    for payload in ("500",)
) + (
    {
        "robot_id": "R9",
        "warehouse_id": "W1",
        "robot_type": "AMR",
        "battery_soc": "90",
        "health_status": "HEALTHY",
        "payload_kg": "600",
        "safety_cert_status": "VALID",
        "calibration_status": "VALID",
        "connectivity": "ONLINE",
    },
)
maintenance = tuple(
    {
        "robot_id": robot["robot_id"],
        "warehouse_id": "W1",
        "cmms_status": "CLOSED",
        "fleet_availability": "AVAILABLE",
    }
    for robot in robots
)
assets = (
    {
        "asset_id": "W1-PACK",
        "warehouse_id": "W1",
        "asset_type": "PACK_STATION",
        "state": "AVAILABLE",
        "maintenance_state": "CLEAR",
    },
    {
        "asset_id": "W1-PACK-BACKUP",
        "warehouse_id": "W1",
        "asset_type": "PACK_STATION",
        "state": "AVAILABLE",
        "maintenance_state": "CLEAR",
    },
    {
        "asset_id": "W1-STAGE",
        "warehouse_id": "W1",
        "asset_type": "DOCK_DOOR",
        "state": "AVAILABLE",
        "maintenance_state": "CLEAR",
    },
)
fixtures = {
    "inventory": inventory,
    "skus": ({"sku": "A"},),
    "warehouses": ({"warehouse_id": "W1"},),
    "robots": robots,
    "maintenance": maintenance,
    "control_assets": assets,
    "labor_capacity": (),
}


def fixture_rows(dataset: str):
    return fixtures.get(dataset, ())


_patches.setattr(fulfillment, "utc_now", lambda: clock["now"])
_patches.setattr(bazaar, "utc_now", lambda: clock["now"])
_patches.setattr(bazaar, "_catalog_cache", None)
_patches.setattr(fulfillment, "_raw_source_rows", fixture_rows)
_patches.setattr(fulfillment, "source_rows", fixture_rows)
# persona_api bootstraps schemas at import time. Use a fresh isolated database
# after installing source fixtures so the import-time real catalog cannot
# become this fixture's immutable opening inventory snapshot.
_fixture_db = Path(_temporary.name) / "ui-scenario.sqlite"
_patches.setattr(fulfillment, "DB_PATH", _fixture_db)
fulfillment._init_db()
persona_api._ensure_schema()
bazaar._init_db()

# Register resources without assigning work. The browser journey deliberately
# begins at Bazaar order creation, so no hidden order can win the first claim.
with fulfillment.db_transaction(now=clock["now"]) as db:
    robot_lifecycle.reconcile(db, clock["now"], fulfillment.source_rows)


def bazaar_to_fulfillment(method: str, path: str, payload=None, timeout=4):
    """In-process replacement for Bazaar's production HTTP delivery seam."""
    if method == "GET" and path == "/catalog":
        return fulfillment.catalog()
    if method == "POST" and path == "/orders":
        return fulfillment.create_order(fulfillment.OrderInput(**payload))
    if method == "GET" and path.startswith("/orders/"):
        return fulfillment.get_order(path.removeprefix("/orders/"))
    raise bazaar.RemoteError(f"Unsupported isolated fixture request: {method} {path}")


_patches.setattr(bazaar, "request_json", bazaar_to_fulfillment)


app = FastAPI(
    title="Lifecycle UI isolated fixture",
    docs_url="/__test__/docs",
    openapi_url="/__test__/openapi.json",
)
app.include_router(fulfillment.router)
app.include_router(persona_api.router)
app.include_router(bazaar.router)


class AdvanceInput(BaseModel):
    seconds: int = Field(gt=0, le=86_400)


@app.post("/__test__/advance")
def advance(payload: AdvanceInput):
    """Advance the controlled clock and execute exactly one durable tick."""
    clock["now"] += timedelta(seconds=payload.seconds)
    completed = fulfillment.run_executor_once(clock["now"])
    with fulfillment._read_db() as db:
        lifecycle = robot_lifecycle.snapshot(db, clock["now"])
    return {
        "advanced_seconds": payload.seconds,
        "now": fulfillment.iso(clock["now"]),
        "completed": completed,
        "lifecycle": lifecycle,
    }


@app.get("/__test__/resource")
def test_resource():
    return {
        "database": str(_fixture_db),
        "bazaar_database": str(_bazaar_db),
        "initial_orders": 0,
        "storage_guard_enabled": True,
        "storage_violations": list(storage_violations),
        "sku": "A",
        "quantity": 2,
        "robot_id": "R1",
        "replacement_robot_id": "R9",
        "battery_pct": 90,
        "clock": fulfillment.iso(clock["now"]),
        "bazaar_create_endpoint": "/api/bazaar/orders",
        "bazaar_payload": {
            "service": "Same_Day",
            "lines": [{"sku": "A", "quantity": 2}],
            "request_id": "supply a new UUID",
        },
        "advance_endpoint": "/__test__/advance",
        "assign_endpoint": "/api/fulfillment/assign-tasks",
        "journey": [
            "Create the order in Bazaar and retain its control_tower_order_id.",
            "Assign once; R1 acquires the queued Pick for 45 seconds.",
            "As fleet, kill the running task with its assignment_token.",
            "Core promptly blocks R1 and acquires R9 with a fresh 45-second window.",
            "Advance the controlled clock to reach control-asset stages and repeat.",
        ],
    }


_cleaned = False


def cleanup() -> None:
    global _cleaned
    if _cleaned:
        return
    _cleaned = True
    _patches.undo()
    _temporary.cleanup()


@app.on_event("shutdown")
def shutdown_fixture() -> None:
    cleanup()


atexit.register(cleanup)


if __name__ == "__main__":
    # Test-only fixed port used by the browser request-forwarding runner.
    uvicorn.run(app, host="127.0.0.1", port=18081, log_level="warning")