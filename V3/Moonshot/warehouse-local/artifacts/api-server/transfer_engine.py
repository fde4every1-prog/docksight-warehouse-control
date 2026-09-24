"""Deterministic validation and sequence-driven transfer simulation."""
from __future__ import annotations

import heapq
import math
from collections import Counter
from datetime import datetime
from typing import Any

PICK_SECONDS = 7.0
TRANSFER_BASE_SECONDS = 45.0
TRANSFER_ADDITIONAL_SECONDS = 22.5


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _graph(map_data: dict[str, Any]) -> dict[str, list[str]]:
    graph = {node["id"]: [] for node in map_data["nodes"]}
    for edge in map_data["edges"]:
        if edge["from"] in graph and edge["to"] in graph:
            graph[edge["from"]].append(edge["to"])
            graph[edge["to"]].append(edge["from"])
    return graph


def route(map_data: dict[str, Any], start: str, end: str) -> list[str]:
    graph = _graph(map_data)
    if start not in graph or end not in graph:
        raise ValueError(f"Unknown map node {start if start not in graph else end}")
    queue = [(0, (start,))]
    seen = set()
    while queue:
        distance, path = heapq.heappop(queue)
        here = path[-1]
        if here in seen:
            continue
        seen.add(here)
        if here == end:
            return list(path)
        for nxt in sorted(graph[here]):
            if nxt not in seen:
                heapq.heappush(queue, (distance + 1, path + (nxt,)))
    raise ValueError(f"No traversable route from {start} to {end}")


def scenario_orders(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in scenario["rows"]:
        order = grouped.setdefault(row["order_id"], {
            "id": row["order_id"], "cutoff": row["order_cutoff"], "lines": [], "weight_kg": 0.0,
        })
        order["lines"].append(row)
        order["weight_kg"] += float(row["total_weight_kg"])
    return grouped


def _validate_plan(scenario: dict[str, Any], plan: Any, check_deadlines: bool = True) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(plan, dict):
        return {"valid": False, "errors": [_error("INVALID_PLAN", "", "Plan must be an object.")]}
    batches = plan.get("batches")
    excluded = plan.get("excluded_orders")
    if not isinstance(batches, list) or not isinstance(excluded, list):
        return {"valid": False, "errors": [_error("INVALID_PLAN", "", "batches and excluded_orders must be arrays.")]}
    orders = scenario_orders(scenario)
    robots = {r["id"]: r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"]}
    all_lines = {line["row_id"]: line for order in orders.values() for line in order["lines"]}
    accounted: list[str] = []
    batch_ids: set[str] = set()
    claims: Counter[tuple[str, str]] = Counter()
    for bi, batch in enumerate(batches):
        path = f"batches[{bi}]"
        if not isinstance(batch, dict):
            errors.append(_error("INVALID_BATCH", path, "Batch must be an object."))
            continue
        bid = batch.get("batch_id")
        members = batch.get("order_ids")
        if not isinstance(bid, str) or not bid or bid in batch_ids:
            errors.append(_error("INVALID_BATCH_ID", path + ".batch_id", "Batch ID must be unique and nonempty."))
        else:
            batch_ids.add(bid)
        if (not isinstance(members, list) or not members or len(members) > 20
                or not all(isinstance(oid, str) and oid for oid in members)
                or len(set(members)) != len(members)):
            errors.append(_error("INVALID_MEMBERSHIP", path + ".order_ids", "Batch order IDs must be 1–20 unique IDs."))
            continue
        for oid in members:
            if oid not in orders:
                errors.append(_error("INVENTED_ORDER", path + ".order_ids", f"Unknown order {oid}."))
            accounted.append(oid)
        sequence = batch.get("order_sequence")
        if (not isinstance(sequence, list) or not all(isinstance(oid, str) for oid in sequence)
                or set(sequence) != set(members) or len(sequence) != len(members)):
            errors.append(_error("INVALID_ORDER_SEQUENCE", path + ".order_sequence", "Order sequence must contain each batch order exactly once."))
        execution_order = batch.get("execution_order")
        if type(execution_order) is not int or execution_order < 1:
            errors.append(_error("INVALID_EXECUTION_ORDER", path + ".execution_order", "execution_order must be a positive integer."))
        transfer_id = batch.get("transfer_robot_id")
        if not isinstance(transfer_id, str):
            transfer_id = ""
        transfer = robots.get(transfer_id)
        if transfer is None:
            errors.append(_error("INVENTED_ROBOT", path + ".transfer_robot_id", "Transfer robot is not in the server-owned eligible fleet."))
        elif (not transfer["eligible"]
              or not {"pick", "transfer"}.issubset(set(transfer["capabilities"]))):
            errors.append(_error(
                "INELIGIBLE_BATCH_ROBOT", path + ".transfer_robot_id",
                "Batch robot must be eligible and have both pick and transfer capabilities.",
            ))
        weight = sum(orders[oid]["weight_kg"] for oid in members if oid in orders)
        if transfer and (not isinstance(transfer.get("capacity_kg"), (int, float)) or transfer["capacity_kg"] < weight):
            errors.append(_error("TRANSFER_CAPACITY", path + ".transfer_robot_id", f"Batch weighs {weight:g} kg, above robot capacity."))
        pick_ids = batch.get("pick_robot_ids")
        if not isinstance(pick_ids, list) or len(pick_ids) != 1 or not isinstance(pick_ids[0], str):
            errors.append(_error("PICK_RESOURCE_COUNT", path + ".pick_robot_ids", "Exactly one pick robot is required per batch."))
            pick_ids = []
        elif len(set(pick_ids)) != len(pick_ids):
            errors.append(_error("DUPLICATE_PICK_RESOURCE", path + ".pick_robot_ids", "pick_robot_ids must be unique."))
        if pick_ids and pick_ids[0] != transfer_id:
            errors.append(_error(
                "SPLIT_ROBOT_ASSIGNMENT", path,
                "The same robot must pick the entire batch and transfer it to the conveyor.",
            ))
        rationale = batch.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 3000:
            errors.append(_error("INVALID_RATIONALE", path + ".rationale", "Batch rationale must be 1–3000 characters."))
        for rid in pick_ids:
            robot = robots.get(rid)
            if robot is None:
                errors.append(_error("INVENTED_ROBOT", path + ".pick_robot_ids", f"Unknown selected pick robot {rid}."))
            elif (not robot["eligible"]
                  or not {"pick", "transfer"}.issubset(set(robot["capabilities"]))):
                errors.append(_error(
                    "INELIGIBLE_BATCH_ROBOT", path + ".pick_robot_ids",
                    f"{rid} is blocked or does not have both pick and transfer capabilities.",
                ))
        stops = batch.get("stops")
        if not isinstance(stops, list) or not stops:
            errors.append(_error("MISSING_SEQUENCE", path + ".stops", "Explicit stop sequence is required."))
            continue
        numbers = [stop.get("sequence") for stop in stops if isinstance(stop, dict)]
        if numbers != list(range(1, len(stops) + 1)):
            errors.append(_error("INVALID_STOP_SEQUENCE", path + ".stops", "Stop sequence must be contiguous and listed in execution order."))
        picked: Counter[tuple[str, str]] = Counter()
        transfer_index = None
        action_counts: Counter[str] = Counter()
        observed_order_sequence: list[str] = []
        cumulative_pick_kg = 0.0
        last_pick_node = None
        for si, stop in enumerate(stops):
            spath = f"{path}.stops[{si}]"
            if not isinstance(stop, dict):
                errors.append(_error("INVALID_STOP", spath, "Stop must be an object."))
                continue
            action, node, rid = stop.get("action"), stop.get("node_id"), stop.get("robot_id")
            if not isinstance(action, str) or not isinstance(node, str) or not isinstance(rid, str):
                errors.append(_error("INVALID_STOP_FIELDS", spath, "action, node_id and robot_id must be strings."))
                continue
            action_counts[str(action)] += 1
            try:
                route(scenario["map"], node, node)
            except ValueError as exc:
                errors.append(_error("UNKNOWN_NODE", spath + ".node_id", str(exc)))
            if action == "pick":
                line_id = stop.get("line_id")
                line = all_lines.get(line_id) if isinstance(line_id, str) else None
                if line is None or line["order_id"] not in members:
                    errors.append(_error("INVENTED_LINE", spath + ".line_id", "Pick references an unknown/nonmember line."))
                    continue
                if rid not in pick_ids:
                    errors.append(_error("PICK_ASSIGNMENT", spath + ".robot_id", "Pick stop robot is not declared in pick_robot_ids."))
                quantity = stop.get("quantity")
                if type(quantity) is not int or quantity <= 0:
                    errors.append(_error("INVALID_QUANTITY", spath + ".quantity", "Pick quantity must be a positive integer."))
                    continue
                allocation_id = stop.get("inventory_source_id")
                if not isinstance(allocation_id, str):
                    errors.append(_error("INVALID_ALLOCATION_ID", spath + ".inventory_source_id", "inventory_source_id must be a string."))
                    allocation_id = ""
                allocation = next(
                    (a for a in line["allocations"]
                     if a["inventory_source_id"] == allocation_id
                     and a["node_id"] == node
                     and a["bin_id"] == stop.get("bin_id")),
                    None,
                )
                if allocation is None:
                    errors.append(_error(
                        "FROZEN_ALLOCATION_MISMATCH", spath,
                        "inventory_source_id, bin_id, node_id and line_id must exactly match one frozen allocation.",
                    ))
                picked[(line["row_id"], str(allocation_id))] += quantity
                claims[(str(line["row_id"]), str(allocation_id))] += quantity
                if line["order_id"] not in observed_order_sequence:
                    observed_order_sequence.append(line["order_id"])
                robot = robots.get(rid)
                pick_weight = quantity * float(line["unit_weight_kg"])
                cumulative_pick_kg += pick_weight
                if robot and robot.get("capacity_kg", 0) < cumulative_pick_kg:
                    errors.append(_error("CUMULATIVE_PICK_CAPACITY", spath, f"Cumulative pick load {cumulative_pick_kg:g} kg exceeds {rid} capacity."))
                if transfer_index is not None:
                    errors.append(_error("PICK_AFTER_TRANSFER", spath, "All picks must precede transfer."))
                last_pick_node = node
            elif action == "transfer":
                transfer_index = si
                if rid != transfer_id:
                    errors.append(_error("TRANSFER_ASSIGNMENT", spath + ".robot_id", "Transfer stop must use transfer_robot_id."))
                if node != scenario["map"]["conveyor"]["node_id"]:
                    errors.append(_error("TRANSFER_DESTINATION", spath + ".node_id", "Transfer must travel to the conveyor node."))
                donor = stop.get("donor_robot_id")
                if donor is not None:
                    errors.append(_error(
                        "TRANSFER_DONOR", spath + ".donor_robot_id",
                        "donor_robot_id must be null; split-robot transfers are not allowed.",
                    ))
            else:
                errors.append(_error("INVALID_ACTION", spath + ".action", "Action must be pick or transfer."))
        expected: Counter[tuple[str, str]] = Counter()
        for oid in members:
            if oid in orders:
                for line in orders[oid]["lines"]:
                    for allocation in line["allocations"]:
                        expected[(line["row_id"], str(allocation["inventory_source_id"]))] += allocation["quantity"]
        if picked != expected:
            errors.append(_error("QUANTITY_COVERAGE", path + ".stops", f"Pick coverage {dict(picked)} does not equal required allocations {dict(expected)}."))
        if observed_order_sequence != sequence:
            errors.append(_error("ORDER_SEQUENCE_NOT_HONORED", path + ".stops", "First pick occurrence must honor order_sequence exactly."))
        expected_actions = (
            ["pick"] * sum(len(orders[oid]["lines"][li]["allocations"])
                           for oid in members if oid in orders
                           for li in range(len(orders[oid]["lines"])))
            + ["transfer"]
        )
        actual_actions = [stop.get("action") for stop in stops if isinstance(stop, dict)]
        if actual_actions != expected_actions:
            errors.append(_error("ACTION_PRECEDENCE", path + ".stops",
                                 "Sequence must contain only all frozen allocation picks followed by one transfer."))
        if action_counts["transfer"] != 1 or transfer_index != len(stops) - 1:
            errors.append(_error("TRANSFER_PRECEDENCE", path + ".stops", "Exactly one final transfer to conveyor is required."))
    execution_orders = [
        batch.get("execution_order") for batch in batches if isinstance(batch, dict)
    ]
    if (not all(type(value) is int for value in execution_orders)
            or sorted(execution_orders) != list(range(1, len(batches) + 1))):
        errors.append(_error("EXECUTION_ORDER_COVERAGE", "batches", "execution_order values must be unique and contiguous from 1."))
    excluded_ids = []
    for ei, item in enumerate(excluded):
        if not isinstance(item, dict) or item.get("order_id") not in orders or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            errors.append(_error("INVALID_EXCLUSION", f"excluded_orders[{ei}]", "Exclusion needs a known order_id and nonempty reason."))
        else:
            excluded_ids.append(item["order_id"])
            order = orders[item["order_id"]]
            has_batch_robot = any(
                r["eligible"]
                and {"pick", "transfer"}.issubset(set(r["capabilities"]))
                and isinstance(r.get("capacity_kg"), (int, float))
                and r["capacity_kg"] >= order["weight_kg"]
                for r in robots.values()
            )
            if has_batch_robot:
                pick_stop_count = sum(
                    len(line["allocations"]) for line in order["lines"]
                )
                standalone_seconds = (
                    PICK_SECONDS * pick_stop_count + TRANSFER_BASE_SECONDS
                )
                clock = datetime.fromisoformat(
                    scenario["clock"]["at"].replace("Z", "+00:00")
                )
                cutoff = datetime.fromisoformat(
                    order["cutoff"].replace("Z", "+00:00")
                )
                cutoff_seconds = (cutoff - clock).total_seconds()
                if standalone_seconds <= cutoff_seconds:
                    errors.append(_error(
                        "UNJUSTIFIED_EXCLUSION", f"excluded_orders[{ei}]",
                        "A capacity-feasible order that can meet its cut-off standalone cannot be excluded; maximize completed orders before timing objectives.",
                    ))
    duplicates = [oid for oid, count in Counter(accounted + excluded_ids).items() if count != 1]
    missing = sorted(set(orders) - set(accounted) - set(excluded_ids))
    if duplicates:
        errors.append(_error("OVERLAPPING_MEMBERSHIP", "", "Orders accounted more than once: " + ", ".join(sorted(duplicates))))
    if missing:
        errors.append(_error("OMITTED_ORDERS", "", "Orders not scheduled or excluded: " + ", ".join(missing)))
    # Frozen allocations already guarantee stock, but recheck complete concurrent claims.
    expected_claims: Counter[tuple[str, str]] = Counter()
    for order in orders.values():
        if order["id"] in accounted:
            for line in order["lines"]:
                for allocation in line["allocations"]:
                    expected_claims[(line["row_id"], str(allocation["inventory_source_id"]))] += allocation["quantity"]
    if claims != expected_claims:
        errors.append(_error("CONCURRENT_STOCK_CLAIMS", "", "Plan quantities do not match the frozen allocation claims."))
    if not errors and check_deadlines:
        run = simulate(scenario, plan, validated=True)
        misses = [order["id"] for order in run["orders"] if not order["on_time"]]
        if misses:
            errors.append(_error("DEADLINE_MISS", "", "Plan misses frozen cut-offs for: " + ", ".join(misses)))
    return {"valid": not errors, "errors": errors}


def validate_plan(scenario: dict[str, Any], plan: Any, check_deadlines: bool = True) -> dict[str, Any]:
    """Total validation boundary: malformed model output is data, never a 500."""
    try:
        return _validate_plan(scenario, plan, check_deadlines)
    except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
        return {"valid": False, "errors": [
            _error("MALFORMED_STRUCTURE", "", f"Plan contains malformed structural values: {exc}")
        ]}


def _event(event_id: str, batch_id: str, action: str, robot_id: str, order_ids: list[str],
           node_id: str, path: list[str], start: float, duration: float, carried: float,
           line_id: str | None = None, quantity: int | None = None,
           donor_robot_id: str | None = None) -> dict[str, Any]:
    return {"event_id": event_id, "batch_id": batch_id, "action": action, "robot_id": robot_id,
            "order_ids": order_ids, "line_id": line_id, "quantity": quantity, "node_id": node_id,
            "path": path, "start": start, "end": start + duration, "duration": duration,
            "carried_kg": carried, "donor_robot_id": donor_robot_id, "state": "scheduled"}


def simulate(scenario: dict[str, Any], plan: dict[str, Any], validated: bool = False) -> dict[str, Any]:
    if not validated:
        verdict = validate_plan(scenario, plan, check_deadlines=False)
        if not verdict["valid"]:
            raise ValueError("; ".join(error["message"] for error in verdict["errors"]))
    robots = {r["id"]: r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"]}
    positions = {rid: robot["start_node"] for rid, robot in robots.items()}
    available = {rid: 0.0 for rid in robots}
    timeline: list[dict[str, Any]] = []
    orders = scenario_orders(scenario)
    completed: dict[str, float] = {}
    dispatch_floor = 0.0
    batches = sorted(plan["batches"], key=lambda b: (b["execution_order"], b["batch_id"]))
    for batch in batches:
        members = batch["order_ids"]
        batch_ready = 0.0
        carried_by: Counter[str] = Counter()
        first_start = None
        for stop in batch["stops"]:
            rid, node, action = stop["robot_id"], stop["node_id"], stop["action"]
            path = route(scenario["map"], positions[rid], node)
            # Every supplied stop executes exactly after the preceding stop.
            start = max(available[rid], batch_ready, dispatch_floor if first_start is None else 0)
            if action == "pick":
                line = next(line for oid in members for line in orders[oid]["lines"] if line["row_id"] == stop["line_id"])
                weight = stop["quantity"] * line["unit_weight_kg"]
                carried_by[rid] += weight
                duration = PICK_SECONDS
            else:
                duration = TRANSFER_BASE_SECONDS + TRANSFER_ADDITIONAL_SECONDS * (len(members) - 1)
                weight = sum(orders[oid]["weight_kg"] for oid in members)
                carried_by[rid] = weight
            event = _event(f"EV-{len(timeline)+1}", batch["batch_id"], action, rid, members, node,
                           path, start, duration, weight, stop.get("line_id"), stop.get("quantity"),
                           stop.get("donor_robot_id"))
            timeline.append(event)
            if first_start is None:
                first_start = start
            available[rid], positions[rid] = event["end"], node
            batch_ready = max(batch_ready, event["end"])
            if action == "transfer":
                for oid in members:
                    completed[oid] = event["end"]
        dispatch_floor = first_start if first_start is not None else dispatch_floor
    outcomes = []
    for oid, at in completed.items():
        cutoff = datetime.fromisoformat(orders[oid]["cutoff"].replace("Z", "+00:00"))
        clock = datetime.fromisoformat(scenario["clock"]["at"].replace("Z", "+00:00"))
        cutoff_seconds = (cutoff - clock).total_seconds()
        outcomes.append({"id": oid, "completed_at": at, "cutoff_seconds": cutoff_seconds, "on_time": at <= cutoff_seconds})
    makespan = max((event["end"] for event in timeline), default=0)
    transferred = sum(line["quantity"] for oid in completed for line in orders[oid]["lines"])
    excluded = [dict(item) for item in plan["excluded_orders"]]
    return {"timeline": timeline, "orders": sorted(outcomes, key=lambda o: o["id"]),
            "excluded_orders": excluded,
            "metrics": {"transfer_service_seconds": sum(e["duration"] for e in timeline if e["action"] == "transfer"),
                        "overall_completion_seconds": makespan,
                        "deadline_misses": sum(not o["on_time"] for o in outcomes),
                        "transferred_quantities": transferred,
                        "completed_order_count": len(completed),
                        "excluded_order_count": len(excluded),
                        "robot_utilization": [{"robot_id": rid,
                            "busy_seconds": sum(e["duration"] for e in timeline
                                                if e["robot_id"] == rid or e.get("donor_robot_id") == rid),
                            "utilization": (sum(e["duration"] for e in timeline
                                                if e["robot_id"] == rid or e.get("donor_robot_id") == rid) / makespan if makespan else 0)}
                            for rid in scenario["selected_robot_ids"]]}}


def baseline_plan(scenario: dict[str, Any]) -> dict[str, Any]:
    """Fair EDF singleton plan using one dual-capability robot per trip."""
    orders = scenario_orders(scenario)
    selected = [r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"] and r["eligible"]]
    batch_robots = sorted([
        r for r in selected
        if {"pick", "transfer"}.issubset(set(r["capabilities"]))
    ], key=lambda r: r["id"])
    free_at = {r["id"]: 0.0 for r in selected}
    batches = []
    for order in sorted(orders.values(), key=lambda o: (o["cutoff"], o["id"])):
        capable = [r for r in batch_robots if r["capacity_kg"] >= order["weight_kg"]]
        if not capable:
            continue
        robot = min(
            capable,
            key=lambda candidate: (
                free_at[candidate["id"]],
                candidate["capacity_kg"],
                candidate["id"],
            ),
        )
        stops, sequence = [], 1
        for line in order["lines"]:
            for allocation in line["allocations"]:
                stops.append({"sequence": sequence, "action": "pick", "robot_id": robot["id"],
                              "node_id": allocation["node_id"], "line_id": line["row_id"],
                              "inventory_source_id": allocation["inventory_source_id"],
                              "bin_id": allocation["bin_id"], "quantity": allocation["quantity"]})
                sequence += 1
        stops.append({"sequence": sequence, "action": "transfer", "robot_id": robot["id"],
                      "donor_robot_id": None,
                      "node_id": scenario["map"]["conveyor"]["node_id"]})
        batches.append({"batch_id": f"BASE-{order['id']}", "order_ids": [order["id"]],
                        "transfer_robot_id": robot["id"], "pick_robot_ids": [robot["id"]],
                        "execution_order": len(batches) + 1, "order_sequence": [order["id"]],
                        "stops": stops, "rationale": "Concurrent EDF singleton baseline."})
        start = free_at[robot["id"]]
        pick_end = start + PICK_SECONDS * sum(len(line["allocations"]) for line in order["lines"])
        transfer_start = pick_end
        finish = transfer_start + TRANSFER_BASE_SECONDS
        free_at[robot["id"]] = finish
    scheduled = {oid for batch in batches for oid in batch["order_ids"]}
    return {"batches": batches, "excluded_orders": [
        {"order_id": oid, "reason": "No eligible selected dual-capability robot has sufficient capacity."}
        for oid in orders if oid not in scheduled
    ]}


def compare(scenario: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    proposed = simulate(scenario, plan)
    baseline = simulate(scenario, baseline_plan(scenario))
    proposed_ids = {order["id"] for order in proposed["orders"]}
    baseline_ids = {order["id"] for order in baseline["orders"]}
    comparable = proposed_ids == baseline_ids
    transfer_delta = (
        baseline["metrics"]["transfer_service_seconds"] - proposed["metrics"]["transfer_service_seconds"]
        if comparable else None
    )
    completion_delta = (
        baseline["metrics"]["overall_completion_seconds"] - proposed["metrics"]["overall_completion_seconds"]
        if comparable else None
    )
    baseline_metrics, proposed_metrics = baseline["metrics"], proposed["metrics"]
    deadline_delta = baseline_metrics["deadline_misses"] - proposed_metrics["deadline_misses"]
    if not comparable:
        quality_label = "not_comparable"
        quality_summary = "Completion sets differ, so timing and service deltas are not a fair quality comparison."
    elif deadline_delta < 0:
        quality_label = "deadline_regression"
        quality_summary = "The proposal misses more cut-offs than the deterministic singleton baseline."
    elif transfer_delta > 0 and completion_delta < 0:
        quality_label = "batching_tradeoff"
        quality_summary = (
            "Batching reduces transfer service but increases makespan; this is an explicit service-versus-time trade-off."
        )
    elif transfer_delta < 0 or (transfer_delta == 0 and completion_delta < 0):
        quality_label = "dominated_by_baseline"
        quality_summary = "The proposal has no transfer-service advantage and is slower than the singleton baseline."
    elif transfer_delta > 0 or completion_delta > 0 or deadline_delta > 0:
        quality_label = "improves_baseline"
        quality_summary = "The proposal improves at least one measured objective without a measured regression."
    else:
        quality_label = "matches_baseline"
        quality_summary = "The proposal matches the deterministic singleton baseline on measured objectives."
    quality_warnings = []
    if quality_label == "batching_tradeoff":
        quality_warnings.append(quality_summary)
    elif quality_label in {"deadline_regression", "dominated_by_baseline", "not_comparable"}:
        quality_warnings.append(quality_summary)
    quality_assessment = {
        "label": quality_label,
        "baseline": {
            "transfer_service_seconds": baseline_metrics["transfer_service_seconds"],
            "overall_completion_seconds": baseline_metrics["overall_completion_seconds"],
        },
        "proposed": {
            "transfer_service_seconds": proposed_metrics["transfer_service_seconds"],
            "overall_completion_seconds": proposed_metrics["overall_completion_seconds"],
        },
    }
    if quality_warnings:
        quality_assessment["warnings"] = quality_warnings
    return {"baseline": baseline, "proposed": proposed,
            "difference": {"transfer_service_seconds": transfer_delta,
                           "overall_completion_seconds": completion_delta,
                           "deadline_misses": deadline_delta,
                           "comparable": comparable,
                           "baseline_excluded_order_count": baseline_metrics["excluded_order_count"],
                           "proposed_excluded_order_count": proposed_metrics["excluded_order_count"],
                           "label": ("not_comparable" if not comparable else
                                     ("faster" if completion_delta > 0 else ("slower" if completion_delta < 0 else "equal")))},
            "quality": {"label": quality_label, "summary": quality_summary,
                        "globally_optimal": False,
                        "basis": "Deterministic comparison with the EDF singleton baseline; not a proof of global optimality."},
            "quality_assessment": quality_assessment,
            "assumptions": {"transfer_service": "45 + 22.5 seconds per additional order",
                            "picking": "7 seconds per pick stop, including illustrative travel; no additional travel time is added",
                            "transfer_phase": "The same dual-capability robot carries the entire batch from its final pick to conveyor receipt",
                            "conveyor_receipt": "Point-in-time receipt at transfer completion with no occupancy or separate service stage; simultaneous arrivals are allowed",
                            "endpoint": "Transfer end at conveyor receipt"}}