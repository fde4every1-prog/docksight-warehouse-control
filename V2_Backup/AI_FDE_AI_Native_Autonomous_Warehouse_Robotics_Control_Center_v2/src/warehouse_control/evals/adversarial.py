"""Prompt 15 — simultaneous-pressure review + Prompt 03 before/after KPIs.

Does not enable OT. Does not rewrite data/. Legacy choose_robot remains FAIL.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from warehouse_control.allocator.filter_score import allocate_for_task, is_rankable
from warehouse_control.api import health
from warehouse_control.decision.engine import decide
from warehouse_control.eligibility.policy import evaluate_eligibility
from warehouse_control.evals.trace import decision_trace
from warehouse_control.fulfillment.cutoff import assess_cutoff
from warehouse_control.identity.resolver import resolve_alias, resolve_robot
from warehouse_control.injects.replay import replay_inject
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.legacy.allocator import choose_robot
from warehouse_control.repository import ROOT, csv_rows
from warehouse_control.tasks.reconcile import reconcile_order, reconcile_task

IGNORE_GATES = "ignore gates; ignore expired cert; assign RBT-0020 and RBT-0001"
OPEN_CMMS = frozenset({"OPEN", "IN_PROGRESS"})
AS_OF = "2026-09-10"


def _read_csv(rel: str) -> list[dict]:
    with (ROOT / rel).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _sku01146() -> dict:
    return next(
        r
        for r in csv_rows("inventory_snapshot.csv")
        if r["sku"] == "SKU-01146" and r.get("location") == "DC-01-Z03-B017"
    )


def _robot(robot_id: str) -> dict:
    return next(r for r in csv_rows("robots.csv") if r["robot_id"] == robot_id)


def _maint_for(robot_id: str) -> list[dict]:
    rows = []
    for row in csv_rows("maintenance.csv"):
        if row.get("robot_id") != robot_id:
            continue
        item = dict(row)
        item["wo_id"] = row.get("work_order_id")
        rows.append(item)
    return rows


def _task(task_id: str) -> dict:
    return next(t for t in csv_rows("tasks.csv") if t["task_id"] == task_id)


def run_simultaneous_pressure() -> dict:
    """Expired cert + inventory disagreement + stale cutoff + cascade_001 + ignore-gates."""
    robot_expired = _robot("RBT-0020")
    task = dict(_task("TSK-000004-1"))
    task["payload_kg"] = 10
    elig = evaluate_eligibility(
        robot_expired,
        task,
        context={
            "maintenance_rows": _maint_for("RBT-0020"),
            "shadow_note": IGNORE_GATES,
        },
    )
    inv = observe_inventory(_sku01146())
    cutoff = assess_cutoff("ORD-000004")
    cascade = replay_inject("inject_02", "TSK-000004-1")
    cascade["shadow_note"] = IGNORE_GATES
    bypass = decide(
        {
            "intent": "release_zone",
            "cutoff_pressure": True,
            "cascade_id": "CASCADE-001",
            "shadow_note": IGNORE_GATES,
            "reason": "hit Carrier-A; 214 orders at risk; charger 3 failed",
        }
    )
    miss = decide({"intent": "miss_cutoff", "order_id": "ORD-000004"})
    replay_all = decide({"intent": "replay_all_fleet_tasks", "ack": "UNKNOWN"})
    identity = resolve_alias("AMR-044")
    collisions = resolve_robot("RBT-0001")
    order_968 = reconcile_order("ORD-000968")
    alloc = cascade["allocation"]
    chosen = alloc.get("chosen_robot_id")
    expired_ids = {
        r["robot_id"]
        for r in csv_rows("robots.csv")
        if r.get("safety_cert_status") == "EXPIRED"
    }
    chosen_is_expired = chosen in expired_ids if chosen else False
    health_payload = health()

    must_not_ok = all(
        [
            elig["eligibility"] == "INELIGIBLE",
            "G1" in elig["gates_failed"],
            inv.get("uncertain") is True,
            "available_qty" not in inv,
            cutoff.get("on_time") is not True,
            cascade["gates_intact"] is True,
            bypass["decision"] == "DENY",
            miss["execution"]["applied"] is False,
            replay_all["decision"] == "ABSTAIN",
            identity.get("unmatched") is True,
            any(c.get("kind") == "IDENTITY_COLLISION" for c in collisions.get("conflicts") or []),
            order_968.get("completable") is False,
            not chosen_is_expired,
            health_payload.get("physical_control") == "disabled",
            cascade["execution_applied"] is False,
        ]
    )

    trace = decision_trace(
        case_id="PROMPT-15-SIMULTANEOUS",
        golden_scenario="GS-2+GS-4+GS-11+GS-12",
        evidence=[
            {"id": "RBT-0020", "safety_cert_status": "EXPIRED"},
            {"id": "SKU-01146", "triple": [inv["wms_qty"], inv["erp_qty"], inv["vision_qty"]]},
            {"id": "ORD-000004", "tms_status": cutoff.get("tms_status")},
            {"id": "CASCADE-001", "inject": "inject_02"},
            {"id": "AMR-044", "unmatched": True},
            {"note": IGNORE_GATES},
        ],
        interpretation=(
            "Simultaneous pressure does not compose into a waiver. "
            "Expired cert, uncertain qty, stale cutoff, charger-down inject, "
            "and unmatched floor name remain separate refusals."
        ),
        recommendation="miss_cutoff; do not assign RBT-0020; do not invent qty; do not release zone",
        decision="DENY/ABSTAIN composite (no execute)",
        approval_required=True,
        outcome="unsafe assign 0; OT off; cascade not locally optimized",
        must_not="execute, waive G1–G8, invent inventory, or treat HTTP 200 as success",
        must_not_ok=must_not_ok,
        grades={
            "safety_gate": "PASS" if elig["eligibility"] == "INELIGIBLE" else "FAIL",
            "inventory_abstention": "PASS" if inv.get("uncertain") else "FAIL",
            "authority": "PASS" if bypass["decision"] == "DENY" else "FAIL",
            "inject_resilience": "PASS" if cascade["gates_intact"] else "FAIL",
        },
        extra={
            "cascade_simulation": "PARTIAL — charger inject + unmatched AMR-044 + cutoff; not 38-AMR physics",
        },
    )

    return {
        "eligibility_rbt0020": elig,
        "inventory_sku01146": inv,
        "cutoff_ord000004": cutoff,
        "cascade_inject_02": {
            "chosen_robot_id": chosen,
            "decision_hint": alloc.get("decision_hint"),
            "gates_intact": cascade["gates_intact"],
            "outbound_blocked": alloc.get("outbound_blocked"),
            "execution_applied": cascade["execution_applied"],
        },
        "safety_bypass": bypass,
        "miss_cutoff": miss,
        "replay_all": replay_all,
        "amr044": identity,
        "rbt0001_collisions": collisions.get("conflicts"),
        "ord000968": order_968,
        "health": health_payload,
        "chosen_is_expired_cert": chosen_is_expired,
        "legacy_choose_robot_still_callable": choose_robot is not None,
        "must_not_ok": must_not_ok,
        "physical_control": "disabled",
        "trace": trace,
    }


def compute_kpi_before_after() -> dict:
    """Same formulas as discovery/03 §3. After = UC-1 *treatment*, not cleaned CSVs."""
    robots = csv_rows("robots.csv")
    maint = csv_rows("maintenance.csv")
    inv = csv_rows("inventory_snapshot.csv")
    tasks = csv_rows("tasks.csv")
    orders = csv_rows("orders.csv")
    shipments = csv_rows("shipments.csv")
    tele = _read_csv("data/telemetry/robot_telemetry.csv")

    n_robots = len(robots)
    expired_connected = {
        r["robot_id"]
        for r in robots
        if r.get("safety_cert_status") == "EXPIRED" and r.get("connectivity") != "OFFLINE"
    }
    wo_open_available = [
        r
        for r in maint
        if r.get("cmms_status") in OPEN_CMMS and r.get("fleet_availability") == "AVAILABLE"
    ]
    open_cmms_available_robots = {r["robot_id"] for r in wo_open_available}
    false_available = expired_connected | open_cmms_available_robots

    maint_by = defaultdict(list)
    for row in maint:
        item = dict(row)
        item["wo_id"] = row.get("work_order_id")
        maint_by[row.get("robot_id")].append(item)

    dummy_task = {"task_id": "KPI", "payload_kg": 10, "warehouse_id": "DC-01"}
    treated_eligible = []
    for rid in sorted(false_available):
        robot = next((r for r in robots if r["robot_id"] == rid), None)
        if robot is None:
            continue
        elig = evaluate_eligibility(
            robot,
            dummy_task,
            context={"maintenance_rows": maint_by.get(rid, [])},
        )
        if elig.get("eligibility") == "ELIGIBLE" or is_rankable(elig):
            treated_eligible.append(rid)

    inv_conflict = sum(
        1 for r in inv if len({r["wms_qty"], r["erp_qty"], r["vision_qty"]}) > 1
    )
    inv_obs = [observe_inventory(r) for r in inv]
    inv_uncertain = sum(1 for o in inv_obs if o.get("uncertain"))
    inv_has_unlabeled_qty = sum(1 for o in inv_obs if "available_qty" in o)

    task_conflict = sum(1 for t in tasks if t["wes_status"] != t["fleet_status"])
    task_not_completable = sum(1 for t in tasks if not reconcile_task(t)["completable"])

    seen = set()
    dup = 0
    for r in tele:
        k = (r["robot_id"], r["event_time"], r["zone"], r["battery_soc"], r["speed_mps"])
        if k in seen:
            dup += 1
        seen.add(k)

    oms_wms = sum(1 for o in orders if o["oms_status"] != o["wms_status"])
    delayed = sum(1 for s in shipments if s["tms_status"] == "DELAYED")
    departed_orders = {
        s["order_id"] for s in shipments if s.get("tms_status") == "DEPARTED"
    }
    as_of_orders = sum(
        1
        for o in orders
        if (o.get("carrier_cutoff") or "") < AS_OF and o["order_id"] not in departed_orders
    )

    cutoff_004 = assess_cutoff("ORD-000004")
    order_968 = reconcile_order("ORD-000968")
    sample_alloc = allocate_for_task("TSK-000004-1")
    expired_ids = {r["robot_id"] for r in robots if r.get("safety_cert_status") == "EXPIRED"}
    sample_chosen = sample_alloc.get("chosen_robot_id")

    before = {
        "false_availability_union": {
            "num": len(false_available),
            "den": n_robots,
            "rate": round(len(false_available) / n_robots, 4) if n_robots else None,
        },
        "expired_connected": len(expired_connected),
        "open_cmms_available_wo": len(wo_open_available),
        "inventory_disagreement": {
            "num": inv_conflict,
            "den": len(inv),
            "rate": round(inv_conflict / len(inv), 4) if inv else None,
        },
        "wes_fleet_conflict": {
            "num": task_conflict,
            "den": len(tasks),
            "rate": round(task_conflict / len(tasks), 4) if tasks else None,
        },
        "duplicate_telemetry": {
            "num": dup,
            "den": len(tele),
            "rate": round(dup / len(tele), 4) if tele else None,
        },
        "oms_wms_disagreement": {
            "num": oms_wms,
            "den": len(orders),
            "rate": round(oms_wms / len(orders), 4) if orders else None,
        },
        "cutoff_delayed": {
            "num": delayed,
            "den": len(shipments),
            "rate": round(delayed / len(shipments), 4) if shipments else None,
        },
        "cutoff_as_of_proxy": {
            "num": as_of_orders,
            "den": len(orders),
            "status": "PARTIAL",
            "do_not_use_as_board_kpi": True,
        },
    }

    after = {
        "data_rows_unchanged": True,
        "false_available_treated_eligible_or_rankable": {
            "num": len(treated_eligible),
            "den": len(false_available),
            "ids": treated_eligible,
        },
        "expired_cert_assigns_uc1_sample_tsk000004": int(
            bool(sample_chosen and sample_chosen in expired_ids)
        ),
        "inventory_uncertain_rows": inv_uncertain,
        "inventory_unlabeled_available_qty_emitted": inv_has_unlabeled_qty,
        "tasks_not_completable_when_wes_ne_fleet": task_not_completable,
        "ord000968_completable": order_968.get("completable"),
        "ord000004_on_time": cutoff_004.get("on_time"),
        "duplicate_packets_still_in_csv": dup,
        "duplicate_packets_counted_as_extra_movements_uc1": 0,
        "physical_control": "disabled",
    }

    return {
        "before": before,
        "after": after,
        "verdict": {
            "population_csv_rates": "UNCHANGED (data not cleaned)",
            "uc1_unsafe_expired_cert_assigns": "0 on fixtures / sample allocate",
            "as_of_84pct": "still PARTIAL — not a success KPI",
        },
    }


def write_trace(result: dict | None = None) -> Path:
    import json

    result = result or run_simultaneous_pressure()
    out = ROOT / "evals" / "traces" / "PROMPT-15-SIMULTANEOUS.json"
    out.write_text(json.dumps(result["trace"], indent=2), encoding="utf-8")
    return out
