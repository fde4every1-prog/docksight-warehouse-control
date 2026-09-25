# ADR-004 — Transactional stock ledger and idempotent intake

**Status:** Accepted (as-built)  
**Date:** 2026-09-22

## Context

Retries, process restarts and partial failures can duplicate customer orders,
reservations or stock movements. The three source quantities already represent
free stock under policy v2, so subtracting reservations again would also
double-count consumption.

## Decision

Persist Bazaar intake and outbox state before handoff. Require stable request
identities and reject changed-body reuse. In Core, atomically debit each free
source quantity and credit reservations at acceptance. On Pick, release
reservation into picked/in-process state without another free-stock debit.
Protect movements with durable identities and transaction boundaries.

## Consequences

- Lost responses and retries do not create duplicate orders or movements.
- Resource unavailability does not erase accepted stock reservations.
- Cancellation after Pick cannot automatically pretend stock returned.
- Schema and recovery logic are more complex and require invariant-based tests.

## Evidence

- Repo 3 `artifacts/api-server/bazaar_api.py`
- Repo 3 `artifacts/api-server/fulfillment_v2.py`
- Repo 3 `artifacts/api-server/order_progress.py`
- Repo 3 `artifacts/api-server/CONTROL_TOWER.md`
