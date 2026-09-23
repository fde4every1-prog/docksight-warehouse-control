# ADR-002 — Deterministic simulation with no AI or physical control

**Status:** Accepted; carries forward V2 ADR-002  
**Date:** 2026-09-22

## Context

The supplied evidence has no trustworthy live topology, sensor ground truth,
training labels, controller interface or approved command authority. Repo 3
needs demonstrable order and resource behavior without inventing those inputs.

## Decision

Implement inventory, eligibility, scheduling, forecasting and recovery as
explicit deterministic/statistical policies. Do not add an LLM, agent or
trained model. Execute only simulated state transitions in app-owned SQLite.
Provide no adapter that writes to a real WMS, FMS, PLC or robot.

## Consequences

- Decisions and failures are inspectable and reproducible.
- The product works without cloud/model availability.
- “AI-native autonomous control” is not a valid as-built runtime claim.
- Statistical forecasts must not be marketed as ML.
- Physical integration requires a separate mandate and safety case.

## Evidence

- Repo 3 `artifacts/api-server/CONTROL_TOWER.md`
- Repo 3 `artifacts/api-server/fulfillment_api.py`
- V2 `specs/adr/ADR-002-llm-off-write-path.md`
