# Brownfield current-version demo

This runs the supplied Python/FastAPI application, not the proposed modernized control center. All extracted archive files under `brownfield/` are preserved unchanged.

## Browser demonstration

Open `/api/docs` for FastAPI's built-in interactive API documentation. The main preview now opens the separate Warehouse Legacy Review UI.

1. Expand **GET /health**, choose **Try it out**, then **Execute**. Physical control is disabled.
2. Expand **GET /diagnostics**, choose **Try it out**, then **Execute**. This runs the original diagnostic code over the bundled CSV snapshot.
3. Expand **GET /robots/{robot_id}**, enter `RBT-0001`, then execute. This reads the original SQLite database.
4. Optionally enter an unknown ID to demonstrate the preserved baseline limitation: HTTP 200 with `{"error":"not_found"}`.

Expected diagnostics: 712 robots, 6 repeated-alias groups, 7,382 inventory differences, 7,351 task-state differences, 176 maintenance/availability conflicts, 35 expired-cert non-offline robots, and 80 duplicate telemetry observations using the legacy key.

The legacy `alias_collisions` metric counts repeated alias strings; it does not prove six distinct identity collisions. All data is synthetic and static, not live telemetry.

## What was added

- Python 3.11 runtime and the archive's four pinned direct dependencies.
- `baseline_demo.py`: imports the original application, mounts it at `/api` for hosting, and redirects the preview to its existing documentation.
- Managed service configuration to run Python instead of the unused Express scaffold.

The subsequent UI adds read-only dataset adapters and a pure legacy allocator inspector under `/api/review`. The inspector runs the original function but never dispatches or saves anything. Dataset annotations are new review aids, not corrections to the source. No authentication, AI or physical-control capability was added. Known legacy defects remain intentionally visible. Do not expose private/real operational data through this unauthenticated demo.

## Local commands

From the project root:

```sh
cd artifacts/api-server/brownfield/AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2
PYTHONPATH=src python -m warehouse_control.cli diagnostics
python -m pytest -q
sha256sum -c checksums.sha256
```

Use the managed API Server workflow to start the browser demo; it supplies the required `PORT`.