# Current policy note

New Bazaar orders require a selected warehouse. Core accepts all lines only if
that warehouse can allocate their full quantities; shortage rejects acceptance
without reservations. Zones and locations are still assigned within that warehouse.
Historical outbox messages without a warehouse retain automatic assignment.
Bazaar persists submissions independently; failed or pending delivery is not Core acceptance.
Cutoffs are
original creation +6 hours (Same_Day), +12 hours (Next_Day) and +24 hours
(Standard). Saved requests retain their bodies and deadlines for idempotent
replay. Requests retired by an authorized reset instead return HTTP 409.
The current unified PRD/architecture/ADRs are in
[CONTROL_TOWER.md](CONTROL_TOWER.md).

# FDE Bazaar intake API

The Bazaar component is mounted on the existing FastAPI gateway at
`/api/bazaar`. It owns `.local/bazaar.sqlite`; it never writes the Control
Tower fulfillment database and never calls fulfillment Python functions.

## Flow and ownership

`GET /catalog` obtains the complete current warehouse and SKU catalog over
HTTP from Control Tower, normalizes it for order entry, and briefly caches the
single complete response. `POST /orders` validates against that catalog,
computes the deadline, and atomically commits the `FBZ-…` order, lines, and
outbox record before attempting delivery.

The durable outbox performs a bounded HTTP `POST` to
`/api/fulfillment/orders`. Its stable downstream `request_id` makes an
ambiguous timeout safe to retry. Transient failures use persisted exponential
backoff; permanent 4xx failures do not loop automatically. Startup recovers
pending work and stale `sending` claims. Manual
`POST /orders/{id}/retry` uses the same serialized claim path.

Control Tower provenance fields are nullable and additive:
`source_order_id`, `order_service`, and `order_source`. Existing callers and
rows remain valid.

## Service assumptions

Deadlines use elapsed hours from original creation and are stored as UTC:

* `Same_Day`: +6 hours, priority `urgent`
* `Next_Day`: +12 hours, priority `high`
* `Standard`: +24 hours, priority `standard`

`GET /orders/{id}` fetches current Control Tower status and issues with a
bounded HTTP request. Failure is returned as `sync_error`; no current status
is fabricated.

The default Control Tower base is
`http://127.0.0.1:$PORT/api/fulfillment`. Deployments may set
`CONTROL_TOWER_API_BASE_URL` through application environment configuration.
No secret is required or logged.

## POC limitation

This shared demo gateway is unauthenticated. Request UUIDs provide
idempotency, not identity, authorization, tenant isolation, or protection
against malicious callers.