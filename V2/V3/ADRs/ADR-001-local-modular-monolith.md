# ADR-001 — Local modular monolith with one shared gateway

**Status:** Accepted (as-built)  
**Date:** 2026-09-22

## Context

Repo 3 must run as a portable local demonstration with Core Warehouse, FDE
Bazaar and Robot Fleet Simulator on one origin. The package has no production
platform, service mesh or managed datastore requirement.

## Decision

Use three React/Vite SPAs served by one Python/FastAPI process. Mount all
application APIs under `/api`; store state in local SQLite databases. Bind the
packaged launcher to `127.0.0.1`.

## Consequences

- Simple install, routing and same-origin integration.
- Transactions and demonstrations are easy to reproduce locally.
- Modules remain logical boundaries, not independently deployable services.
- One process/host and SQLite limit scaling, availability and isolation.
- Any network/shared deployment requires a new architecture and security review.

## Evidence

- Repo 3 `local_server.py`
- Repo 3 `artifacts/api-server/baseline_demo.py`
- Repo 3 `pnpm-workspace.yaml`
