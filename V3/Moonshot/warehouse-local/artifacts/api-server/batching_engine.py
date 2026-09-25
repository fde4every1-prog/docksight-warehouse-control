"""Pure event-driven batching sandbox; intentionally never imports live modules."""
from collections import Counter
from itertools import combinations
import heapq
import math

STAGES = ("pick", "move", "pack_feed", "stage")
ROBOT_TYPES = {"pick": {"AGV", "AMR", "CASE_PICKER", "FORK_AMR"},
               "move": {"AGV", "AMR", "FORK_AMR", "PALLET_MOVER", "TUGGER"}}


def duration(n, base=45):
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("Operation size must be a positive integer")
    return base + 0.5 * base * (n - 1)


def _route(s, start, end):
    nodes = {n["id"]: n for n in s["map"]["nodes"]}
    if start not in nodes or end not in nodes:
        raise ValueError("Unknown graph node")
    graph = {key: [] for key in nodes}
    for edge in s["map"]["edges"]:
        a, b = edge["from"], edge["to"]
        distance = math.hypot(nodes[a]["x"] - nodes[b]["x"], nodes[a]["y"] - nodes[b]["y"])
        graph[a].append((b, distance))
        graph[b].append((a, distance))
    queue, seen = [(0, (start,))], set()
    while queue:
        distance, path = heapq.heappop(queue)
        here = path[-1]
        if here in seen:
            continue
        seen.add(here)
        if here == end:
            return distance, list(path)
        for nxt, weight in sorted(graph[here]):
            if nxt not in seen:
                heapq.heappush(queue, (distance + weight, path + (nxt,)))
    raise ValueError(f"Unreachable route: {start} → {end}")


def _weight(s, order_ids):
    skus = {sku["id"]: sku["unit_weight_kg"] for sku in s["skus"]}
    return sum(line["quantity"] * skus[line["sku"]]
               for o in s["orders"] if o["id"] in order_ids for line in o["lines"])


def _eligible(s, stage, weight):
    return sorted(
        [r for r in s["robots"]
         if r["available"] and not r.get("blocked_reason")
         and r["warehouse_id"] == s["warehouse_id"]
         and r["type"] in ROBOT_TYPES[stage] and stage in r["capabilities"]
         and isinstance(r.get("capacity_kg"), (int, float)) and r["capacity_kg"] >= weight
         and isinstance(r.get("battery_percent"), (int, float)) and 10 < r["battery_percent"] <= 100],
        key=lambda r: (r["capacity_kg"], r["id"]))


def _check(s, batches):
    if not isinstance(batches, list):
        raise ValueError("batches must be an array")
    orders = {o["id"]: o for o in s["orders"]}
    bins = {b["id"]: b for b in s["map"]["bins"]}
    if len(orders) != len(s["orders"]):
        raise ValueError("Duplicate scenario order identity")
    lines, reservations = set(), Counter()
    for o in s["orders"]:
        if o["status"] != "queued":
            raise ValueError(f"{o['id']}: already running/nonqueued work cannot be altered")
        if not o["lines"]:
            raise ValueError("Orders require lines")
        for line in o["lines"]:
            if line["id"] in lines:
                raise ValueError("Duplicate order-line identity")
            lines.add(line["id"])
            if type(line["quantity"]) is not int or line["quantity"] <= 0:
                raise ValueError("Line quantity must be a positive integer")
            b = bins[line["bin_id"]]
            if b["sku"] != line["sku"]:
                raise ValueError("Bin SKU mismatch")
            reservations[b["id"]] += line["quantity"]
    for bid, quantity in reservations.items():
        if quantity > bins[bid]["stock"]:
            raise ValueError(f"Stock overcommitment at {bid}")
    used, ids = set(), set()
    for batch in batches:
        if not isinstance(batch, dict) or not isinstance(batch.get("id"), str) or not batch["id"]:
            raise ValueError("Each batch requires a nonempty string id")
        members = batch.get("order_ids")
        if not isinstance(members, list) or not all(isinstance(x, str) for x in members):
            raise ValueError("order_ids must be an array of strings")
        if batch["id"] in ids:
            raise ValueError("Duplicate batch identity")
        ids.add(batch["id"])
        if not 2 <= len(members) <= s["constraints"]["max_batch_size"]:
            raise ValueError("Batch requires 2–3 orders")
        if len(set(members)) != len(members) or used.intersection(members):
            raise ValueError("Duplicate/overlapping order membership")
        if any(oid not in orders for oid in members):
            raise ValueError("Unknown order membership")
        used.update(members)
        locations = [bins[line["bin_id"]] for oid in members for line in orders[oid]["lines"]]
        if len({b["zone"] for b in locations}) != 1:
            raise ValueError("Batch crosses picking zones")
        for a, b in combinations(locations, 2):
            if _route(s, a["node_id"], b["node_id"])[0] > s["constraints"]["max_proximity"]:
                raise ValueError("Batch bins exceed graph proximity limit")
    for members in [b["order_ids"] for b in batches] + [[oid] for oid in orders if oid not in used]:
        weight = _weight(s, members)
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError("Payload weights must be explicit positive finite evidence")
        for stage in ("pick", "move"):
            if not _eligible(s, stage, weight):
                raise ValueError(f"Payload/robot eligibility: no ready {stage} robot for {members} ({weight} kg)")
    return reservations


def _run(s, batches):
    reservations = _check(s, batches)
    orders = {o["id"]: o for o in s["orders"]}
    bins = {b["id"]: b for b in s["map"]["bins"]}
    nodes = {n["id"]: n for n in s["map"]["nodes"]}
    grouped = {oid for b in batches for oid in b["order_ids"]}
    groups = [(b["id"], b["order_ids"]) for b in batches]
    groups += [(None, [oid]) for oid in orders if oid not in grouped]
    pending, finished, timeline, active, positions = [], set(), [], [], {
        r["id"]: r["start_node"] for r in s["robots"]}
    def task(stage, members, batch, deps):
        tid = stage + ":" + ",".join(sorted(members))
        pending.append({"id": tid, "stage": stage, "order_ids": sorted(members),
                        "batch_id": batch, "deps": set(deps)})
        return tid
    for bid, members in groups:
        pick = task("pick", members, bid, [])
        move = task("move", members, bid, [pick])
        for oid in members:
            pack = task("pack_feed", [oid], bid, [move])
            task("stage", [oid], bid, [pack])
    now = 0.0
    while pending or active:
        for event in list(active):
            if event["end"] <= now:
                active.remove(event)
                finished.add(event["id"])
                if event["resource_type"] == "robot":
                    positions[event["resource_id"]] = event["path"][-1]["node_id"]
        used = {e["resource_id"] for e in active}
        ready = sorted(
            [t for t in pending if t["deps"] <= finished],
            key=lambda t: (min(orders[oid]["cutoff_seconds"] for oid in t["order_ids"]),
                           min(orders[oid]["sub_order_id"] for oid in t["order_ids"]),
                           STAGES.index(t["stage"]), t["id"]))
        for t in ready:
            stage, members = t["stage"], t["order_ids"]
            weight = _weight(s, members)
            robot = stage in ROBOT_TYPES
            resources = _eligible(s, stage, weight) if robot else sorted(
                [a for a in s["assets"] if a["available"] and a["stage"] == stage
                 and a["warehouse_id"] == s["warehouse_id"]], key=lambda a: a["id"])
            resource = next((r for r in resources if r["id"] not in used), None)
            if resource is None:
                continue
            rid = resource["id"]
            span = duration(len(members) if robot else 1, s["constraints"]["base_duration_seconds"])
            if robot:
                stops = ([bins[line["bin_id"]]["node_id"] for oid in members for line in orders[oid]["lines"]]
                         if stage == "pick" else [
                             next(e["path"][-1]["node_id"] for e in timeline
                                  if e["stage"] == "pick" and e["order_ids"] == members),
                             s["map"]["destinations"]["transfer"]])
                route = [positions[rid]]
                for stop in stops:
                    route.extend(_route(s, route[-1], stop)[1][1:])
            else:
                route = [resource["node_id"]]
            distances = [0.0]
            for a, b in zip(route, route[1:]):
                distances.append(distances[-1] + math.hypot(nodes[a]["x"]-nodes[b]["x"], nodes[a]["y"]-nodes[b]["y"]))
            points = [{"node_id": node, "x": nodes[node]["x"], "y": nodes[node]["y"],
                       "at": now + (distances[i] / distances[-1] * span if distances[-1] else 0)}
                      for i, node in enumerate(route)]
            event = {k: v for k, v in t.items() if k != "deps"}
            event.update({"resource_id": rid, "resource_type": "robot" if robot else "asset",
                          "start": now, "end": now + span, "duration": span,
                          "payload_kg": weight, "path": points,
                          "line_ids": [l["id"] for oid in members for l in orders[oid]["lines"]],
                          "tote_ids": [orders[oid]["tote_id"] for oid in members]})
            timeline.append(event)
            active.append(event)
            used.add(rid)
            pending.remove(t)
        if active:
            now = min(e["end"] for e in active)
        elif pending:
            raise ValueError("Infeasible resource schedule: no eligible asset or reachable dependency")
    outcomes = [{"id": oid, "completed_at": next(e["end"] for e in timeline if e["stage"] == "stage" and oid in e["order_ids"]),
                 "cutoff_seconds": o["cutoff_seconds"]} for oid, o in orders.items()]
    for o in outcomes:
        o["on_time"] = o["completed_at"] <= o["cutoff_seconds"]
    return {
        "mode": "batched" if batches else "baseline", "scenario_id": s["scenario_id"],
        "timeline": timeline, "orders": outcomes,
        "metrics": {"completed_orders": len(outcomes), "completed_tasks": len(timeline),
                    "logical_tasks": sum(len(e["order_ids"]) for e in timeline),
                    "service_seconds": sum(e["duration"] for e in timeline),
                    "makespan_seconds": now, "deadline_misses": sum(not o["on_time"] for o in outcomes),
                    "robot_utilization": [
                        {"robot_id": r["id"], "busy_seconds": sum(e["duration"] for e in timeline if e["resource_id"] == r["id"]),
                         "utilization": sum(e["duration"] for e in timeline if e["resource_id"] == r["id"]) / now if now else 0}
                        for r in s["robots"]]},
        "inventory": [{"bin_id": b["id"], "sku": b["sku"], "opening": b["stock"],
                       "reserved": reservations[b["id"]], "remaining": b["stock"] - reservations[b["id"]]}
                      for b in s["map"]["bins"]],
    }


def validate_plan(s, proposal):
    try:
        if not isinstance(proposal, dict) or proposal.get("scenario_id") != s["scenario_id"]:
            raise ValueError("Missing or stale scenario_id")
        if "batches" not in proposal:
            raise ValueError("Missing batches")
        batches = proposal["batches"]
        run = _run(s, batches)
        if batches:
            misses = [o["id"] for o in run["orders"] if not o["on_time"]]
            if misses:
                raise ValueError("Full downstream deadline infeasible for: " + ", ".join(misses))
        return {"valid": True, "errors": [], "batches": batches}
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return {"valid": False, "errors": [str(exc)], "batches": []}


def simulate(s, batches):
    result = validate_plan(s, {"scenario_id": s["scenario_id"], "batches": batches})
    if not result["valid"]:
        raise ValueError("; ".join(result["errors"]))
    return _run(s, batches)


def enumerate_candidates(s):
    candidates, exclusions = [], []
    ids = sorted(o["id"] for o in s["orders"])
    for count in range(2, s["constraints"]["max_batch_size"] + 1):
        for members in combinations(ids, count):
            batch = {"id": "BATCH-" + "-".join(members), "order_ids": list(members),
                     "reason": "Same-zone graph-nearby work; stock, payload, readiness and full downstream deadlines validated."}
            result = validate_plan(s, {"scenario_id": s["scenario_id"], "batches": [batch]})
            if result["valid"]:
                candidates.append(batch)
            else:
                exclusions.append({"order_ids": list(members), "reason": "; ".join(result["errors"])})
    return {"candidates": candidates, "exclusions": exclusions}


def compare(s, batches):
    baseline, batched = simulate(s, []), simulate(s, batches)
    return {"scenario_id": s["scenario_id"], "baseline": baseline, "batched": batched,
            "savings": {"service_seconds": baseline["metrics"]["service_seconds"] - batched["metrics"]["service_seconds"],
                        "makespan_seconds": baseline["metrics"]["makespan_seconds"] - batched["metrics"]["makespan_seconds"]}}