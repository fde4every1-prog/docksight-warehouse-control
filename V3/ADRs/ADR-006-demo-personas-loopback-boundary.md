# ADR-006 — Demo personas require a loopback-only trust boundary

**Status:** Accepted as a demo constraint; supersede before shared use  
**Date:** 2026-09-22

## Context

Repo 3 exposes Supervisor, Fleet and Admin behavior using a UI selector and
`X-Demo-Persona` header. The caller controls that value. Several other mutating
routes do not use persona checks.

## Decision

Treat persona selection as a workflow demonstration only. Keep the packaged
application bound to loopback and use synthetic data. Do not expose it to a
shared network or claim secure approval/RBAC. Before shared use, introduce
authenticated identity, deny-by-default server authorization and route-level
coverage tests.

## Consequences

- Local demonstrations remain simple.
- Audit events show selected roles, not cryptographically trusted actors.
- Any network exposure is a security boundary violation.
- `/api/fulfillment/assign-tasks`, order/config/scenario mutations and all other
  write routes must be included in a future authorization inventory.

## Evidence

- Repo 3 `local_server.py`
- Repo 3 `artifacts/api-server/lifecycle_api.py`
- Repo 3 `artifacts/api-server/persona_api.py`
- Repo 3 `artifacts/api-server/FULFILLMENT_API.md`
