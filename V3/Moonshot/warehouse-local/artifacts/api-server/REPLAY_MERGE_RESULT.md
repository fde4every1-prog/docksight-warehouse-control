# Operational replay consolidation

Applied in the development workspace on 2026-09-21. No production database or deployment was changed.

## Committed outcome

- Destination before merge: 9 ordinary orders.
- Imported: 7,000 orders (5,735 completed, 1,156 rejected for inventory shortage, 109 active).
- Destination after merge: 7,009 orders (5,742 completed, 1,156 rejected, 110 active, 1 cancelled).
- Imported task records: 23,376. Completed picks were retained.
- Source: `.local/replays/9f25c721-25ef-4d6c-a258-00b34c421191/simulation.sqlite`.
- Database integrity: `ok`; foreign-key violations: zero; negative stock balances: zero.
- Read-only repeat preflight recognizes the committed import without additional records or stock effects.

Paths below are relative to `artifacts/api-server/`.

## Backup and audit evidence

- Pre-merge database: `.local/backups/before-replay-merge-20260921T082822392549Z.sqlite`
- External identity/accounting manifest: `.local/backups/before-replay-merge-20260921T082822392549Z.audit.json`
- Pre-forecast-refresh database: `.local/backups/before-forecast-refresh-20260921T083257763007Z.sqlite`

The manifest's digest must match the committed maintenance receipt; a manifest alone is not proof of commit. The receipt is not an order classification or runtime scheduling filter.

## Inventory and execution

The imported ledger changes free WMS/ERP/vision by −5,844 each, reserved by zero, picked by +109, and completed by +5,735. Existing operational effects are retained. All 9,360 inventory rows reconcile against the opening evidence, retained reset baseline, recorded corrections, and movement ledgers. Four recorded corrections and one retired completed unit explain the otherwise different opening balances.

After restart the live scheduler continued advancing its normal clock. All 109 imported unfinished orders remain in DC-14 with pick completed, move queued, and pack-feed/stage pending. Move payloads are 1,013–1,493 kg. The recorded wait reason reports insufficient payload for RBT-0526 through RBT-0533. No resources, payload limits, task-duration settings, fleet repairs, or registrations were changed to bypass this.

## Application and forecast verification

Network Orders displays 7,009. Two 25-order pages have distinct records; exact source-ID search, rejected details, and merged replay redirects return ordinary records. Full CSV contains 7,010 allocation/line rows representing all 7,009 unique orders, including 1,156 rejected rows.

Observed proxied requests: state 0.322 seconds; first list page 0.236 seconds; next page 0.028 seconds; CSV 0.548 seconds. These are one-run observations, not performance guarantees.

The current forecast was explicitly regenerated from unified original-time demand while archiving its previous snapshot. Its 30-day window is 2026-08-22 through the start of 2026-09-21 in Asia/Kolkata, containing 3,020 units. Rejected demand is counted once by requested warehouse/SKU. The UI explicitly states that this calendar window does not establish complete coverage or zero demand after the supplied dataset ends.

Disposable-copy checks covered atomic rollback, idempotency before and after pending-stage progress, identity collisions, reconciled stock, unchanged operational configuration, and actual scheduler continuation with a compatible test-only robot. The normal fleet test retained the real capacity blocker. Application startup and the Network Orders screenshot were healthy.

The pre-existing `lifecycle-ui` browser workflow fails at fixture creation because its Bazaar request omits the required warehouse. This does not validate the changed flow; it is tracked separately rather than represented as a passing test.

## Reuse

`replay_merge.py` is offline-only. Stop the shared API before using it; its maintenance lock refuses concurrent runtime writers. Without `--apply` it performs read-only preflight. Never configure it to execute automatically at startup, after merge, or against production.