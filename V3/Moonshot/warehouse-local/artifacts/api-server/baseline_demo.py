"""Hosting adapter only. The imported ZIP source remains unchanged."""

import os
import sys
from contextlib import ExitStack
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

BASELINE_ROOT = (
    Path(__file__).resolve().parent
    / "brownfield"
    / "AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2"
)
sys.path.insert(0, str(BASELINE_ROOT / "src"))

from warehouse_control.api import app as baseline_app  # noqa: E402
from review_api import router as review_router  # noqa: E402
from fulfillment_api import router as fulfillment_router, start_executor, stop_executor  # noqa: E402
from persona_api import router as persona_router  # noqa: E402
from bazaar_api import router as bazaar_router, start_worker, stop_worker  # noqa: E402
from replay_api import router as replay_router  # noqa: E402
from predictive_api import router as predictive_router  # noqa: E402
from monthly_kpi_api import router as monthly_kpi_router  # noqa: E402
from batching_api import router as batching_router  # noqa: E402
from transfer_api import router as transfer_router  # noqa: E402
import bazaar_api
import fulfillment_api
import demand_forecast
from maintenance_lock import runtime_lock

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(review_router)
app.include_router(fulfillment_router)
app.include_router(persona_router)
app.include_router(bazaar_router)
app.include_router(replay_router)
app.include_router(predictive_router)
app.include_router(monthly_kpi_router)
app.include_router(batching_router)
app.include_router(transfer_router)
_runtime_locks = ExitStack()


@app.get("/api/fulfillment/specification")
def control_tower_specification():
    return FileResponse(
        Path(__file__).parent / "CONTROL_TOWER.md",
        media_type="text/markdown",
        filename="Control-Tower-PRD-Architecture-ADRs.md",
    )


@app.on_event("startup")
def start_fulfillment_simulator():
    try:
        for directory in sorted({
            fulfillment_api.DB_PATH.parent.resolve(),
            bazaar_api.DB_PATH.parent.resolve(),
        }):
            _runtime_locks.enter_context(runtime_lock(directory))
        start_executor()
        demand_forecast.start(fulfillment_api.db_transaction)
        start_worker()
    except Exception:
        stop_worker()
        demand_forecast.stop()
        stop_executor()
        _runtime_locks.close()
        raise


@app.on_event("shutdown")
def stop_fulfillment_simulator():
    try:
        stop_worker()
        demand_forecast.stop()
        stop_executor()
    finally:
        _runtime_locks.close()


@app.get("/", include_in_schema=False)
@app.get("/api", include_in_schema=False)
@app.get("/api/", include_in_schema=False)
def demo_entry():
    return RedirectResponse("/api/docs")


app.mount("/api", baseline_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ["PORT"]))