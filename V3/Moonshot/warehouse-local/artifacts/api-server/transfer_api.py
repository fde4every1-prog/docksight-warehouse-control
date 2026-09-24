"""HTTP boundary for frozen, upload-driven DC-01 transfer batching."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from transfer_engine import compare, validate_plan
from transfer_import import MAX_BYTES, WorkbookError, normalize, parse_xlsx, sample_rows, template_bytes
from transfer_snapshot import SnapshotError, create_snapshot, get_snapshot, public_snapshot

router = APIRouter(prefix="/api/batching/transfer", tags=["transfer-batching"])
SCENARIO_TTL = 1800
MAX_SCENARIOS = 64
MAX_LLM_CONTEXT_BYTES = 180_000
MAX_PROVIDER_ATTEMPTS = 3
TRANSIENT_PROVIDER_STATUSES = {408, 409, 429, 500, 502, 503, 504}
_lock = threading.Lock()
_suggest_lock = threading.Lock()
_scenarios: dict[str, tuple[float, dict[str, Any]]] = {}


class RowPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_id: str = Field(min_length=1, max_length=40)
    order_id: str | None = Field(None, min_length=1, max_length=120)
    order_cutoff: str | None = Field(None, min_length=1, max_length=80)


class ReviewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    rows: list[RowPatch] = Field(default_factory=list, max_length=500)
    selected_robot_ids: list[str] | None = Field(None, max_length=500)


class RevisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class CompareBody(RevisionBody):
    recommendation_id: str = Field(min_length=1, max_length=100)


class ValidateBody(RevisionBody):
    plan: dict[str, Any]


def _purge() -> None:
    now = time.monotonic()
    for key in [key for key, value in _scenarios.items() if value[0] <= now]:
        _scenarios.pop(key, None)


def _snapshot_is_expired(scenario: dict[str, Any]) -> bool:
    value = scenario.get("snapshot", {}).get("expires_at")
    try:
        expires = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    return expires.tzinfo is None or expires.utcoffset() is None or expires <= datetime.now(timezone.utc)


def _live_entry(scenario_id: str) -> dict[str, Any]:
    entry = _scenarios.get(scenario_id)
    if not entry:
        raise HTTPException(404, "Scenario is unknown or expired; upload again.")
    scenario = entry[1]
    if _snapshot_is_expired(scenario):
        _scenarios.pop(scenario_id, None)
        raise HTTPException(409, "Scenario snapshot expired; upload again.")
    return scenario


def _get(scenario_id: str) -> dict[str, Any]:
    with _lock:
        _purge()
        return copy.deepcopy(_live_entry(scenario_id))


def _put(scenario: dict[str, Any]) -> None:
    with _lock:
        _purge()
        _scenarios[scenario["scenario_id"]] = (
            time.monotonic() + SCENARIO_TTL,
            copy.deepcopy(scenario),
        )
        while len(_scenarios) > MAX_SCENARIOS:
            oldest = min(_scenarios, key=lambda key: _scenarios[key][0])
            _scenarios.pop(oldest, None)


def _replace_if_revision(
    scenario_id: str,
    expected_revision: int,
    replacement: dict[str, Any],
) -> dict[str, Any]:
    with _lock:
        _purge()
        current = _live_entry(scenario_id)
        if current["revision"] != expected_revision:
            raise HTTPException(409, "Scenario revision changed; reload before editing.")
        stored = copy.deepcopy(replacement)
        _scenarios[scenario_id] = (time.monotonic() + SCENARIO_TTL, stored)
        return copy.deepcopy(stored)


def _store_recommendation_if_revision(
    scenario_id: str,
    expected_revision: int,
    key: str,
    result: dict[str, Any],
) -> None:
    with _lock:
        _purge()
        current = _live_entry(scenario_id)
        if current["revision"] != expected_revision:
            raise HTTPException(409, "Scenario revision changed while generating recommendation; retry.")
        current["recommendations"][key] = copy.deepcopy(result)
        _scenarios[scenario_id] = (time.monotonic() + SCENARIO_TTL, current)


def _review(scenario: dict[str, Any]) -> dict[str, Any]:
    snapshot = scenario["snapshot"]
    selected = set(scenario["selected_robot_ids"])
    selected_robots = [r for r in snapshot["robots"] if r["id"] in selected]
    blockers = list(scenario["row_blockers"])
    eligible_ids = {r["id"] for r in snapshot["robots"] if r["eligible"]}
    if selected != eligible_ids:
        blockers.append("Server-owned fleet selection must contain every eligible frozen DC-01 robot.")
    blockers.extend(
        f"{robot['id']}: {reason}" for robot in selected_robots for reason in robot["exclusion_reasons"]
    )
    if not any(
        robot["eligible"]
        and {"pick", "transfer"}.issubset(set(robot["capabilities"]))
        for robot in selected_robots
    ):
        blockers.append("Eligible fleet includes no robot with both pick and transfer capabilities.")
    blockers.extend(snapshot["blockers"])
    return {
        "scenario_id": scenario["scenario_id"], "snapshot_id": snapshot["snapshot_id"],
        "revision": scenario["revision"], "valid": not blockers,
        "ready_for_planning": not blockers, "rows": copy.deepcopy(scenario["rows"]),
        "errors": [], "blockers": list(dict.fromkeys(blockers)), "map": copy.deepcopy(snapshot["map"]),
        "robots": copy.deepcopy(snapshot["robots"]), "selected_robot_ids": list(scenario["selected_robot_ids"]),
        "clock": copy.deepcopy(snapshot["clock"]), "mode": snapshot["mode"],
        "snapshot": {key: snapshot[key] for key in ("snapshot_at", "expires_at", "source_version")},
        "assumptions": copy.deepcopy(snapshot["assumptions"]),
    }


def _planning_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    review = _review(scenario)
    if not review["ready_for_planning"]:
        raise HTTPException(422, {"code": "SCENARIO_BLOCKED", "message": "Resolve review blockers before planning.",
                                  "errors": review["blockers"]})
    return review


@router.get("/preview")
def preview(mode: str = Query("live", pattern="^(live|synthetic_demo)$")):
    try:
        return public_snapshot(create_snapshot(mode))
    except SnapshotError as exc:
        raise HTTPException(503, str(exc)) from None


def _snapshot_or_new(snapshot_id: str | None) -> dict[str, Any]:
    try:
        return get_snapshot(snapshot_id) if snapshot_id else create_snapshot("live")
    except SnapshotError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/sample")
def sample(snapshot_id: str | None = Query(None, max_length=100)):
    snapshot = _snapshot_or_new(snapshot_id)
    try:
        rows = sample_rows(snapshot)
    except WorkbookError as exc:
        raise HTTPException(422, {"code": exc.code, "message": exc.message, "errors": exc.errors}) from None
    return {"snapshot_id": snapshot["snapshot_id"], "headers": ["Order ID", "SKU", "Qty", "Order Cut-off"],
            "rows": rows, "notes": ["Rows are examples only; identifiers and bins come from frozen eligible stock.",
                                    "Cut-offs are explicit UTC values relative to the frozen simulation clock."]}


@router.get("/template")
def template(snapshot_id: str | None = Query(None, max_length=100)):
    snapshot = _snapshot_or_new(snapshot_id)
    try:
        content = template_bytes(snapshot)
    except WorkbookError as exc:
        raise HTTPException(422, {"code": exc.code, "message": exc.message, "errors": exc.errors}) from None
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="dc01-transfer-orders.xlsx"',
                             "X-Snapshot-Id": snapshot["snapshot_id"]})


@router.post("/imports")
async def import_workbook(request: Request, snapshot_id: str = Query(..., min_length=1, max_length=100)):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BYTES:
        raise HTTPException(413, {"code": "FILE_TOO_LARGE", "message": "Workbook exceeds the 2 MiB limit."})
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, {"code": "FILE_TOO_LARGE", "message": "Workbook exceeds the 2 MiB limit."})
    try:
        snapshot = get_snapshot(snapshot_id)
        raw_rows = parse_xlsx(data)
        rows, blockers = normalize(raw_rows, snapshot)
    except SnapshotError as exc:
        raise HTTPException(409, str(exc)) from None
    except WorkbookError as exc:
        raise HTTPException(422, {"code": exc.code, "message": exc.message, "errors": exc.errors}) from None
    scenario = {"scenario_id": "TR-" + uuid.uuid4().hex, "snapshot": snapshot, "revision": 1,
                "raw_rows": raw_rows, "rows": rows, "row_blockers": blockers,
                "selected_robot_ids": list(snapshot["selected_robot_ids"]), "recommendations": {}}
    _put(scenario)
    return _review(scenario)


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    return _review(_get(scenario_id))


@router.patch("/scenarios/{scenario_id}/rows")
def patch_rows(scenario_id: str, body: ReviewPatch):
    scenario = _get(scenario_id)
    if scenario["revision"] != body.revision:
        raise HTTPException(409, "Scenario revision changed; reload before editing.")
    raw_by_id = {row["row_id"]: row for row in scenario["raw_rows"]}
    seen = set()
    for patch in body.rows:
        if patch.row_id in seen:
            raise HTTPException(422, f"Duplicate patch for {patch.row_id}.")
        seen.add(patch.row_id)
        raw = raw_by_id.get(patch.row_id)
        if raw is None:
            raise HTTPException(422, f"Unknown row_id {patch.row_id}.")
        changes = patch.model_fields_set
        if "order_id" in changes:
            raw["order_id"] = patch.order_id.strip() if patch.order_id else None
        if "order_cutoff" in changes:
            raw["order_cutoff_raw"] = patch.order_cutoff
    if body.selected_robot_ids is not None:
        authoritative = set(scenario["snapshot"]["selected_robot_ids"])
        supplied = set(body.selected_robot_ids)
        if len(supplied) != len(body.selected_robot_ids) or supplied != authoritative:
            raise HTTPException(
                422,
                "Robot selection is server-owned and must exactly equal all eligible frozen DC-01 robots.",
            )
        scenario["selected_robot_ids"] = list(scenario["snapshot"]["selected_robot_ids"])
    rows, blockers = normalize(scenario["raw_rows"], scenario["snapshot"])
    scenario["rows"], scenario["row_blockers"] = rows, blockers
    scenario["revision"] += 1
    scenario["recommendations"].clear()
    stored = _replace_if_revision(scenario_id, body.revision, scenario)
    return _review(stored)


def _llm_context(review: dict[str, Any]) -> dict[str, Any]:
    selected_robots = [r for r in review["robots"] if r["id"] in review["selected_robot_ids"]]
    order_weights: dict[str, float] = {}
    for row in review["rows"]:
        order_weights[row["order_id"]] = order_weights.get(row["order_id"], 0.0) + row["total_weight_kg"]
    batch_robot_capacities = {
        r["id"]: r["capacity_kg"] for r in selected_robots
        if r["eligible"] and {"pick", "transfer"}.issubset(set(r["capabilities"]))
    }
    feasible_by_order = {
        oid: {
            "weight_kg": weight,
            "batch_robot_ids": sorted(
                rid for rid, capacity in batch_robot_capacities.items() if capacity >= weight
            ),
        }
        for oid, weight in order_weights.items()
    }
    return {
        "scenario_id": review["scenario_id"], "clock": review["clock"], "map": review["map"],
        "orders": review["rows"],
        "robots": selected_robots,
        "validation_facts": {
            "order_payload_kg": order_weights,
            "line_id_is_exact_row_id": {row["row_id"]: {
                "order_id": row["order_id"], "sku": row["sku"],
                "allocations": row["allocations"],
            } for row in review["rows"]},
            "eligible_dual_capability_robot_capacities_kg": batch_robot_capacities,
            "concrete_feasible_robots_per_order": feasible_by_order,
        },
        "constraints": {
            "selected_robot_ids": review["selected_robot_ids"], "conveyor_node": review["map"]["conveyor"]["node_id"],
            "pick_seconds_per_stop": 7,
            "transfer_service": "45 + 22.5 * (order_count - 1)",
            "transfer_phase_includes": ["travel from final pick to conveyor", "point-in-time conveyor receipt"],
            "conveyor_receipt": "No occupancy or extra service stage; independent transfers may overlap and simultaneous completion is allowed.",
            "donor_claim": "donor_robot_id must always be null; split-robot transfers are prohibited.",
            "resource_requirement": "One eligible robot with both pick and transfer capabilities must pick the entire batch and transfer it; its capacity must cover the cumulative batch payload.",
            "trip_shape": "Each batch is one trip: collect its assigned orders one by one in order_sequence, then perform its one final transfer. A singleton follows the same normal pick-then-transfer trip.",
            "batching_priority": "Prefer multi-order batches; singleton orders are a last resort. Evaluate feasible merges and regroupings across the full order set before leaving an order alone. Do not split compatible orders merely to use more robots or improve makespan at the expense of batching.",
            "singleton_justification": "For each singleton, its rationale must state the concrete capacity, dual-capability eligibility, deadline, batch-size limit, or unavoidable remaining-order constraint that prevented batching. Check alternative robots and regroupings first. Never force an infeasible merge or omit an order to avoid a singleton.",
            "parallelism": "Assign independent batches to distinct feasible resources so they can begin in parallel when possible; do not force four assignments or any fixed parallel count when fleet capability, capacity, readiness, or deadlines do not support it.",
            "allowed_actions_in_order": ["pick", "transfer"],
            "all_orders_must_be_scheduled_or_explicitly_excluded": True,
            "exclusion_policy": "Exclude only when no capacity-feasible dual-capability robot exists or the order provably cannot meet its cut-off even standalone (7 seconds per frozen pick allocation plus 45 seconds transfer).",
            "objective_lexicographic": [
                "maximize completed order count", "meet earliest deadlines",
                "improve transfer service through feasible batching", "minimize makespan",
            ],
        },
    }


def _plan_response_schema() -> dict[str, Any]:
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    nullable_integer = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    stop = {
        "type": "object", "additionalProperties": False,
        "required": ["sequence", "action", "robot_id", "node_id", "line_id",
                     "inventory_source_id", "bin_id", "quantity", "order_ids", "donor_robot_id"],
        "properties": {
            "sequence": {"type": "integer", "minimum": 1},
            "action": {"type": "string", "enum": ["pick", "transfer"]},
            "robot_id": {"type": "string"}, "node_id": {"type": "string"},
            "line_id": nullable_string, "inventory_source_id": nullable_string,
            "bin_id": nullable_string, "quantity": nullable_integer,
            "order_ids": {"type": "array", "items": {"type": "string"}},
            "donor_robot_id": nullable_string,
        },
    }
    batch = {
        "type": "object", "additionalProperties": False,
        "required": ["batch_id", "order_ids", "transfer_robot_id", "pick_robot_ids",
                     "execution_order", "order_sequence", "stops", "rationale"],
        "properties": {
            "batch_id": {"type": "string"}, "order_ids": {"type": "array", "items": {"type": "string"}},
            "transfer_robot_id": {"type": "string"},
            "pick_robot_ids": {"type": "array", "minItems": 1, "maxItems": 1, "items": {"type": "string"}},
            "execution_order": {"type": "integer", "minimum": 1},
            "order_sequence": {"type": "array", "items": {"type": "string"}},
            "stops": {"type": "array", "items": stop}, "rationale": {"type": "string"},
        },
    }
    return {
        "type": "object", "additionalProperties": False, "required": ["summary", "plan"],
        "properties": {
            "summary": {"type": "string"},
            "plan": {
                "type": "object", "additionalProperties": False,
                "required": ["batches", "excluded_orders"],
                "properties": {
                    "batches": {"type": "array", "items": batch},
                    "excluded_orders": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["order_id", "reason"],
                        "properties": {"order_id": {"type": "string"}, "reason": {"type": "string"}},
                    }},
                },
            },
        },
    }


def _provider_error(status_code: int, code: str, message: str, attempts: int) -> HTTPException:
    return HTTPException(status_code, {
        "code": code,
        "message": message,
        "errors": [],
        "request_provenance": {
            "provider_attempts": attempts,
            "fallback_substituted": False,
        },
    })


def _repair_feedback(errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep repair prompts bounded while retaining error types and representative paths."""
    counts = Counter(
        str(error.get("code", "UNKNOWN"))
        for error in errors
        if isinstance(error, dict)
    )
    return {
        "error_count": len(errors),
        "code_counts": dict(sorted(counts.items())),
        "errors": errors[:60],
        "errors_truncated": max(0, len(errors) - 60),
        "instruction": (
            "Fix every occurrence, including unsampled occurrences represented by code_counts. "
            "Preserve exact order membership, allocations, quantities, capacities, cut-offs, and frozen IDs."
        ),
    }


def _request_llm(
    context: dict[str, Any],
    repair_errors: list[dict[str, Any]] | None = None,
    previous_plan: dict[str, Any] | None = None,
    provider_trace: dict[str, int] | None = None,
) -> dict[str, Any]:
    base, key = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"), os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
    if not base or not key:
        raise HTTPException(503, "AI integration is not configured. No recommendation was generated.")
    context_json = json.dumps(context, separators=(",", ":"))
    if len(context_json.encode()) > MAX_LLM_CONTEXT_BYTES:
        raise HTTPException(413, "Normalized scenario exceeds the bounded AI context; reduce the workbook.")
    system = (
        "You are a transfer batching planner, not a dispatcher. Return ONLY a JSON object with summary and plan. "
        "plan has batches and excluded_orders. Every batch requires batch_id, order_ids, transfer_robot_id, "
        "pick_robot_ids (exactly one ID), execution_order (unique contiguous values from 1), order_sequence, rationale, and stops. Stops are an exact contiguous "
        "sequence of {sequence,action,robot_id,node_id,line_id?,inventory_source_id?,bin_id?,quantity?,order_ids?}; "
        "each pick must exactly copy its allocation's inventory_source_id, bin_id, node_id and quantity; the ONLY "
        "actions are picks followed by one final transfer. Pick every supplied allocation quantity at its node. "
        "The same one robot must perform every pick and the final transfer, must have BOTH pick and transfer "
        "capabilities, and must carry the cumulative batch load within capacity. Transfer-only TUGGER/PALLET_MOVER "
        "and pick-only robots cannot execute a batch, even as a pair. Split-robot assignment is prohibited. "
        "Conveyor receipt has no occupancy or extra service stage: independent transfer phases may overlap and "
        "simultaneous arrivals are allowed. "
        "donor_robot_id MUST always be null. The transfer stop node_id must be the conveyor and "
        "consumes exactly 45+22.5*(order_count-1) seconds. Never emit handoff or deliver stops. Genuinely "
        "choose batch membership and order/bin sequence from topology, deadlines, stock, capacities and readiness. "
        "Assign the SAME eligible dual-capability robot to pick and transfer every batch; there is no specialist "
        "or donor fallback. Treat each batch as one trip: collect every allocation for each assigned order one order at a "
        "time in order_sequence, then perform the single final transfer. Singleton batches use that same normal "
        "pick-then-transfer trip. Assign independent batches to distinct feasible resources so their work can run "
        "in parallel when possible. Do not force four assignments, four batches, or any fixed parallel count when "
        "capability, capacity, readiness, topology, or deadlines make that infeasible. "
        "IMPORTANT identity rule: for every pick, line_id MUST equal the exact row_id shown in "
        "validation_facts.line_id_is_exact_row_id, and inventory_source_id/bin_id/node_id/quantity MUST be copied "
        "from that line's exact allocation. Sum order_payload_kg before batching and never assign a batch above the "
        "chosen dual-capability robot's capacity. Do not confuse an order's "
        "weight with a robot capacity: use concrete_feasible_robots_per_order, then RECOMPUTE AND SELF-CHECK each "
        "candidate batch's summed weight against the chosen robot capacity before returning it. "
        "Actively seek the best feasible multi-order batching across the full order set. Avoid singleton orders unless "
        "necessary: compare feasible merges, alternative dual-capability robots, and regroupings before finalizing. "
        "Do not leave compatible orders separate merely to use more robots or achieve a shorter makespan at the "
        "expense of batching. For EVERY remaining singleton, explain in its rationale the concrete constraint "
        "(combined payload, robot eligibility, deadline, maximum batch size, or unavoidable remaining order) "
        "that prevents grouping it; identify the relevant weights, capacities, or timing evidence. "
        "A singleton remains valid when grouping is infeasible; never force an infeasible batch or omit an order. "
        "For non-applicable strict-schema stop fields return null, and use [] for "
        "non-applicable order_ids. "
        "Never invent IDs, omit quantities, overlap membership, or silently omit an order; excluded_orders entries "
        "need order_id and reason and are permitted only if that order has no capacity-feasible dual-capability robot "
        "or cannot meet its cut-off even standalone using 7 seconds per frozen pick allocation plus 45 seconds transfer. "
        "Optimize lexicographically: maximize completed orders first, then deadlines, then service batching, "
        "then makespan. Do not claim global optimality. A slower makespan can be an honest batching trade-off when it "
        "reduces transfer service, but do not make assignments that are slower without any measured service benefit. "
        "Keep summary/rationale concise."
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": context_json}]
    if repair_errors is not None:
        messages.extend([
            {"role": "assistant", "content": json.dumps({
                "summary": "Prior proposal requiring repair.",
                "plan": previous_plan,
            }, separators=(",", ":"))},
            {"role": "user", "content": json.dumps({"repair": _repair_feedback(repair_errors)},
                                                   separators=(",", ":"))},
        ])
    payload = {"model": "gpt-5.4-mini", "max_completion_tokens": 16384,
               "response_format": {"type": "json_schema", "json_schema": {
                   "name": "dc01_transfer_plan", "strict": True, "schema": _plan_response_schema(),
               }},
                "messages": messages}
    request_data = json.dumps(payload).encode()
    for attempt in range(1, MAX_PROVIDER_ATTEMPTS + 1):
        if provider_trace is not None:
            provider_trace["attempts"] = provider_trace.get("attempts", 0) + 1
        request = URLRequest(
            base.rstrip("/") + "/chat/completions",
            data=request_data,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                result = json.loads(response.read(500_000))
            choice = result["choices"][0]
            finish_reason = choice.get("finish_reason")
            if finish_reason != "stop":
                code = "AI_OUTPUT_TRUNCATED" if finish_reason == "length" else "AI_OUTPUT_INCOMPLETE"
                raise _provider_error(
                    502, code,
                    f"AI structured output did not complete (finish_reason={finish_reason!s}); no fallback was substituted.",
                    attempt,
                )
            output = json.loads(choice["message"]["content"])
            if (not isinstance(output, dict) or not isinstance(output.get("summary"), str)
                    or not isinstance(output.get("plan"), dict)):
                raise ValueError("shape")
            return output
        except HTTPException:
            raise
        except HTTPError as exc:
            if exc.code in TRANSIENT_PROVIDER_STATUSES and attempt < MAX_PROVIDER_ATTEMPTS:
                time.sleep(0.25 * (2 ** (attempt - 1)))
                continue
            raise _provider_error(
                502, "AI_PROVIDER_ERROR",
                f"AI provider failed (HTTP {exc.code}) after {attempt} attempt(s); no fallback was substituted.",
                attempt,
            ) from None
        except (URLError, TimeoutError):
            if attempt < MAX_PROVIDER_ATTEMPTS:
                time.sleep(0.25 * (2 ** (attempt - 1)))
                continue
            raise _provider_error(
                504, "AI_PROVIDER_TIMEOUT",
                f"AI provider timed out after {attempt} attempts; no fallback was substituted.",
                attempt,
            ) from None
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise _provider_error(
                502, "AI_MALFORMED_STRUCTURED_OUTPUT",
                "AI returned malformed structured output; no fallback was substituted.",
                attempt,
            ) from None


def _quality_score(comparison: dict[str, Any]) -> tuple[int, int, float, float]:
    """Lexicographic measured objectives; lower is better and makes no optimality claim."""
    metrics = comparison["proposed"]["metrics"]
    return (
        -int(metrics["completed_order_count"]),
        int(metrics["deadline_misses"]),
        float(metrics["transfer_service_seconds"]),
        float(metrics["overall_completion_seconds"]),
    )


@router.post("/scenarios/{scenario_id}/suggest")
def suggest(scenario_id: str, body: RevisionBody):
    scenario = _get(scenario_id)
    if scenario["revision"] != body.revision:
        raise HTTPException(409, "Scenario revision changed; reload before suggesting.")
    planning = _planning_scenario(scenario)
    captured_revision = scenario["revision"]
    context = _llm_context(planning)
    key = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    if key in scenario["recommendations"]:
        current = _get(scenario_id)
        if current["revision"] != captured_revision:
            raise HTTPException(409, "Scenario revision changed; reload before suggesting.")
        return copy.deepcopy(current["recommendations"].get(key) or scenario["recommendations"][key])
    if not _suggest_lock.acquire(blocking=False):
        raise HTTPException(429, "A transfer recommendation is already being generated; retry shortly.")
    try:
        provider_trace: dict[str, int] = {"attempts": 0}
        output = _request_llm(context, provider_trace=provider_trace)
        verdict = validate_plan(planning, output["plan"])
        planning_attempts = 1
        original_output, original_verdict = output, verdict
        original_comparison = compare(planning, output["plan"]) if verdict["valid"] else None
        quality_repair = bool(
            original_comparison
            and original_comparison["quality"]["label"] == "dominated_by_baseline"
        )
        quality_baseline = original_comparison["baseline"]["metrics"] if quality_repair else None
        quality_proposed = original_comparison["proposed"]["metrics"] if quality_repair else None
        repair_errors = verdict["errors"] if not verdict["valid"] else ([{
            "code": "QUALITY_DOMINATED_BY_BASELINE",
            "path": "",
            "message": (
                "The valid proposal is dominated by the deterministic singleton baseline: "
                f"baseline transfer service={quality_baseline['transfer_service_seconds']}s and "
                f"makespan={quality_baseline['overall_completion_seconds']}s; proposal transfer "
                f"service={quality_proposed['transfer_service_seconds']}s and "
                f"makespan={quality_proposed['overall_completion_seconds']}s. Reassign or resequence "
                "without changing frozen facts. Do not copy the baseline silently and do not claim global optimality."
            ),
            "baseline_metrics": {
                "transfer_service_seconds": quality_baseline["transfer_service_seconds"],
                "overall_completion_seconds": quality_baseline["overall_completion_seconds"],
            },
            "proposed_metrics": {
                "transfer_service_seconds": quality_proposed["transfer_service_seconds"],
                "overall_completion_seconds": quality_proposed["overall_completion_seconds"],
            },
        }] if quality_repair else [])
        repair_accepted = False
        quality_repair_failure = None
        if repair_errors:
            planning_attempts = 2
            repaired_output = None
            try:
                repaired_output = _request_llm(
                    context,
                    repair_errors=repair_errors,
                    previous_plan=output["plan"],
                    provider_trace=provider_trace,
                )
            except HTTPException as exc:
                if not original_verdict["valid"]:
                    raise
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                quality_repair_failure = {
                    "code": str(detail.get("code", "AI_QUALITY_REPAIR_FAILED")),
                    "message": (
                        "Optional quality repair failed at the AI provider; returning the original "
                        "validated LLM plan. No heuristic plan was substituted."
                    ),
                }
            if repaired_output is not None:
                repaired_verdict = validate_plan(planning, repaired_output["plan"])
                if not original_verdict["valid"] and not repaired_verdict["valid"]:
                    raise HTTPException(502, {"code": "AI_PLAN_REJECTED",
                                              "message": "AI proposal and one bounded repair failed deterministic validation; no fallback was substituted.",
                                              "errors": repaired_verdict["errors"],
                                              "request_provenance": {
                                                  "planning_attempts": planning_attempts,
                                                  "provider_attempts": provider_trace["attempts"],
                                                  "repair_attempted": True,
                                                  "fallback_substituted": False,
                                              }})
                if repaired_verdict["valid"]:
                    repaired_comparison = compare(planning, repaired_output["plan"])
                    if (not original_verdict["valid"]
                            or _quality_score(repaired_comparison) < _quality_score(original_comparison)):
                        output, verdict = repaired_output, repaired_verdict
                        repair_accepted = True
                    else:
                        output, verdict = original_output, original_verdict
                else:
                    output, verdict = original_output, original_verdict
        quality = compare(planning, output["plan"])
        quality_assessment = copy.deepcopy(quality["quality_assessment"])
        if quality_repair_failure:
            quality_assessment.setdefault("warnings", []).append(quality_repair_failure["message"])
        result = {"recommendation_id": "REC-" + uuid.uuid4().hex, "scenario_id": scenario_id,
                  "revision": captured_revision, "source": "llm", "summary": output["summary"],
                  "plan": output["plan"], "validation": verdict,
                  "quality": {"difference": quality["difference"], **quality["quality"]},
                  "quality_assessment": quality_assessment,
                  "request_provenance": {
                      "planning_attempts": planning_attempts,
                      "provider_attempts": provider_trace["attempts"],
                      "repair_attempted": planning_attempts == 2,
                      "repair_reason": (
                          "validation" if not original_verdict["valid"]
                          else ("baseline_quality" if quality_repair else None)
                      ),
                      "repair_accepted": repair_accepted,
                      "fallback_substituted": False,
                      **({"quality_repair_failure": quality_repair_failure}
                         if quality_repair_failure else {}),
                  }}
        _store_recommendation_if_revision(scenario_id, captured_revision, key, result)
        return result
    finally:
        _suggest_lock.release()


@router.post("/scenarios/{scenario_id}/validate")
def validate(scenario_id: str, body: ValidateBody):
    scenario = _get(scenario_id)
    if scenario["revision"] != body.revision:
        raise HTTPException(409, "Scenario revision changed; reload before validating.")
    return validate_plan(_planning_scenario(scenario), body.plan)


@router.post("/scenarios/{scenario_id}/compare")
def compare_runs(scenario_id: str, body: CompareBody):
    scenario = _get(scenario_id)
    if scenario["revision"] != body.revision:
        raise HTTPException(409, "Scenario revision changed; reload before comparing.")
    recommendation = next(
        (item for item in scenario["recommendations"].values()
         if item["recommendation_id"] == body.recommendation_id and item["revision"] == body.revision),
        None,
    )
    if recommendation is None:
        raise HTTPException(404, "Recommendation is unknown, expired, or invalidated.")
    try:
        result = compare(_planning_scenario(scenario), recommendation["plan"])
    except ValueError as exc:
        raise HTTPException(422, {
            "code": "SIMULATION_REJECTED",
            "message": "Approved plan could not be simulated.",
            "errors": [str(exc)],
        }) from None
    return {"scenario_id": scenario_id, "recommendation_id": body.recommendation_id, **result}