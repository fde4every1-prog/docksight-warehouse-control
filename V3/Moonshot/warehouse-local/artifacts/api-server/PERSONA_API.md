# Persona workspace API

## Direct fleet readiness repair

`GET /api/personas/fleet/issues?limit=10&offset=0&q=...` returns active robot
and control-asset source-readiness issues as
`{"items": FleetIssue[], "pagination": {"limit": 10, "offset": 0, "total": n}}`.
Search is applied before pagination. Fleet and Admin may read this endpoint;
Supervisor is forbidden. `GET /api/personas/fleet/issues/{id}` returns one
issue. Each issue includes `blockers`, independent `assignment_blockers`,
complete editable `contexts`, event history, and a top-level `fingerprint`.
Contexts contain `entity_type`, stable `entity_id`, integer `revision`,
effective `values`, `allowed_values`, and `missing: true` when a robot has no
maintenance record.

Only Fleet may call `POST /api/personas/fleet/issues/{id}/repair`. The body is:

```json
{
  "fingerprint": "64-character fingerprint returned with the issue",
  "contexts": [{
    "entity_type": "robot",
    "entity_id": "R-1",
    "revision": 123,
    "values": {"health_status": "HEALTHY"}
  }]
}
```

The complete context membership must be returned. The fingerprint covers
effective readiness values and maintenance membership; revisions also cover
scenario and registration changes. Stale snapshots return 409. Values are
validated against each context's allowed values. A multi-record repair,
optional explicit missing-maintenance registration, durable corrections, and
before/after history are committed atomically. There is no comment, proposal,
approval, or verification step. The response is the updated `FleetIssue`;
once all source blockers clear it has `status: "resolved"` and disappears from
the active list. Admin is read-only and Supervisor cannot use these routes.

## Supervisor monitoring sections

`GET /api/personas/workspace?section=discrepancies&limit=10&offset=0&q=...`
excludes replenishment alerts before paging and counting. Other intervention
kinds remain accessible, while role summary counts remain global. Omitting
`section` preserves the existing mixed-workspace contract.

`GET /api/personas/low-stock?limit=10&offset=0&q=...&status=active` returns
`items` grouped by warehouse/SKU and `pagination` with `limit`, `offset` and
`total`. `status` is either `active` (the default) or `closed`. Each item has
`id`, `warehouse_id`, `sku`, `priority`, an optional `aggregate_alert`, an
optional `alert` intervention for the warehouse/SKU condition, and an
`interventions` array containing location-specific replenishment issues.
`status=closed` keeps closing comments and event history discoverable after
refresh. Supervisor and Admin may inspect these alerts; only Supervisor may
close them.

An aggregate alert retains the fulfillment state alert's `available`,
`threshold` and optional `inventory_policy`. A null aggregate means only
location-specific issues remain actionable; it does not mean a warehouse-wide
shortage. Groups and location issues are not interchangeable stock scopes.
Search filters the complete collection before pagination, and both monitoring
sections maintain independent offsets.

### Direct low-stock closure

Every active warehouse/SKU `alert` and location entry in `interventions`
includes `manual_close` in `allowed_actions` for Supervisor. Close it directly
with the condition token returned on that exact alert:

```json
{
  "action": "manual_close",
  "reason": "Required closing comment",
  "evidence": {
    "condition_fingerprint": "token from alert.evidence.condition_fingerprint"
  }
}
```

The trimmed comment is required and limited to 2,000 characters. A missing
token returns 422. A changed condition/token, duplicate close, or already
closed alert returns 409. This direct action does not require investigation,
proposal, approval, verification, or a stock update.

The resolved intervention records `evidence.manual_closure` with the comment,
Supervisor role, timestamp, condition fingerprint, affected warehouse/SKU
(and location when applicable), and the effective inventory state reviewed.
The audit/event history records the same condition identity. Closing does not
change inventory sources, reservations, picked/completed quantities,
thresholds, orders, tasks, or fulfillment state.

Aggregate warehouse/SKU alerts use a durable intervention identity. Detection
suppresses an unchanged manually closed condition across polling and process
restart. If effective availability, threshold/policy, or relevant inventory
state materially changes while the condition remains low, the same identity
reopens with an incremented recurrence count and a new condition fingerprint.
If the low-stock condition recovers, the intervention resolves with a durable
`recovered` history event. A later low condition is a new recurrence even when
its values happen to match the condition from before recovery.
Underlying `aggregate_alert.available` remains the truthful fulfillment
calculation even while a reviewed intervention is hidden from the active list.

Location alert fingerprints likewise cover the configured threshold and
inventory policy as well as the exact effective inventory row. Detection
records recovery when that location is no longer below the current threshold.
The close endpoint independently checks the current threshold and inventory
state, so a token from a condition that has already recovered is rejected even
before the next workspace poll performs reconciliation.

## Manual inventory mismatch closure

Supervisors may send `{"action":"manual_close","reason":"Required closing comment"}`
to `POST /api/personas/interventions/{id}/actions` for an unresolved
`inventory_mismatch`. Comments are trimmed, nonempty and limited to 2,000
characters. The response uses the existing `resolved` status and records
`evidence.manual_closure` with the comment, supervisor role, timestamp and
post-update condition fingerprint and per-row `inventory_sync` before/after
quantities, plus an audit event.

Closing synchronizes the affected inventory location's app-owned WMS, ERP and
Vision free quantities to their current numeric maximum, atomically with closure.
Historical SKU-wide issues use each location's own maximum. Reserved and picked
quantities stay unchanged. This does not write to external WMS/ERP systems,
clear allocation blockers or run fulfillment.
Unchanged source conditions stay closed across polling; changed conditions may
reopen a detected issue. Other intervention kinds retain their existing flows.

> This reference retains historical intervention compatibility contracts.
> The current [CONTROL_TOWER.md](CONTROL_TOWER.md) adds location/source-specific
> corrections, free-versus-total quantity basis, replenishment issues and P1/P2
> held-work linkage. New structured proposals use the existing action lifecycle;
> historical scalar aggregate overlays are not the v2 inventory authority.

The persona API is a demo control surface. `X-Demo-Persona` is a role switcher,
not authentication. The accepted values are exactly `fleet`, `supervisor`, and
`admin`; the default is `supervisor`. The route is mounted at
`/api/personas`. Source snapshots are never rewritten.

## Workspace contract

`GET /api/personas/workspace` returns:

```json
{
  "persona": "supervisor",
  "summary": {"open": 0, "awaiting_approval": 0, "resolved": 0},
  "interventions": [],
  "capabilities": ["investigate", "propose", "approve", "verify", "handoff"],
  "assumptions": []
}
```

The optional `section` filter accepts `discrepancies`. The former
`section=fleet_reports` path is retired and returns HTTP 422. Existing fleet
intervention history remains available through the normal workspace and
intervention detail contracts.

Every intervention has this shape:

```json
{
  "id": "INT-...",
  "kind": "inventory_mismatch",
  "warehouse_id": "DC-01",
  "entity_id": "SKU-01146@DC-01-Z03-B017",
  "title": "Inventory mismatch: SKU-01146 at DC-01-Z03-B017",
  "description": "...",
  "owner": "supervisor",
  "status": "open",
  "evidence": {},
  "proposed_action": null,
  "created_at": "2030-01-01T00:00:00Z",
  "updated_at": "2030-01-01T00:00:00Z",
  "events": [
    {"at": "...", "persona": "system", "action": "detected",
     "reason": "Source discrepancy detected", "details": {}}
  ],
  "allowed_actions": ["investigate"]
}
```

`GET /api/personas/interventions/{id}` returns the same complete object. A
non-admin only sees interventions in its role scope. Admin can view all but has
no operational actions.

## Creating and acting

`POST /api/personas/interventions` accepts:

```json
{
  "kind": "resource_failure",
  "warehouse_id": "DC-01",
  "entity_id": "TS-...",
  "description": "Robot failed during the active pick",
  "evidence": {"source": "operator_report"}
}
```

Allowed creation kinds depend on the persona. Supervisors can create inventory,
priority, task conflict, and resource failure scenarios. Fleet manual creation
of `fleet_readiness`, `control_asset_readiness`, and `resource_failure` reports
is retired and returns HTTP 403. Fleet continues to act on automatically
detected readiness issues and internally recorded lifecycle incidents through
the existing action, repair, simulator, and recovery contracts; historical
records are not deleted.

`POST /api/personas/interventions/{id}/actions` always requires a non-empty
`reason`:

```json
{
  "action": "propose",
  "reason": "Physical count completed by the shift lead",
  "evidence": {"count_method": "cycle_count"},
  "value": 198,
  "assigned_to": null
}
```

Transitions are intentionally strict:

`open -> investigate -> investigating -> propose -> awaiting_approval ->
approve -> investigating -> verify -> resolved`.

`handoff` is available while a fleet-owned scenario is being investigated or
awaiting approval. It changes ownership to `supervisor` and leaves the
intervention operationally unresolved. Stale or terminal transitions return
HTTP 409. Unauthorized role/scope access returns HTTP 403. There is no reset
action.

### Proposal schemas by kind

All `propose` actions require a non-empty object `evidence`; `verify` actions
also require a non-empty evidence object. Values and effects are:

| kind | `value` | proposal | approval effect |
| --- | --- | --- | --- |
| `inventory_mismatch` | Non-negative number, or `{"physical_qty": number}` | `inventory_overlay` with `physical_qty` | Stores a durable POC ATP overlay for warehouse + SKU. Source WMS/ERP/vision rows remain unchanged. No automatic ground truth is selected. |
| `priority_override` | `"standard"`, `"high"`, or `"urgent"` | `priority_override`; evidence includes an `impacted_order_queue` preview | Updates only the matching existing POC order when it is `held`, `planned`, or `queued`. Running/completed orders are rejected with 409. Original order source rows are never changed. |
| `fleet_readiness` | `"hold"` or `"release"` | `safety_hold` for a known robot | `hold` writes a durable POC safety hold consulted by resource selection. `release` runs current safety validation and is rejected unless safe; it never fakes safety facts. |
| `task_completion_conflict` | Any JSON decision value (optional) | `record_verified_outcome` | Records the source discrepancy decision only. It never replays a historical task and never consumes stock. |
| `resource_failure` | Optional (normally omitted) | `pause_task`; `assigned_to` may name a replacement resource | The targeted running POC task enters persisted `paused` state with remaining seconds and the order is held. A supervisor handoff can assign a different recovery resource. Completed picks are never consumed again. |

The wire-level evidence objects are JSON objects (not strings). The backend
preserves additional keys, but the following are the exact POC keys used by
each workflow:

* `inventory_mismatch`: propose evidence
  `{"count_method": string, "verified_by": string, "verified_at": string}`
  and value `{"physical_qty": number}` (a number shorthand is also accepted);
  verify evidence
  `{"physical_qty": number, "verified_by": string, "verification": string}`.
* `priority_override`: propose evidence
  `{"business_reason": string, "requested_by": string, "expires_at": string|null}`
  and one of the three priority strings as value. The response's
  `proposed_action.impacted_order_queue` is the authoritative preview;
  no queue preview is accepted from the client.
* `fleet_readiness`: propose evidence
  `{"finding": string, "source": string, "safe_to_release": boolean|null}`
  and `"hold"` or `"release"` as value. Verify evidence
  `{"validation": string, "validated_by": string}` is required; release is
  independently checked against current robot and maintenance source state.
* `task_completion_conflict`: propose evidence
  `{"wes_status": string, "fleet_status": string, "decision_basis": string}`
  and a decision value such as `"physical_complete"` or
  `"source_baseline_retained"`. Verify evidence
  `{"physical_outcome": string, "source_discrepancy_decision": string,
  "verified_by": string}`. No executor call is made.
* `resource_failure`: propose evidence
  `{"failure_mode": string, "reported_by": string, "reported_at": string}`
  and optional `assigned_to` (a different recovery resource). Verify evidence
  `{"resume": boolean, "remaining_task_check": string, "verified_by": string}`
  and, when no replacement was assigned in the proposal, a different
  `assigned_to` is required when `resume` is true.

Recovery `assigned_to` is not an arbitrary string: it must be present in the
registered source/POC resource registry, belong to the task warehouse, be
stage-compatible, have enough source payload capacity where applicable, pass
current source safety and maintenance checks, have no durable safety hold, and
not collide with a primary or auxiliary claim. Approval uses the same planner
resource-selection policy for the current and every downstream stage; the
failed resource is durably excluded from both. A newly assigned task retains
the simulator's full configured duration (45 seconds by default).
`remaining_seconds` in the persisted pause record is inspection/audit metadata
for operators, not a shortened execution duration, and configuration changes
do not rewrite it.

Approving a durable fleet hold atomically invalidates pre-existing planned or
queued assignments that claim the held robot, including auxiliary claims,
releases their unconsumed POC reservations, and replans through the normal
planner. A running claim is paused before completion and downstream work stays
blocked or is safely replanned; no held robot can be acquired by a later
executor tick. Releasing a hold ignores only that robot's durable hold row and
still applies the underlying source maintenance, certification, health,
calibration, connectivity, and safety checks.

Inventory `verify` evidence should include the physical count and verifier.
Task conflict `verify` evidence should state the verified physical outcome and
source discrepancy decision. Resource failure recovery verification may include
`{"resume": true, "remaining_task_check": "..."}`; without `resume`, the task
remains safely pending/paused even though the intervention can be resolved.

### Recovery handoff `allowed_actions`

For a fleet-owned `resource_failure`:

1. Fleet: `investigate` (`open -> investigating`).
2. Fleet: `propose` with evidence (optional `assigned_to`) or `handoff`.
3. Fleet: `handoff` (`investigating` or `awaiting_approval` -> supervisor-owned
   `investigating`).
4. Supervisor: `propose` with evidence and, when needed, a different
   `assigned_to` recovery resource.
5. Supervisor: `approve` (pauses the running task; records remaining seconds).
6. Supervisor: `verify` with evidence; use `resume: true` only after safe
   remaining-task replanning. The task returns to the executor's queued state.

After approval, `allowed_actions` is `["verify", "handoff"]` (not `propose`);
before approval while investigating it is `["propose", "handoff"]`. Fleet
cannot approve. Admin's `allowed_actions` and `capabilities` are always empty.

## Admin-only endpoints

`GET /api/personas/audit` returns `{ "events": [...] }` and
`GET /api/personas/policy` returns `{ "roles": [...] }`; both require the admin
persona. The policy is descriptive and does not turn the demo header into
secure RBAC.

`POST /api/personas/resources/{dataset}` accepts
`{"values": {...}}` and is admin-only. Supported datasets are exactly
`warehouses`, `skus`, `robots`, and `control_assets`. Identity fields are
required and unique (`warehouse_id`, `sku`, `robot_id`, or `asset_id`).
Robot/control-asset warehouse references must exist. Unknown fields and active
POC plans are rejected. Registered rows are stored in `registered_resources`,
appended after immutable source rows, and are visible to fulfillment catalog,
resource metadata, planner input, and source indexes. Scenario reset removes
only scenario overlays; it never removes registered rows. Registration is
rejected while a planned, queued, or running POC order exists.

## Detection

The first workspace refresh inspects all supplied inventory, task, robot, and
maintenance rows. It creates deduplicated inventory mismatches (WMS/ERP/vision),
task WES/fleet or robot-site conflicts, and unsafe claimed fleet availability.
Historical rows do not create synthetic outages or consume stock. A persistent
detection revision marker avoids rescanning all rows on every workspace poll;
the full scan runs again after a scenario revision or registration.