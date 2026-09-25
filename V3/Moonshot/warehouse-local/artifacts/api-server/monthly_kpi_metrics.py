"""Pure, read-only monthly calculations. No operational state is imported."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

ROBOT_TASK_TYPES = {"PICK", "MOVE", "PACK_FEED", "STAGE", "REPLENISH"}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def unique(rows, fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k) for k in fields)].append(row)
    # Repeated identical identities are safe to collapse; conflicting ones are unknown.
    good, conflicts, duplicates = [], 0, 0
    for key, values in groups.items():
        duplicates += len(values) - 1
        if any(v in (None, "") for v in key) or any(v != values[0] for v in values):
            conflicts += 1
        else:
            good.append(values[0])
    return good, {"duplicate_rows": duplicates, "ambiguous_identities": conflicts}


def value(numerator, denominator, scale, rows, field, basis, exclusions):
    dates = sorted(t for r in rows if (t := timestamp(r.get(field))))
    return dict(value=numerator / denominator * scale if denominator else None,
                numerator=numerator, denominator=denominator, sample_size=denominator,
                exclusions=exclusions, basis=basis,
                coverage={"start": dates[0].isoformat() if dates else None,
                          "end": dates[-1].isoformat() if dates else None})


def aggregate(data, month, warehouse="", snapshots=False, basis="Source observations", as_of=None):
    """An optional UTC cutoff bounds source evidence; scenario callers omit it."""
    cutoff = timestamp(as_of) if isinstance(as_of, str) else as_of
    if as_of is not None and cutoff is None:
        raise ValueError("Invalid as_of timestamp")
    if cutoff is not None:
        cutoff = cutoff.replace(tzinfo=timezone.utc) if cutoff.tzinfo is None else cutoff.astimezone(timezone.utc)
    def scope(name):
        return [r for r in data[name] if not warehouse or r.get("warehouse_id") == warehouse]

    def in_month(row, field):
        t = timestamp(row.get(field))
        return t is not None and t.strftime("%Y-%m") == month and (cutoff is None or t <= cutoff)

    orders, order_audit = unique(scope("orders"), ("order_id",))
    shipments, shipment_audit = unique(scope("shipments"), ("shipment_id",))
    # A duplicate order join must never silently multiply durations.
    by_order = defaultdict(list)
    for r in shipments:
        by_order[r.get("order_id")].append(r)
    cycles, cycle_rows = [], []
    exclusions = {**order_audit,
                  **{f"shipment_{key}": count for key, count in shipment_audit.items()},
                  "ambiguous_shipment_orders": 0, "future_actual_departure": 0,
                  "missing_actual_departure": 0, "invalid_or_negative_duration": 0,
                  "unmatched_orders": 0, "warehouse_mismatch": 0}
    for order in orders:
        if not in_month(order, "created_at"):
            continue
        joined = by_order.get(order["order_id"], [])
        if not joined:
            exclusions["unmatched_orders"] += 1
            continue
        if len(joined) != 1:
            exclusions["ambiguous_shipment_orders"] += 1
            continue
        shipment = joined[0]
        if shipment.get("warehouse_id") != order.get("warehouse_id"):
            exclusions["warehouse_mismatch"] += 1
            continue
        actual = timestamp(shipment.get("actual_departure"))
        if actual is None:
            exclusions["missing_actual_departure"] += 1
            continue
        if cutoff is not None and actual > cutoff:
            exclusions["future_actual_departure"] += 1
            continue
        duration = (actual - timestamp(order["created_at"])).total_seconds() / 3600
        if duration < 0:
            exclusions["invalid_or_negative_duration"] += 1
            continue
        cycles.append(duration)
        cycle_rows.append(order)
    result = {"cycle_time": value(sum(cycles), len(cycles), 1, cycle_rows, "created_at", basis, exclusions)}
    result["cycle_time"]["matched_pair_count"] = len(cycles)

    # Planned-departure cohort, falling back to actual only if planned is unknown.
    cohort = [r for r in shipments if in_month(r, "planned_departure")
              or (timestamp(r.get("planned_departure")) is None and in_month(r, "actual_departure"))]
    recorded_actuals = [r for r in cohort if timestamp(r.get("actual_departure")) is not None]
    actuals = [r for r in recorded_actuals if cutoff is None or timestamp(r["actual_departure"]) <= cutoff]
    unknown = sum(timestamp(r.get("planned_departure")) is None for r in actuals)
    ontime = sum(timestamp(r["actual_departure"]) <= timestamp(r["planned_departure"])
                 for r in actuals if timestamp(r.get("planned_departure")) is not None)
    result["on_time_departure"] = value(ontime, len(actuals), 100, cohort, "planned_departure", basis,
        {**shipment_audit, "missing_actual_departure": len(cohort) - len(recorded_actuals),
         "future_actual_departure": len(recorded_actuals) - len(actuals),
         "unknown_planned_departure_in_denominator": unknown})

    tasks = [r for r in scope("tasks") if in_month(r, "created_at")
             and (r.get("task_type") in ROBOT_TASK_TYPES or r.get("assigned_robot"))]
    # Task identity deduplication uses OR across all observations; unassigned work remains.
    grouped = defaultdict(list)
    for row in tasks:
        if row.get("task_id"):
            grouped[row["task_id"]].append(row)
    blocked = sum(any(r.get("wes_status") in {"BLOCKED", "FAILED"}
                      or r.get("fleet_status") in {"BLOCKED", "FAILED"} for r in rows)
                  for rows in grouped.values())
    result["interventions"] = value(blocked, len(grouped), 1000, tasks, "created_at", basis,
        {"duplicate_rows": len(tasks) - sum(not r.get("task_id") for r in tasks) - len(grouped),
         "missing_task_id": sum(not r.get("task_id") for r in tasks)})

    inventory, inv_audit = unique(scope("inventory_snapshot") if snapshots else [],
                                  ("warehouse_id", "sku", "location"))
    comparable, equal = 0, 0
    for row in inventory:
        try:
            qty = [Decimal(row[k]) for k in ("wms_qty", "erp_qty", "vision_qty")]
            if not all(q.is_finite() and q >= 0 for q in qty):
                continue
        except (InvalidOperation, KeyError, TypeError):
            continue
        comparable += 1
        equal += len(set(qty)) == 1
    snapshot_basis = basis if basis.startswith("Generated") else "Assumed August baseline from undated source snapshot"
    result["inventory_accuracy"] = value(equal, comparable, 100, [], "", snapshot_basis if snapshots else "Unavailable: no dated snapshot",
        {**inv_audit, "unknown_quantities": len(inventory) - comparable})
    robot_rows = scope("robots") if snapshots else []
    robots, robot_audit = unique(robot_rows, ("robot_id",))
    # Ambiguous snapshots still represent a known unique robot, but not a known
    # certification/connectivity status. Do not artificially shrink fleet size.
    robot_ids = {r["robot_id"] for r in robot_rows if r.get("robot_id")}
    unknown_ids = robot_ids - {r["robot_id"] for r in robots}
    expired = sum(r.get("safety_cert_status") == "EXPIRED" and r.get("connectivity") in {"ONLINE", "INTERMITTENT"} for r in robots)
    result["false_availability"] = value(expired, len(robot_ids), 100, [], "", snapshot_basis if snapshots else "Unavailable: no dated snapshot",
        {**robot_audit, "unknown_status": len(unknown_ids) + sum(r.get("safety_cert_status") not in {"VALID", "EXPIRING", "EXPIRED"}
                                             or r.get("connectivity") not in {"ONLINE", "INTERMITTENT", "OFFLINE"} for r in robots)})
    return result


def changes(before, after, rate=False):
    a, b = before["value"], after["value"]
    delta = b - a if a is not None and b is not None else None
    return {"absolute": delta, "percentage_points": delta if rate else None,
            "relative_percent": delta / a * 100 if delta is not None and a else None}