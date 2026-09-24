# ADR-003 — Keep brownfield evidence immutable and separate mutable state

**Status:** Accepted (as-built)  
**Date:** 2026-09-22

## Context

The inherited CSV, JSONL and SQLite data contain contradictions that are part of
the FDE evidence. Editing those files would erase lineage and make demo effects
indistinguishable from source observations.

## Decision

Treat all inherited brownfield files as immutable. Store orders, reservations,
tasks, quantity movements, scenario overlays, corrections, lifecycle state,
interventions and forecasts in separate application-owned SQLite databases.
Expose source and effective values with explicit labels.

## Consequences

- Original defects and provenance remain reviewable.
- Demo state survives restarts without rewriting evidence.
- Reconciliation logic must clearly combine source, overlay and ledger state.
- A correction proves only a modeled app change, not an external-system update
  or physical observation.

## Evidence

- Repo 3 `artifacts/api-server/fulfillment_api.py`
- Repo 3 `artifacts/api-server/PERSONA_API.md`
- Repo 3 `artifacts/api-server/.local/fulfillment.sqlite`
- Repo 3 nested `brownfield/.../data`
