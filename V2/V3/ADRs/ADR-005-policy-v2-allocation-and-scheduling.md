# ADR-005 — Policy v2 per-SKU allocation and deterministic scheduling

**Status:** Accepted (as-built)  
**Date:** 2026-09-22

## Context

A multi-line order may have stock for some SKUs but not others. Splitting one
line across warehouses adds unrequested routing/coordination complexity.
Resource selection must also remain explainable with incomplete brownfield data.

## Decision

For new Bazaar requests, require one selected warehouse and reject the entire
request if any line is unavailable there. For historical/compatibility callers,
allocate each SKU independently to one warehouse and allow available sibling
lines to progress. Within a warehouse, allow multiple locations. Schedule work
by explicit deadline/eligibility policy using deterministic tie-breaks.

## Consequences

- New Bazaar behavior is easy to explain and does not silently cross warehouses.
- Compatibility flows support partial multi-SKU fulfillment.
- No line is split across warehouses.
- The scheduler does not optimize travel, congestion or learned throughput.
- Historical plans remain compatible rather than being retroactively replanned.

## Evidence

- Repo 3 `artifacts/api-server/fulfillment_v2.py`
- Repo 3 `artifacts/api-server/CONTROL_TOWER.md`
- Repo 3 `artifacts/api-server/test_fulfillment_v2.py`
