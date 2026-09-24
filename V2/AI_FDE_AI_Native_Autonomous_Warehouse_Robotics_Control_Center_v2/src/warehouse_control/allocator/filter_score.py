"""Filter-then-score allocator (UC-1). Does not replace legacy_score()."""

from collections import defaultdict

from warehouse_control.eligibility.policy import INELIGIBLE_GATES, evaluate_eligibility
from warehouse_control.injects.catalog import apply_asset_overlay, load_inject
from warehouse_control.legacy.allocator import choose_robot, legacy_score
from warehouse_control.repository import csv_rows


def score_robot(robot: dict, task: dict) -> float:
    """Rank only after hard gates. Not a waiver."""
    battery = float(robot.get("battery_soc") or 0)
    conn = 10.0 if str(robot.get("connectivity") or "").upper() == "ONLINE" else 0.0
    fit = 0.0
    raw_need = task.get("payload_kg") if "payload_kg" in task else None
    if raw_need is not None and str(raw_need).strip() != "":
        try:
            have = float(robot.get("payload_kg") or 0)
            need = float(raw_need)
            fit = max(0.0, have - need) / 100.0
        except (TypeError, ValueError):
            fit = 0.0
    penalty = 0.0
    blocked = task.get("blocked_zone")
    if blocked and str(robot.get("zone") or "") == str(blocked):
        penalty = 1000.0
    site = 0.0
    if robot.get("warehouse_id") and task.get("warehouse_id"):
        site = 25.0 if robot["warehouse_id"] == task["warehouse_id"] else -50.0
    return battery + conn + fit + site - penalty


def is_rankable(elig: dict) -> bool:
    if elig.get("eligibility") == "ELIGIBLE":
        return True
    if elig.get("eligibility") == "INELIGIBLE":
        return False
    failed = elig.get("gates_failed") or []
    if any(g in INELIGIBLE_GATES for g in failed):
        return False
    if elig.get("uncertainty"):
        return False
    return set(failed) <= {"G8"}


def _charger_down(robot: dict, charging_by: dict, assets_by: dict) -> dict | None:
    ch = charging_by.get(robot.get("robot_id") or "")
    if not ch:
        return None
    asset_id = ch.get("preferred_charger")
    asset = assets_by.get(asset_id) or {}
    if str(asset.get("state") or "").upper() == "DOWN":
        return {
            "preferred_charger": asset_id,
            "asset_state": "DOWN",
            "charging_eligible": ch.get("charging_eligible"),
        }
    return None


def allocate(robots: list[dict], task: dict, context=None) -> dict:
    context = dict(context or {})
    maint_by = context.get("maintenance_by_robot") or {}
    zones_by = context.get("zones_by_id") or {}
    charging_by = context.get("charging_by_robot") or {}
    assets_by = context.get("assets_by_id") or {}
    outbound_blocked = bool(context.get("outbound_blocked"))
    no_cross_dc = bool(context.get("no_cross_dc"))

    dest = task.get("dest_zone") or task.get("target_zone")
    zone = context.get("zone") or (zones_by.get(dest) if dest else {})

    eligible, ineligible, abstain, scored = [], [], [], []

    for robot in robots:
        if no_cross_dc and task.get("warehouse_id") and robot.get("warehouse_id") != task.get("warehouse_id"):
            ineligible.append(
                {
                    "robot_id": robot.get("robot_id"),
                    "gates_failed": ["SITE_MISMATCH"],
                    "reason": "inject_no_cross_dc",
                }
            )
            continue
        elig = evaluate_eligibility(
            robot,
            task,
            context={
                "maintenance_rows": maint_by.get(robot.get("robot_id"), []),
                "zone": zone,
                "shadow_note": context.get("shadow_note"),
            },
        )
        rid = robot.get("robot_id")
        down = _charger_down(robot, charging_by, assets_by)
        if down:
            elig = dict(elig)
            elig["eligibility"] = "ABSTAIN"
            elig["uncertainty"] = list(elig.get("uncertainty") or []) + ["CHARGER_DOWN"]
            elig["gates_failed"] = list(elig.get("gates_failed") or []) + ["G8"]
            elig["charger"] = down

        row = {
            "robot_id": rid,
            "gates_failed": elig.get("gates_failed") or [],
            "eligibility": elig.get("eligibility"),
        }
        if elig.get("eligibility") == "INELIGIBLE":
            ineligible.append(row)
            continue
        if not is_rankable(elig) or down:
            abstain.append(row)
            continue
        eligible.append(row)
        scored.append((score_robot(robot, task), robot, elig))

    chosen = None
    decision_hint = "ABSTAIN"
    if outbound_blocked:
        decision_hint = "ABSTAIN"
        chosen = None
    elif scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        chosen = scored[0][1]
        decision_hint = "ALLOW"

    legacy = choose_robot(robots, task)
    return {
        "task_id": task.get("task_id"),
        "chosen_robot_id": chosen.get("robot_id") if chosen else None,
        "eligibility_summary": {
            "eligible": eligible,
            "ineligible": ineligible,
            "abstain": abstain,
        },
        "score_path": "filter_then_score",
        "legacy_choice_robot_id": legacy.get("robot_id") if legacy else None,
        "legacy_score_named": True,
        "decision_hint": decision_hint,
        "outbound_blocked": outbound_blocked,
        "physical_control": "disabled",
        "execution_applied": False,
    }


def _index_maint(rows):
    by = defaultdict(list)
    for row in rows:
        item = dict(row)
        item["wo_id"] = row.get("work_order_id")
        by[row.get("robot_id")].append(item)
    return by


def allocate_for_task(task_id: str, inject_id: str | None = None) -> dict:
    tasks = csv_rows("tasks.csv")
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if task is None:
        return {"error": "not_found", "task_id": task_id}

    inject = load_inject(inject_id) if inject_id else None
    warehouse_id = task.get("warehouse_id")
    assets = apply_asset_overlay(csv_rows("control_assets.csv"), inject, warehouse_id)
    assets_by = {a["asset_id"]: a for a in assets}
    charging_by = {c["robot_id"]: c for c in csv_rows("charging_state.csv")}
    zones_by = {z["zone_id"]: z for z in csv_rows("zones.csv")}
    robots = csv_rows("robots.csv")

    outbound_blocked = False
    no_cross_dc = False
    kind = (inject or {}).get("force_asset_type_down")
    if kind == "DOCK_DOOR":
        outbound_blocked = True
        no_cross_dc = True
    if kind == "ASRS":
        outbound_blocked = True
        no_cross_dc = True
    if kind == "CHARGER":
        no_cross_dc = True

    result = allocate(
        robots,
        task,
        context={
            "maintenance_by_robot": _index_maint(csv_rows("maintenance.csv")),
            "zones_by_id": zones_by,
            "charging_by_robot": charging_by,
            "assets_by_id": assets_by,
            "outbound_blocked": outbound_blocked,
            "no_cross_dc": no_cross_dc,
        },
    )
    result["inject_id"] = inject_id
    result["legacy_score_fn"] = legacy_score.__name__
    return result


def rejection_reasons(robot_id: str, task_id: str, inject_id: str | None = None) -> dict:
    robots = csv_rows("robots.csv")
    robot = next((r for r in robots if r.get("robot_id") == robot_id), None)
    tasks = csv_rows("tasks.csv")
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if robot is None or task is None:
        return {"error": "not_found"}

    inject = load_inject(inject_id) if inject_id else None
    assets = apply_asset_overlay(
        csv_rows("control_assets.csv"), inject, task.get("warehouse_id")
    )
    assets_by = {a["asset_id"]: a for a in assets}
    charging_by = {c["robot_id"]: c for c in csv_rows("charging_state.csv")}
    zones_by = {z["zone_id"]: z for z in csv_rows("zones.csv")}
    maint = _index_maint(csv_rows("maintenance.csv")).get(robot_id, [])
    dest = task.get("dest_zone")
    elig = evaluate_eligibility(
        robot,
        task,
        context={"maintenance_rows": maint, "zone": zones_by.get(dest, {})},
    )
    charger = _charger_down(robot, charging_by, assets_by)
    reasons = list(elig.get("gates_failed") or [])
    if charger:
        reasons.append("CHARGER_DOWN")
    return {
        "robot_id": robot_id,
        "task_id": task_id,
        "eligibility": elig.get("eligibility"),
        "gates_failed": elig.get("gates_failed") or [],
        "reasons": reasons,
        "evidence": elig.get("evidence") or [],
        "conflicts": elig.get("conflicts") or [],
        "uncertainty": elig.get("uncertainty") or [],
        "charger": charger,
        "physical_control": "disabled",
    }
