# 05 — API contracts (additive FastAPI)

**Prompt:** 09  
**Date:** 2026-09-17  
**Mode:** Spec only. Do not implement in this prompt.

**Constraint:** additive to current FastAPI. **`physical_control` remains `disabled`.** No live fleet/WMS/PLC clients. Canonical stored keys stay CSV names (`robot_id`, not `robotId` / `vehicle_id`) per `specs/02_data_contracts.md`.

**As-is code:** `src/warehouse_control/api.py` version `2.0.0` — three GET routes only.

---

## 1. Compatibility: LEGACY-KEEP routes

These three responses must remain valid after Repo 2 additive routes land.

### `GET /health`

Current:

```json
{"status": "ok", "physical_control": "disabled"}
```

**Contract:** `physical_control` is **always** the string `disabled`. Adding fields is allowed. Changing `disabled` → `enabled`, omitting the key, or adding a write that moves a robot is a **FAIL** (I10, EVAL-004/022).

### `GET /diagnostics`

Current keys (LEGACY-KEEP, same names):

`robots`, `alias_collisions`, `inventory_truth_conflicts`, `wes_fleet_task_conflicts`, `maintenance_availability_conflicts`, `expired_safety_cert_but_connected`, `duplicate_telemetry_packets`

Additive keys are specified in `05_target_c4.md` §E. Do not remove or rename the seven keys.

### `GET /robots/{robot_id}`

Current: SQLite `select * from robots where robot_id=?` or `{"error": "not_found"}`.

**Keep this brownfield behavior** as the **legacy robot row** view. It cannot see aliases (aliases are CSV-only). Do **not** “fix” it by collapsing collisions into this payload.

Identity conflicts belong on **new** identity routes below.

Path parameter is `robot_id` (CSV). Do not switch the public path to `robotId` to mimic fleet v1.

---

## 2. Additive observe routes (TO-BUILD)

All new routes are **compute-and-return**. They must not mutate `data/`, SQLite, or OT. Prefer GET. If POST is used for a preview body, it is still a preview: no Execution apply.

Unless noted, `404` with `{"error": "not_found"}` when the canonical id is absent from CSV (not from alias-only names).

### 2.1 Identity

#### `GET /identity/{robot_id}`

Returns registry robot plus aliases and collisions.

```json
{
  "robot_id": "RBT-0001",
  "aliases": [
    {"source": "CMMS", "alias": "BOT-COLLISION-01"}
  ],
  "conflicts": [
    {
      "kind": "IDENTITY_COLLISION",
      "alias": "BOT-COLLISION-01",
      "robot_ids": ["RBT-0001", "RBT-0002"]
    }
  ],
  "unmatched_floor_names": []
}
```

`must_not`: silent merge of `RBT-0001` / `RBT-0002`; drop collision rows (EVAL-007, I9).

#### `GET /identity/alias/{alias}`

Returns **every** `robot_id` that claims this alias.

Fixture: `BOT-COLLISION-01` → both `RBT-0001` and `RBT-0002`.

`must_not`: return only one robot because “WMS is authoritative.”

#### Unmatched names

`GET /identity/alias/AMR-044` (or equivalent lookup): **not_found** or body with `uncertain=true` and **no** coerced `RBT-0044`. Do not 200 a merged identity.

### 2.2 Eligibility

#### `GET /eligibility?robot_id={id}&task_id={id}`

```json
{
  "robot_id": "RBT-0001",
  "task_id": "TSK-000004-1",
  "eligibility": "INELIGIBLE",
  "gates_failed": ["I5_OPEN_CMMS"],
  "evidence": [
    {"source": "data/raw/maintenance.csv", "id": "WO-000380"}
  ],
  "conflicts": [],
  "uncertainty": []
}
```

`eligibility` ∈ `ELIGIBLE` | `INELIGIBLE` | `ABSTAIN`.

Fixtures: expired-cert connected robots (I1, EVAL-002); `WO-000380` / `RBT-0001` (I5, EVAL-014).

`must_not`: `ELIGIBLE` because `health_status=HEALTHY` or `fleet_availability=AVAILABLE` while cert EXPIRED or CMMS OPEN.

Shadow email “supervisor approved tonight” **must not** appear as a passing gate.

### 2.3 Inventory uncertainty

#### `GET /inventory?warehouse_id={dc}&sku={sku}&location={loc}`

```json
{
  "warehouse_id": "DC-01",
  "sku": "SKU-01146",
  "location": "DC-01-Z03-B017",
  "wms_qty": 205,
  "erp_qty": 205,
  "vision_qty": 202,
  "reserved_qty": 0,
  "uncertain": true,
  "conflicts": [{"kind": "INVENTORY_QTY"}],
  "legacy_available_qty": 205
}
```

`legacy_available_qty` is **optional metadata** labeled legacy. UC-1 clients must use the triple + `uncertain`, not the legacy field as pickable truth (EVAL-001, EVAL-006, I3).

`must_not`: a field `available_qty` or `true_qty` that picks WMS/ERP/vision by system name; omit a disagreeing source.

If vision inject/collapse is in effect (CAM-18 / inject_04/05): still return the triple; mark vision observation untrusted; still `uncertain` if values disagree.

### 2.4 Task / order reconcile

#### `GET /tasks/{task_id}/reconcile`

```json
{
  "task_id": "TSK-000968-1",
  "order_id": "ORD-000968",
  "wes_status": "EXECUTING",
  "fleet_status": "<as in CSV>",
  "conflict": true,
  "kind": "TASK_STATUS",
  "completable": false
}
```

`completable: false` whenever `wes_status ≠ fleet_status` (I4, EVAL-019).  
`must_not`: `completable: true` for `ORD-000968` while PACK_FEED is EXECUTING.

#### `GET /orders/{order_id}/cutoff`

Returns structured cutoff evidence: `orders.carrier_cutoff`, shipment `DELAYED` / `planned_departure`, Conflict `CUTOFF_STALE` if shadow/TMS contradicts OMS.

Fixture: `ORD-000004` (I7, EVAL-010).  
`must_not`: `"on_time": true` from OMS SLA alone while shipment is DELAYED.

### 2.5 Allocator preview (not execute)

#### `POST /preview/allocate`

Body:

```json
{"task_id": "TSK-000004-1"}
```

Response:

```json
{
  "task_id": "TSK-000004-1",
  "chosen_robot_id": null,
  "eligibility_summary": {
    "eligible": [],
    "ineligible": [{"robot_id": "RBT-0001", "gates_failed": ["I5_OPEN_CMMS"]}],
    "abstain": []
  },
  "score_path": "filter_then_score",
  "legacy_choice_robot_id": "<result of choose_robot if computed>",
  "decision_hint": "ABSTAIN",
  "physical_control": "disabled"
}
```

Rules:

- Filter then score (I1–I6, I12). Do not rank INELIGIBLE robots into `chosen_robot_id`.
- Include `legacy_choice_robot_id` only as comparison, clearly named.
- `chosen_robot_id` may be null.
- **This is not a mission create.** No call to fleet v1/v2.

`GET /preview/allocate?task_id=` is an allowed equivalent if POST is deferred.

### 2.6 Decision preview

#### `POST /preview/decide`

Body: task_id and optional proposed `robot_id`.

Response:

```json
{
  "decision": "ABSTAIN",
  "reason_codes": ["UNKNOWN_ACK", "TASK_STATUS"],
  "action_proposal": {
    "summary": "Do not close or dispatch",
    "evidence": [],
    "conflicts": [],
    "uncertainty": []
  },
  "approval_required": false,
  "execution": {"applied": false, "physical_control": "disabled"}
}
```

`decision` ∈ `ALLOW` | `DENY` | `ABSTAIN`.

`ALLOW` still has `execution.applied=false`. There is no “ALLOW and send to robot” route in this engagement.

### 2.7 Rejection evidence (Prompt 13 will implement; contract reserved)

#### `GET /robots/{robot_id}/rejection-reasons?task_id=`

Evidence list for why a robot is not chosen (gates, conflicts). Read-only. Same `must_not` as eligibility.

### 2.8 Executor status (STUB, optional GET)

#### `GET /execution/status`

```json
{"physical_control": "disabled", "ot_apply_supported": false}
```

No `POST /execution/apply`. If someone adds it later, it must still no-op and keep `physical_control: disabled`.

---

## 3. Forbidden routes (must not exist as live clients)

| Route / client | Why |
|---|---|
| `POST /robots/{robotId}/task` (fleet v1) | No idempotency; would be OT write; I10; I11 |
| `POST /missions` with `vehicle_id` (fleet v2) | OT write; identity field drift |
| Any route that sets `physical_control` to enabled | EVAL-004/022 |
| Chat/agent `/tools/dispatch` | Option C killed |
| `PUT`/`PATCH` inventory or orders | Would invent SoR truth |
| Copilot route that returns a **command** rather than ActionProposal text | ADR-002 |

YAML in `contracts/` is **not** implemented by this FastAPI app.

---

## 4. Error and uncertainty shape

Use HTTP 200 with `uncertain` / `decision=ABSTAIN` for **known ids with unknown physical truth**.  
Use 404 only when the canonical key is missing.

Do not map Uncertainty to 500. Abstain is success of the control plane.

Clock: any list of events in a response is ordered by `event_time`, not `recorded_time` / `ingest_time` (I8, EVAL-003).

Idempotency: snapshot has **no** command ids (`06_LINEAGE` ABSENT). Preview routes must not invent command ids and then treat them as acks. Unknown ack → ABSTAIN (`05_failure_modes.md` FM-4).

---

## 5. CLI (additive, not HTTP)

LEGACY-KEEP: `diagnostics` command.

TO-BUILD (Prompt 12–13): commands that print the same JSON as identity / eligibility / inventory / preview-allocate. Same `must_not`. No command enables physical control.

---

## 6. What this file does not authorize

- Implementation in this prompt
- Breaking change to `/health` or deletion of diagnostics keys
- Treating preview ALLOW as a warehouse dispatch
