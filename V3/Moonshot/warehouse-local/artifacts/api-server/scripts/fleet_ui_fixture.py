"""Isolated browser-test API; never opens the operational database.

Run with an unused port argument. The temporary database and synthetic
resources exist only for this process; the normal UI can proxy its /api
requests here during browser verification.
"""

from contextlib import asynccontextmanager
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fulfillment_api as fulfillment
import persona_api as persona
from fastapi import FastAPI
import uvicorn


def main(port: int):
    with tempfile.TemporaryDirectory(prefix="fleet-ui-") as directory:
        fulfillment.DB_PATH = Path(directory) / "fixture.sqlite"
        inventory = ({
            "warehouse_id": "W1", "sku": "TEST-SKU", "location": "W1-Z1-B1",
            "wms_qty": "20", "erp_qty": "20", "vision_qty": "20",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "1",
        },)
        fixtures = {
            "inventory": inventory,
            "warehouses": ({"warehouse_id": "W1"},),
            "skus": ({"sku": "TEST-SKU"},),
            "robots": tuple({
                "robot_id": f"TEST-R{index:02}", "warehouse_id": "W1",
                "robot_type": "AMR", "payload_kg": "100",
                "health_status": "DEGRADED", "safety_cert_status": "EXPIRED",
                "connectivity": "OFFLINE", "battery_soc": "1",
                "calibration_status": "INVALID",
            } for index in range(12)),
            "maintenance": (),
            "control_assets": (
                {"asset_id": "TEST-CONVEYOR", "warehouse_id": "W1",
                 "asset_type": "CONVEYOR", "state": "BLOCKED", "maintenance_state": "DUE"},
                {"asset_id": "TEST-DOCK", "warehouse_id": "W1",
                 "asset_type": "DOCK_DOOR", "state": "AVAILABLE", "maintenance_state": "CLEAR"},
            ),
        }
        def source(dataset):
            return fixtures.get(dataset, ())
        source.cache_clear = lambda: None
        persona._ORIGINAL_RAW_SOURCE_ROWS = source
        fulfillment._init_db()
        persona._ensure_schema()
        order = fulfillment.create_order(fulfillment.OrderInput(
            request_id=str(uuid.uuid4()), priority="standard",
            order_service="Standard", order_created_at=fulfillment.iso(fulfillment.utc_now()),
            lines=[fulfillment.OrderLineInput(sku="TEST-SKU", quantity=1)],
        ))
        print(f"Isolated fleet fixture: {fulfillment.DB_PATH}; order: {order['id']}", flush=True)

        @asynccontextmanager
        async def lifespan(app):
            fulfillment.start_executor()
            try:
                yield
            finally:
                fulfillment.stop_executor()

        app = FastAPI(lifespan=lifespan)
        app.include_router(fulfillment.router)
        app.include_router(persona.router)
        uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python fleet_ui_fixture.py UNUSED_PORT")
    main(int(sys.argv[1]))