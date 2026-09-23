# AI FDE Brownfield Repo v2 — AI-Native Autonomous Warehouse & Robotics Control Center

This repository is a **fictional, deterministic, locally runnable brownfield enterprise simulation** for an AI Forward-Deployed Engineering capstone.

It represents a multinational warehouse network where ERP, OMS, WMS, WES, WCS, TMS, CMMS, robotics fleet managers, PLC/conveyor controls, vision systems, safety systems, labor systems and carrier feeds have evolved independently.

## Core engineering tension

**Digital warehouse state ≠ Physical warehouse state**

and

**Robot Available ≠ Robot Suitable ≠ Robot Optimal for Task**

The baseline works well enough to operate, but hidden inconsistencies, degraded modes, duplicated logic, conflicting system states, stale mappings, weak observability, local optimization and manual workarounds prevent trustworthy autonomous orchestration.

## L1–L12 brownfield imperfection model

1. **L1 — Software / Code** — legacy WMS/WES/WCS code, robot scripts, PLC logic, duplication, hard-coded rules, technical debt, weak tests.
2. **L2 — Robotics / Control Systems** — AMR, AGV, robotic arms, PLCs, conveyors, sorters, AS/RS, fleet managers, vendor integration drift.
3. **L3 — Data / Telemetry** — events, locations, sensor readings, vision observations, timestamps, confidence, quality and lineage problems.
4. **L4 — Asset / Robot** — identity, firmware, configuration, health, battery, calibration, payload/tooling and task suitability.
5. **L5 — Physical Warehouse** — aisles, racks, bins, zones, docks, paths, temporary obstacles, congestion and human movement.
6. **L6 — Inventory / Order** — SKU, lot, serial, quantity, location, reservation, pick, pack, shipment and physical-truth inconsistencies.
7. **L7 — Safety / Human-Robot Interaction** — safety zones, e-stops, interlocks, pedestrian interaction, reduced-speed modes and overrides.
8. **L8 — Operations** — dispatch, replenishment, wave planning, charging, maintenance, workforce, exceptions and workarounds.
9. **L9 — Enterprise / Supply-Chain Ecosystem** — ERP + OMS + WMS + WES + WCS + TMS + CMMS + suppliers + carriers + robotics vendors.
10. **L10 — Resilience / Continuity** — robot failures, network outages, conveyor failures, congestion, charger failures, rerouting, fallback and restart.
11. **L11 — Decision Intelligence Gaps** — weak planning, local optimization, poor forecasting, fragmented prioritization, uncertainty and weak causal reasoning.
12. **L12 — Autonomy / Safety Assurance** — bounded authority, human approvals, safety constraints, explainability, HITL, TEVV, auditability and governance.

## Forensic lenses

Every layer can be investigated using: **Imperfection, Inconsistency, Friction, Complexity, Volatility, Uncertainty, Hidden Dependency, Unknown Unknown**.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_data.py --check-only
python -m warehouse_control.cli diagnostics
pytest -q
```

Optional API:

```bash
uvicorn warehouse_control.api:app --reload
```

Set `PYTHONPATH=src` if your IDE does not infer the source root.

## Recommended participant path


## Safety / scope

This is synthetic warehouse/robotics training data. It does not connect to real robots, warehouses, safety PLCs, or external services. The baseline intentionally avoids issuing physical control commands.

## V2 reliability profile

This repository intentionally preserves domain-realistic brownfield contradictions and expected-failure tests while accidental packaging, import, stale-metadata and distributable-content defects are treated as release blockers. All external integrations are synthetic or read-only simulation surfaces; no real clinical, military, robotic, or OT control endpoint is configured. See `VERIFICATION.md` and `docs/07_v2_audit_and_changelog.md`.
