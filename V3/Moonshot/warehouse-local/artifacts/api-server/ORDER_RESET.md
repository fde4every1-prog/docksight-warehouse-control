# Development order reset

This is an explicitly authorized, destructive maintenance operation, not an
API route or startup migration. It deletes app-owned operational orders and
their history in both stores. Imported brownfield reference files are untouched.

## Safety

- Stop the API workflow first: it owns intake, the executor and Bazaar delivery.
  The API and command also use a shared/exclusive cross-process lock.
- Both databases are backed up and integrity-checked before modification.
- The reset switches both stores to rollback journals and commits the attached
  databases in one transaction. An error rolls back both.
- Only outstanding unpicked allocations are released. Picked/completed stock,
  external reservations and unrelated correction/resource safety state remain.
- Per-location non-order inventory baselines are retained. Old request IDs are
  retained only as digests to reject stale replays.
- A durable marker makes this specific reset one-time. Rerunning it must not
  delete the new orders. Do not remove the marker to repeat the operation.

## Explicit command

From the repository root, with the API stopped:

```sh
python artifacts/api-server/operational_order_reset.py \
  --development-confirm \
  --fulfillment-db artifacts/api-server/.local/fulfillment.sqlite \
  --bazaar-db artifacts/api-server/.local/bazaar.sqlite
```

The command prints backup locations and counts. Backups remain in the
unserved `.local/backups` directory; do not expose them as public assets.
Do not restore only one database: their intake identities must stay paired.
Never run this command against published or production data.

Restart the API, then seed the two approved examples through actual HTTP:

```sh
python artifacts/api-server/scripts/seed_reset_orders.py \
  --base-url "https://$REPLIT_DEV_DOMAIN"
```

The seed command uses stable request identities and refuses to add test
orders if unrelated orders are present. It creates one Standard single-SKU
order and one Next_Day two-SKU order, quantity one per line. Reruns cannot
create duplicates. The normal executor, not the seed command, performs work.
Resource holds must be reported, never bypassed to manufacture completion.