# Warehouse Fulfillment Control Tower

Single maintained product requirements, architecture and decision record.

## Shared robot charging lifecycle

Robot battery and charging are persisted simulation state, separate from source
fitness. Source battery initializes a known robot once and never overwrites its
evolved battery after replay or restart. An unclaimed robot with known battery
strictly below 10% docks automatically, including when its health/readiness
evidence is not assignment-eligible. A robot at exactly 10% does not dock.
Running, paused, and legacy multi-resource claims always prevent docking until
the claim is released, so an admitted stage completes without a battery-driven
pause. Reconciliation immediately after completion docks a newly released,
low-battery robot before another assignment can acquire it.

Charging remains the persisted `charging` Y/N state, advances at +5 percentage
points per minute, and automatically changes to N at 100%. Non-charging battery
advances at -5 percentage points per hour. The lifecycle resource response exposes the
same persisted value under both `charging` and the exact compatibility alias
`Docked_for_charging`; no second mutable docking column exists. Unknown-battery
robots and control assets never auto-charge. Charging continues to block new
assignment eligibility, while existing fitness and explicit safety blocks
remain independently enforced.

## 1. Product requirements

This application demonstrates API-connected warehouse fulfillment using durable
simulated inventory, robot and asset state. It does not operate physical
equipment, modify external WMS/ERP/FMS systems, or establish sensor ground truth.
The original CSV/JSONL datasets and six legacy inspection tabs remain intact.

### Order entry: FDE Bazaar

FDE Bazaar is a separate web application with its own SQLite order database.
Orders contain one or more distinct SKUs, positive integer quantities, a
generated FBZ identity and one of `Same_Day`, `Next_Day`, or `Standard`.
An independently persisted HTTP outbox sends the same request identity and
original order creation time to Control Tower through retries and restarts.
New Bazaar orders require an explicitly selected warehouse, without an arbitrary default.

Deadlines are absolute UTC instants from the original creation timestamp:

| Service | Cutoff |
|---|---|
| Same_Day | Creation + 6 hours |
| Next_Day | Creation + 12 hours |
| Standard | Creation + 24 hours |

### Acceptance, warehouse mapping and partial fulfillment

For new Bazaar orders, Core validates every SKU against allocatable stock in
the selected warehouse within the reservation transaction. A shortage rejects
the entire order with no partial reservations and no cross-warehouse fallback.
Zones and locations are assigned as before within that warehouse. Bazaar keeps
failed submissions for inspection/retry; submission alone is not Core acceptance.

For historical automatic requests and non-Bazaar callers, Control Tower
allocates each SKU independently to one warehouse that can supply
the entire line. Within that warehouse it can allocate multiple locations/zones.
Other available SKU lines proceed even if one line remains held. A line is not
partially allocated across warehouses or split into available/unavailable units.

Eligible warehouses are ordered by greatest remaining stock after allocation,
then warehouse ID. Locations are ordered by location ID. These are deterministic
demo tie-breaks, not claims about distance or travel time.

The effective `inventory_snapshot` table stores **unallocated/free** WMS, ERP
and vision quantities. Location availability is the nonnegative minimum of
those three values, subject to eligible inventory status and no blocking
opening-balance discrepancy. Reservations must not be subtracted again.

Forecast reporting instead sums the nonnegative source minimum across all
locations without applying allocation eligibility and without another
reservation deduction. This deliberately distinct free-availability metric
does not weaken inventory allocation safety. A persisted daily statistical
baseline (mean ordered units over up to 30 completed IST calendar days,
including zero-demand days) provides integer 7/30-day forecasts. Seven-day
predicted demand replaces the legacy fixed low-stock threshold.

Each accepted allocation transfers quantity `q`:

| Event | Each free source quantity | Reserved | Picked / in-process |
|---|---|---|---|
| Accept stock allocation | −q | +q | No change |
| Assign robot / start Pick | No change | No change | No change |
| Successfully complete Pick | No change | −q | +q |
| Move / Pack_feed | No change | No change | Remains in-process |
| Complete Stage | No change | No change | Moves to completed |
| Cancel before Pick completes | +unpicked q | −unpicked q | No change |
| Cancel after Pick completes | No automatic restock | No picked reservation remains | Recovery required |

Stock-shortage holds have no reservation. Resource waits retain already
accepted inventory. Replenishment/corrections reconsider held stock in cutoff
order and cannot reserve twice. A parent order cannot claim full completion
while required lines remain held, active or in recovery.

### Fleet task assignment

Each SKU executes `Pick → Move → Pack_feed → Stage`, with a separate Pick task
for each allocated location; Move waits for all of that SKU's Picks. Each Pick
releases only its own location reservation. Every assigned task
uses the shared `task_duration_seconds` setting (45 simulated seconds by
default); four stages therefore require at least four times the configured
duration, excluding resource waits and interruption/recovery.

Robot eligibility includes:

- `health_status = HEALTHY`.
- A nonblank `safety_cert_status` other than `EXPIRED`.
- `connectivity` of `ONLINE` or `INTERMITTENT`.
- Battery, calibration and certificate-date fields are informational, not
  additional source-readiness conditions in this simulator policy.
- Appropriate robot type, warehouse and sufficient payload for the actual
  quantity carried using the SKU's consistent positive `weight_kg`.
- No blocking maintenance/readiness evidence, explicit safety hold, resource
  block or conflicting resource claim.

Maintenance evidence with `OPEN`/`IN_PROGRESS` work or non-`AVAILABLE` fleet
availability blocks selection. Contradictory evidence is not bypassed by a
safety-release flag. Control assets must match the stage and warehouse, have
`state = AVAILABLE` and `maintenance_state = CLEAR`, and be unclaimed.
These checks are simulator policies, not certification of real feasibility.
Synthetic SKU weights are not measured physical weights.

Missing maintenance evidence or a missing CMMS status is ineligible. All
supplied maintenance records are treated as current evidence because the source
does not provide a reliable supersession mechanism; any blocking record wins.
Closed historical work is nonblocking only when its availability is also
`AVAILABLE`.

### Supervisor Workspace

Surface quantity discrepancies and below-threshold replenishment alerts.
Issues linked to held work are P1; other inventory issues are P2.
Two independently searched and paginated sections show **Discrepancies &
Interventions** and **Low Stock**, side by side on desktop and stacked on mobile.
Each page contains up to 10 items. The first section excludes replenishment
issues but retains other operational intervention kinds.

Low Stock groups alerts by warehouse and SKU. A warehouse/SKU aggregate alert
retains the fulfillment state API's conservative stock calculation and configured
threshold; related location-specific replenishment issues retain their own
quantity basis and correction workflow. These are distinct scopes, presented in
one group rather than duplicated cards. A location issue may still need review
when no warehouse-wide low-stock alert exists.

Inventory mismatch issues use a simple **Mark as closed** action with a required
comment. Closing sets the affected location's app-owned WMS, ERP and Vision free
quantities to the maximum of their current values in the same transaction as
closure. Historical SKU-wide issues synchronize each location independently.
Closing records the comment, role, time and before/after quantities. It does not
write to external WMS/ERP systems, release reservations, change picked quantities,
clear allocation blockers or recover held orders.
Unchanged observations remain closed on polling. A changed source condition can
reopen the issue for a new review.

The Supervisor workspace does not offer manual “Report Inventory Mismatch” or
“Report Task Conflict” creation options. Priority overrides remain available.
Other modeled correction/replenishment workflows retain their source, quantity
basis, revision and approval/evidence controls.

Free-stock corrections are explicitly different from observations of total
on-hand stock. Total observations must be converted according to the stated
accounting basis, protecting existing reservations and picked units.
The total-on-hand basis includes free, reserved and picked onsite stock;
conversion subtracts reserved plus picked exactly once. Completed/offsite units
are not part of that observation.

### Fleet Manager Workspace

Show one **Active Fleet Issues** panel, searched before pagination, with ten
items per page. Clicking an alert opens a direct edit-and-save popup for robot,
linked maintenance or control-asset readiness values; no investigation,
approval or required comment is part of this repair flow.

Repairs are persisted atomically in the application database with revision
checks and before/after history. Imported source files remain unchanged.
Every linked maintenance record must satisfy the readiness rules. Missing
readiness evidence must be supplied explicitly, never presumed healthy.

After repair, the same effective source values drive detection and execution.
An alert clears only when its source conditions are satisfied. The executor
can acquire repaired resources or resume eligible paused work using the V2
sub-order warehouse and task stage. Warehouse/type/capacity compatibility,
exclusive claims, explicit holds and blocks still apply; repairs do not
release independent holds, fabricate task completion or change stock counts.

The **Reported incidents** link opens a separate searchable, paginated record
of manually reported holds/releases and task failures. Creating a report opens
its existing incident workflow immediately. This keeps investigation, handoff
and recovery available without mixing them into source-readiness repairs or
restoring the removed Active Interventions panel.

### Order Fulfillment

Show completed, held, cancelled, active and partially fulfilled work with
sub-order quantities, warehouse/zone assignments, cutoff/overdue state and
movement/task timelines. This is the Supervisor's landing page. The order queue
links to order details, and **View All** opens the full order list. Inventory
Explorer in the sidebar provides resource access; duplicate Dashboard, Orders
and Resources subnavigation is not shown for Supervisors.

Low-stock monitoring belongs in Supervisor Workspace, not beside the order
queue. The application does not expose a **Run Demo** button or HTTP demo
execution endpoint. The isolated fixture runner remains available to developers
for internal verification only. The **Specs** download button is removed from the
operational UI; this maintained specification is retained in the workspace
Library.

The existing persona switch is a **demo role selector, not secure login**.
Server-side persona action checks do not constitute production authentication.

## 2. Architecture

```text
FDE Bazaar UI
    → Bazaar API / SQLite orders + durable HTTP outbox
    → Control Tower acceptance API
        → SQLite parent orders + SKU sub-orders + location allocations
        → effective inventory_snapshot + immutable quantity-movement ledger
        → deadline-prioritized persisted task executor
            → simulated robots and control assets (shared configurable duration)

Supervisor / Fleet UI
    → persona proposal → approval → effective source correction → verification
    → held-work reevaluation and operational polling
```

### Consistency boundaries

1. Intake identity, allocation, source debits, reservation credit and queue
   records commit atomically. Same identity with a different body is rejected.
2. Fleet acquisition is a separate transaction. Failure to acquire a robot
   cannot roll back a previously accepted inventory reservation.
3. Pick completion and cancellation serialize around outstanding allocations.
   Persisted movement identities prevent duplicate debits or releases.
4. The executor persists task start/due/completion times and resource claims.
   Restarting does not restart an assigned task's clock or replay stock
   movements. Configuration changes apply only to later assignments.
5. Corrections use optimistic revisions and preserve reservation/picked
   accounting. No browser can directly overwrite reservation totals.
6. Mutable availability is recomputed from current database state, not cached
   as an immutable source value.

### Compatibility and storage

Python FastAPI and SQLite remain the active backend. Raw sources stay read-only.
Opening migration accounts for external reservations once.
Opening inconsistencies block allocation and require review, not invented stock.

All operational orders and stock reads use policy v2. The old WMS-only
calculation, combined-policy alerts, physical-count overlays, planner and
executor are retired. Explicit-warehouse requests use the same current
allocation rules; they cannot select the old accounting policy.

The authorized development order reset is offline and one-time, never an
automatic startup action. It backs up both operational databases before
removing old order-owned records and Bazaar delivery state. Only unpicked
reservations return to free stock. Existing consumed/picked quantities remain
in the inventory model with a non-order opening baseline. Inventory
corrections, external reservations and unrelated resource safety data survive.
Hashed retired request identities prevent stale requests from recreating old
orders without retaining their contents. A cross-process maintenance lock
excludes the API and its workers while the reset runs.

### API surfaces

- `/api/bazaar/catalog`, `/api/bazaar/orders`: separate order entry/history.
- `/api/fulfillment/orders`: acceptance, detail, retry and cancellation.
- `/api/fulfillment/state`: live order/task summaries and stock alerts.
- `/api/fulfillment/resources/inventory`: effective inventory inspection.
- `/api/personas/workspace` and intervention actions: audited corrections.
- `/api/personas/workspace?section=discrepancies`: non-replenishment issues with
  server-side search and paging; summary counts remain global to the role.
- `/api/personas/low-stock`: grouped warehouse/SKU alerts and location-specific
  replenishment workflows with server-side search and paging.
- `/api/fulfillment/specification`: this document, retained for compatibility
  without an operational UI download button.

### Durable progress and generated order export

`order_progress.py` is an additive projection over the authoritative order,
sub-order, task and allocation tables. Within the same transaction as lifecycle
work, callers run `ensure_schema(db)` and `sync(db, now)`, then use
`enrich_order(db, result)` for reads. The projection persists the specified
fulfillment vocabulary for parents and sub-orders and records idempotent
transition keys. Task `started_at` and `completed_at` remain the time authority;
in particular, a completed stage is retained in history even when its next
awaiting state is entered at that same instant. Multiple location Picks reach
Pickup Completed only after every Pick is durably complete. Parent progress is
the least advanced required SKU, so held or incomplete lines are not hidden by
completed siblings. Existing public statuses and hold, cancellation and
recovery reasons are not changed.

After the lifecycle transaction commits, the API may call
`export_orders(db, path)` and retry a failed call. It regenerates a separate
application-owned CSV from SQLite, with one row per allocation and one row for
an unallocated/held sub-order, actual warehouse/zone assignments, public and
fulfillment statuses, deadlines and quantities. The writer escapes
spreadsheet-formula prefixes, fsyncs a temporary file, atomically replaces the
target and fsyncs its directory. Repeated export neither resets database state
nor reads, edits or reinterprets an imported source CSV.

## 3. Architecture decision records

### 2026-09-18 — Acceptance debits free stock

**Decision:** WMS/ERP/vision fields in the effective model represent free stock;
acceptance reduces all three and increases reserved stock. Pick releases the
reservation without another source debit.

**Why:** The user's acceptance/Pick clarification supersedes the original
specification's repeated `minimum − reserved` formula. Applying both would
double-deduct stock. Original imported raw fields remain available as evidence.

### 2026-09-18 — SKU-independent allocation

**Decision:** Choose one warehouse per requested SKU, allow multiple locations
inside it, and hold only unavailable SKU lines.

**Why:** This enables partial multi-SKU fulfillment without introducing an
unrequested split-quantity/cross-warehouse shipment policy.

### 2026-09-18 — Reserve before fleet assignment

**Decision:** Stock acceptance and resource acquisition are separate durable
transactions.

**Why:** Robot unavailability should not lose an accepted customer's reservation
or cause quantity effects to repeat on retry.

### 2026-09-18 — Compatibility instead of historical replanning

**Decision:** Keep saved historical plans/deadlines and adapt their accounting;
new automatic-mapping orders use the new policy.

**Why:** Replanning existing active work would risk changing commitments or
consuming stock twice.

### 2026-09-18 — Corrections update modeled systems only

**Decision:** Persist source-specific corrections with reason, evidence,
approval and verification in the demo database, without editing raw files.

**Why:** External integrations and physical verification do not exist in this
project. The UI must not imply that an external WMS or real robot was updated.

### 2026-09-18 — Deterministic scheduling, no ML

**Decision:** Use explicit eligibility and cutoff-prioritized scheduling.

**Why:** The approved scope requires a demonstrably correct order lifecycle,
not spatial prediction using nonexistent warehouse maps or training labels.

## 4. Requirement traceability and verification

| Uploaded specification requirement | Implementation surface | Verification |
|---|---|---|
| §1 Separate order app and API handoff | Bazaar API/UI + outbox | Isolated Bazaar tests |
| §2 Warehouse mapping, queue, partials | Policy-v2 inventory/sub-orders | Isolated core lifecycle tests |
| Acceptance/Pick accounting | Location allocations + movement ledger | 100→90 case; 60+30 case; retries/cancellation |
| §3 Fleet stages and eligibility | V2 scheduler and selectors | Configured-duration and eligibility-boundary tests |
| §4 Supervisor corrections/P1/P2 | Persona workspace/actions | Isolated role correction tests |
| §5 Fleet readiness corrections | Persona workspace/actions | Approval, remaining-blocker and role checks |
| §4 Operational summaries | Fulfillment UI and state API | Type checks, build and browser verification |
| Preserved history | V1 compatibility adapter | Existing regression suite and migration tests |
| Demonstrable working flow | Internal isolated fixture runner (not exposed in UI/API) | Real generated movement/check results |

### Verification record — 2026-09-18

- 73 isolated Python regression checks passed across fulfillment, inventory
  boundaries, persona workflows and Bazaar.
- Both web applications passed TypeScript checks and production builds.
- The isolated demo passed all seven assertions, including the 60-then-30
  availability boundary and stock-shortage recovery.
- Full-catalog role polling was profiled against all 9,360 inventory rows in a
  temporary database; repeated unchanged polls were approximately 0.08 seconds.
  Workspaces paginate persisted issue/history records rather than discarding
  records to achieve this speed.
- The six legacy page implementations and original source data were not edited.
- One browser end-to-end pass confirmed multi-SKU Bazaar intake, exact Standard
  cutoff, partial stock acceptance/resource wait, per-item detail and ledger,
  cancellation restoring only the new order's unpicked stock, the passing demo,
  role-specific screens and server-batch navigation. Its test order was cancelled;
  unrelated orders and inventory were not reset.
- A targeted follow-up of the repaired correction flow completed actual browser
  investigate → propose → approve → verify actions with revision zero and required
  evidence. The clearly labeled test intervention resolved, and its zero-change
  correction left all three quantities and protected reservations unchanged.

The general resource browser retains original source-column observations for
inspection and adds `effective_*` live inventory balances. Inventory editing
initializes the three source quantity inputs from those live free balances;
observed total-on-hand corrections belong in the Supervisor workflow.

### Audited opening-balance recovery

Source corrections alone do not erase an opening reservation discrepancy.
Verification requires a reviewer reference and current observations of all three
sources, their revision and an explicit attestation. For an opening external
reservation discrepancy, these observations must use total-on-hand quantities:
each total equals its current free quantity plus protected reserved and picked
quantities. Valid verification clears only that opening block, records an audit
correction and reevaluates held work without changing existing reservations.
An unresolved historical reservation mapping discrepancy remains blocked until
its separate reconciliation is completed. Duplicate opening verification cannot
release, reserve or record the same inventory movement twice.

New aggregate-only `physical_qty` proposals are rejected under policy v2 with
guidance to specify source, location, basis and revision. Existing persisted
overlays remain readable through historical compatibility paths; new corrections
cannot silently write a separate, ineffective stock overlay.

This document describes the implemented policy and its explicit simulation
boundaries, not production certification, live stock accuracy or secure
multi-user access.