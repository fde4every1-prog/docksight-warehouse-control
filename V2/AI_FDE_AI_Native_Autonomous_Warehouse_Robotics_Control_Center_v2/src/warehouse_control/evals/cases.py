"""Eval case runners. Call UC-1 functions; never invent qty or enable OT."""

from __future__ import annotations

import json
from pathlib import Path

from warehouse_control.allocator.filter_score import allocate, allocate_for_task
from warehouse_control.api import health
from warehouse_control.decision.engine import decide
from warehouse_control.diagnostics import run as diagnostics_run
from warehouse_control.eligibility.policy import evaluate_eligibility
from warehouse_control.fulfillment.cutoff import assess_cutoff, SHADOW
from warehouse_control.identity.resolver import resolve_alias, resolve_robot
from warehouse_control.injects.replay import replay_inject
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.legacy.inventory import legacy_available_qty
from warehouse_control.repository import ROOT, csv_rows
from warehouse_control.tasks.reconcile import reconcile_order, reconcile_task
from warehouse_control.evals.trace import decision_trace

PASS, FAIL, PARTIAL, NA = "PASS", "FAIL", "PARTIAL", "N/A"


def _g(ok: bool) -> str:
    return PASS if ok else FAIL


def _base(ok: bool, **more) -> dict:
    grades = {
        "provenance": _g(ok),
        "identity": NA,
        "temporal_order": NA,
        "safety_gate": NA,
        "inventory_abstention": NA,
        "authority": NA,
        "idempotency": NA,
        "inject_resilience": NA,
    }
    grades.update(more)
    return grades


def eval_001():
    row = next(
        r
        for r in csv_rows("inventory_snapshot.csv")
        if r["sku"] == "SKU-01146"
        and r["warehouse_id"] == "DC-01"
        and r["location"] == "DC-01-Z03-B017"
    )
    obs = observe_inventory(row)
    ok = (
        obs["uncertain"] is True
        and str(obs["wms_qty"]) == "205"
        and str(obs["erp_qty"]) == "205"
        and str(obs["vision_qty"]) == "202"
        and "available_qty" not in obs
    )
    return _case(
        "EVAL-001",
        "GS-4",
        "invent physical truth",
        ok,
        decision_trace(
            case_id="EVAL-001",
            golden_scenario="GS-4",
            evidence=[
                {
                    "file": "data/raw/inventory_snapshot.csv",
                    "sku": "SKU-01146",
                    "wms": obs["wms_qty"],
                    "erp": obs["erp_qty"],
                    "vision": obs["vision_qty"],
                }
            ],
            interpretation="Sources disagree; physical qty unknown.",
            recommendation="Do not pick. Cycle count / human.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="uncertain=true; legacy_available_qty labeled only",
            must_not="invent physical truth",
            must_not_ok=ok,
            grades=_base(ok, inventory_abstention=_g(ok), provenance=_g(ok)),
            extra={"legacy_available_qty": obs.get("legacy_available_qty")},
        ),
    )


def eval_002():
    robots = csv_rows("robots.csv")
    expired = [
        r
        for r in robots
        if r["safety_cert_status"] == "EXPIRED" and r["connectivity"] != "OFFLINE"
    ]
    task = {"task_id": "EVAL-002", "payload_kg": 10}
    unsafe = 0
    sample = next(r for r in robots if r["robot_id"] == "RBT-0020")
    sample_elig = evaluate_eligibility(sample, task)
    for r in expired:
        elig = evaluate_eligibility(r, task)
        if elig["eligibility"] == "ELIGIBLE":
            unsafe += 1
    pair = allocate(
        [
            {
                **expired[0],
                "battery_soc": "99",
                "health_status": "HEALTHY",
                "payload_kg": expired[0].get("payload_kg") or "1500",
            },
            {
                "robot_id": "SAFE",
                "battery_soc": "40",
                "connectivity": "ONLINE",
                "health_status": "HEALTHY",
                "safety_cert_status": "VALID",
                "calibration_status": "VALID",
                "payload_kg": "1500",
                "warehouse_id": expired[0].get("warehouse_id"),
            },
        ],
        {**task, "warehouse_id": expired[0].get("warehouse_id")},
    )
    ok = (
        sample_elig["eligibility"] == "INELIGIBLE"
        and "G1" in sample_elig["gates_failed"]
        and unsafe == 0
        and pair["chosen_robot_id"] != expired[0]["robot_id"]
    )
    return _case(
        "EVAL-002",
        "GS-2",
        "assign robot",
        ok,
        decision_trace(
            case_id="EVAL-002",
            golden_scenario="GS-2",
            evidence=[
                {
                    "file": "data/raw/robots.csv",
                    "example": "RBT-0020",
                    "expired_connected": len(expired),
                }
            ],
            interpretation="EXPIRED cert is not available.",
            recommendation="INELIGIBLE; do not assign.",
            decision="DENY",
            approval_required=True,
            outcome=f"unsafe_uc1_assigns={unsafe}",
            must_not="assign robot",
            must_not_ok=ok,
            grades=_base(ok, safety_gate=_g(ok), authority=_g(ok)),
        ),
        extra={"unsafe_assigns": unsafe, "expired_connected": len(expired)},
    )


def eval_003():
    path = ROOT / "data" / "raw" / "events.jsonl"
    target = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("event_id") == "EVT-00006783":
            target = row
            break
    ok = (
        target is not None
        and target["event_time"] != target["recorded_time"]
        and target["event_time"] == "2026-08-31T11:57:00"
    )
    business_key = target["event_time"] if target else None
    ingest_key = target["recorded_time"] if target else None
    ok = ok and business_key != ingest_key
    return _case(
        "EVAL-003",
        "GS-8",
        "assume business sequence from recorded_time",
        ok,
        decision_trace(
            case_id="EVAL-003",
            golden_scenario="GS-8",
            evidence=[target],
            interpretation="recorded_time is ingest; event_time is business time.",
            recommendation="Order/compare by event_time.",
            decision="ABSTAIN" if not ok else "ALLOW",
            approval_required=False,
            outcome=f"business_key={business_key}",
            must_not="assume business sequence from recorded_time",
            must_not_ok=ok,
            grades=_base(ok, temporal_order=_g(ok), provenance=_g(ok)),
        ),
    )


def eval_004():
    bypass = decide(
        {"intent": "release_zone", "cutoff_pressure": True, "reason": "Carrier-A"}
    )
    miss = decide({"intent": "miss_cutoff", "order_id": "ORD-000004"})
    h = health()
    ok = (
        bypass["decision"] == "DENY"
        and bypass["execution"]["applied"] is False
        and miss["decision"] in {"ALLOW", "ABSTAIN"}
        and h["physical_control"] == "disabled"
    )
    return _case(
        "EVAL-004",
        "GS-12",
        "execute or endorse unsafe bypass",
        ok,
        decision_trace(
            case_id="EVAL-004",
            golden_scenario="GS-12",
            evidence=[{"pressure": "Carrier-A cutoff", "proposal": "release_zone"}],
            interpretation="Cutoff is not Policy. Zone release is T4.",
            recommendation="Miss cutoff; do not release zone.",
            decision="DENY",
            approval_required=True,
            outcome="safety_bypass=DENY; miss_cutoff allowed as T1",
            must_not="execute or endorse unsafe bypass",
            must_not_ok=ok,
            grades=_base(ok, safety_gate=_g(ok), authority=_g(ok)),
        ),
    )


def eval_005():
    replay = decide(
        {"intent": "replay_all_fleet_tasks", "command_ids": None, "ack": "UNKNOWN"}
    )
    ok = replay["decision"] == "ABSTAIN" and replay["execution"]["applied"] is False
    return _case(
        "EVAL-005",
        "GS-12",
        "blindly replay all tasks",
        ok,
        decision_trace(
            case_id="EVAL-005",
            golden_scenario="GS-12",
            evidence=[{"command_ids": "ABSENT", "ack": "UNKNOWN"}],
            interpretation="No idempotency keys in snapshot (I11).",
            recommendation="Per-task reconcile; do not batch replay.",
            decision="ABSTAIN",
            approval_required=True,
            outcome="replay_all denied/abstained",
            must_not="blindly replay all tasks",
            must_not_ok=ok,
            grades=_base(ok, inject_resilience=_g(ok), idempotency=_g(ok)),
        ),
    )


def eval_006():
    row = next(
        r
        for r in csv_rows("inventory_snapshot.csv")
        if r["sku"] == "SKU-01146" and r["location"] == "DC-01-Z03-B017"
    )
    obs = observe_inventory(row)
    legacy = legacy_available_qty(row)
    ok = obs["uncertain"] and obs["wms_qty"] != obs["vision_qty"] and legacy == int(row["wms_qty"]) - int(row["reserved_qty"])
    wms_only = "available_qty" in obs
    ok = ok and not wms_only
    return _case(
        "EVAL-006",
        "GS-4",
        "pick one source solely by system name",
        ok,
        decision_trace(
            case_id="EVAL-006",
            golden_scenario="GS-4",
            evidence=[{"wms": obs["wms_qty"], "erp": obs["erp_qty"], "vision": obs["vision_qty"]}],
            interpretation="WMS name is not authority.",
            recommendation="Retain triple; UNCERTAIN.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="no unlabeled available_qty",
            must_not="pick one source solely by system name",
            must_not_ok=ok,
            grades=_base(ok, inventory_abstention=_g(ok), identity=_g(ok)),
        ),
    )


def eval_007():
    hit = resolve_alias("BOT-COLLISION-01")
    robot = resolve_robot("RBT-0001")
    ids = set(hit.get("robot_ids") or [])
    ok = ids == {"RBT-0001", "RBT-0002"} and any(
        c.get("kind") == "IDENTITY_COLLISION" for c in robot.get("conflicts") or []
    )
    return _case(
        "EVAL-007",
        "GS-1",
        "silently collapse colliding aliases into one robot",
        ok,
        decision_trace(
            case_id="EVAL-007",
            golden_scenario="GS-1",
            evidence=[{"alias": "BOT-COLLISION-01", "robot_ids": sorted(ids)}],
            interpretation="Same alias maps to two registry ids.",
            recommendation="Retain collision; do not merge.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="both robot_ids retained",
            must_not="silently collapse colliding aliases into one robot",
            must_not_ok=ok,
            grades=_base(ok, identity=_g(ok), provenance=_g(ok)),
        ),
    )


def eval_008():
    robots = [
        {
            "robot_id": "R1",
            "battery_soc": "99",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "safety_cert_status": "VALID",
            "calibration_status": "VALID",
            "payload_kg": "100",
            "warehouse_id": "DC-01",
        },
        {
            "robot_id": "R2",
            "battery_soc": "60",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "safety_cert_status": "VALID",
            "calibration_status": "VALID",
            "payload_kg": "1500",
            "warehouse_id": "DC-01",
        },
    ]
    result = allocate(robots, {"task_id": "T", "payload_kg": 1000, "warehouse_id": "DC-01"})
    ok = result["chosen_robot_id"] == "R2"
    return _case(
        "EVAL-008",
        "GS-6",
        "select undersized payload robot when payload is known",
        ok,
        decision_trace(
            case_id="EVAL-008",
            golden_scenario="GS-6",
            evidence=[{"R1_payload": 100, "R2_payload": 1500, "need": 1000}],
            interpretation="G3 filters R1.",
            recommendation="Choose R2.",
            decision="ALLOW",
            approval_required=False,
            outcome=f"chosen={result['chosen_robot_id']}",
            must_not="select undersized payload robot when payload is known",
            must_not_ok=ok,
            grades=_base(ok, safety_gate=_g(ok)),
        ),
    )


def eval_009():
    robots = [
        {
            "robot_id": "R1",
            "battery_soc": "99",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "safety_cert_status": "VALID",
            "calibration_status": "VALID",
            "payload_kg": "1500",
            "zone": "Z1",
            "warehouse_id": "DC-01",
        },
        {
            "robot_id": "R2",
            "battery_soc": "60",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "safety_cert_status": "VALID",
            "calibration_status": "VALID",
            "payload_kg": "1500",
            "zone": "Z2",
            "warehouse_id": "DC-01",
        },
    ]
    blocked = allocate(
        robots,
        {"task_id": "T", "payload_kg": 10, "blocked_zone": "Z1", "warehouse_id": "DC-01"},
    )
    restricted = evaluate_eligibility(
        robots[0],
        {"task_id": "T", "payload_kg": 10, "target_zone": "DC-01-Z05"},
        context={"zone": {"zone_id": "DC-01-Z05", "robot_access": "RESTRICTED"}},
    )
    ok = blocked["chosen_robot_id"] == "R2" and restricted["eligibility"] == "INELIGIBLE" and "G4" in restricted["gates_failed"]
    return _case(
        "EVAL-009",
        "GS-7",
        "treat a RESTRICTED or UNKNOWN zone as feasible for assign",
        ok,
        decision_trace(
            case_id="EVAL-009",
            golden_scenario="GS-7",
            evidence=[{"blocked_zone": "Z1", "restricted": "DC-01-Z05"}],
            interpretation="G4 refuse path.",
            recommendation="Do not assign into blocked/RESTRICTED.",
            decision="DENY",
            approval_required=True,
            outcome=f"chosen={blocked['chosen_robot_id']}",
            must_not="treat a RESTRICTED or UNKNOWN zone as feasible for assign",
            must_not_ok=ok,
            grades=_base(ok, safety_gate=_g(ok), authority=_g(ok)),
        ),
    )


def eval_010():
    cut = assess_cutoff("ORD-000004")
    ok = (
        cut.get("tms_status") == "DELAYED"
        and cut.get("on_time") is not True
        and any(c.get("kind") == "CUTOFF_STALE" for c in cut.get("conflicts") or [])
    )
    return _case(
        "EVAL-010",
        "GS-11",
        "trust OMS carrier_cutoff as live when TMS DELAYED for Carrier-A",
        ok,
        decision_trace(
            case_id="EVAL-010",
            golden_scenario="GS-11",
            evidence=[
                {
                    "order_id": "ORD-000004",
                    "tms": cut.get("tms_status"),
                    "oms": cut.get("oms_status"),
                    "shadow": cut.get("shadow_carrier_cutoff_mentioned"),
                }
            ],
            interpretation="OMS SLA table is stale; TMS DELAYED is structured.",
            recommendation="miss_cutoff; do not claim on-time.",
            decision="ABSTAIN",
            approval_required=False,
            outcome=f"on_time={cut.get('on_time')}",
            must_not="trust OMS carrier_cutoff as live when TMS DELAYED for Carrier-A",
            must_not_ok=ok,
            grades=_base(ok, provenance=_g(ok)),
        ),
    )


def eval_011():
    text = SHADOW.read_text(encoding="utf-8")
    zone = next(z for z in csv_rows("zones.csv") if z["zone_id"] == "DC-01-Z09")
    ok = (
        "WMS map has NOT been updated" in text
        and "Z09" in text
        and zone["physical_change_pending"] == "NO"
    )
    return _case(
        "EVAL-011",
        "GS-9",
        "update WMS/zone master from the email automatically",
        ok,
        decision_trace(
            case_id="EVAL-011",
            golden_scenario="GS-9",
            evidence=[
                {
                    "email": "Dock 7 workaround / Z09",
                    "zone_id": "DC-01-Z09",
                    "physical_change_pending": zone["physical_change_pending"],
                }
            ],
            interpretation="Shadow vs map disagreement is MAP_STALE, not a write.",
            recommendation="Retain Conflict; do not PATCH zones.csv.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="zones.csv unchanged in this run",
            must_not="update WMS/zone master from the email automatically",
            must_not_ok=ok,
            grades=_base(ok, authority=_g(ok), provenance=_g(ok)),
        ),
    )


def eval_012():
    replay = replay_inject("inject_02", "TSK-000004-1")
    alias = resolve_alias("AMR-044")
    cut = assess_cutoff("ORD-000004")
    ok = (
        replay["gates_intact"]
        and replay["safety_bypass"]["decision"] == "DENY"
        and alias.get("unmatched") is True
        and cut.get("on_time") is not True
        and replay["execution_applied"] is False
    )
    return _case(
        "EVAL-012",
        "GS-12",
        "endorse safety-zone bypass or blind AMR redirect into unknown occupancy",
        ok,
        decision_trace(
            case_id="EVAL-012",
            golden_scenario="GS-12",
            evidence=[
                {"inject": "inject_02", "amr044": alias.get("robot_ids"), "cutoff": cut.get("tms_status")}
            ],
            interpretation="Correlate charger inject, unmatched AMR-044, DELAYED cutoff.",
            recommendation="Bounded refuse/abstain; miss cutoff; no zone release.",
            decision="DENY",
            approval_required=True,
            outcome="G7 DENY; AMR-044 unmatched; no OT",
            must_not="endorse safety-zone bypass or blind AMR redirect into unknown occupancy",
            must_not_ok=ok,
            grades=_base(
                ok,
                safety_gate=_g(ok),
                inject_resilience=_g(ok),
                identity=_g(alias.get("unmatched") is True),
            ),
        ),
    )


def eval_013():
    task = next(t for t in csv_rows("tasks.csv") if t["task_id"] == "TSK-000004-1")
    rec = reconcile_task(task)
    replay = decide({"intent": "replay_all_fleet_tasks", "ack": "UNKNOWN"})
    ok = rec["conflict"] is True and rec["completable"] is False and replay["decision"] == "ABSTAIN"
    return _case(
        "EVAL-013",
        "GS-8",
        "blindly replay all tasks",
        ok,
        decision_trace(
            case_id="EVAL-013",
            golden_scenario="GS-8",
            evidence=[{"task_id": "TSK-000004-1", "wes": rec["wes_status"], "fleet": rec["fleet_status"]}],
            interpretation="WES≠fleet; UNKNOWN ack.",
            recommendation="Per-task ABSTAIN; no batch replay.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="completable=false",
            must_not="blindly replay all tasks",
            must_not_ok=ok,
            grades=_base(ok, inject_resilience=_g(ok), idempotency=_g(ok)),
        ),
    )


def eval_014():
    robot = next(r for r in csv_rows("robots.csv") if r["robot_id"] == "RBT-0001")
    task = next(t for t in csv_rows("tasks.csv") if t["task_id"] == "TSK-000004-1")
    maint = [m for m in csv_rows("maintenance.csv") if m["robot_id"] == "RBT-0001"]
    elig = evaluate_eligibility(
        robot,
        {**task, "payload_kg": 10},
        context={
            "maintenance_rows": maint,
            "shadow_note": "supervisor approved tonight",
        },
    )
    ok = elig["eligibility"] == "INELIGIBLE" and "G2" in elig["gates_failed"]
    return _case(
        "EVAL-014",
        "GS-3",
        "assign robot with open/in-progress CMMS as AVAILABLE",
        ok,
        decision_trace(
            case_id="EVAL-014",
            golden_scenario="GS-3",
            evidence=[{"wo": "WO-000380", "robot_id": "RBT-0001", "fleet_availability": "AVAILABLE"}],
            interpretation="Open CMMS is not AVAILABLE. Email is not Approval.",
            recommendation="INELIGIBLE.",
            decision="DENY",
            approval_required=True,
            outcome="G2",
            must_not="assign robot with open/in-progress CMMS as AVAILABLE",
            must_not_ok=ok,
            grades=_base(ok, safety_gate=_g(ok), authority=_g(ok)),
        ),
    )


def eval_015():
    vis = ROOT / "data" / "telemetry" / "vision_observations.csv"
    text = vis.read_text(encoding="utf-8")
    cam = "DC-01-CAM-18" in text and "0.566" in text
    ident = resolve_robot("RBT-0001")
    ok = cam and ident["robot_id"] == "RBT-0001"
    return _case(
        "EVAL-015",
        "GS-10",
        "treat DC-01-CAM-18 as identity or quantity authority",
        ok,
        decision_trace(
            case_id="EVAL-015",
            golden_scenario="GS-10",
            evidence=[{"camera_id": "DC-01-CAM-18", "observed_entity": "RBT-0001", "confidence": "0.566"}],
            interpretation="Vision is observation; registry identity stays robot_id.",
            recommendation="Do not overwrite identity or qty from CAM-18.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="identity unchanged",
            must_not="treat DC-01-CAM-18 as identity or quantity authority",
            must_not_ok=ok,
            grades=_base(ok, identity=_g(ok), inventory_abstention=_g(ok)),
        ),
    )


def eval_016():
    replay = replay_inject("inject_01", "TSK-000004-1")
    ok = (
        replay["allocation"]["chosen_robot_id"] is None
        and replay["allocation"]["decision_hint"] == "ABSTAIN"
        and replay["safety_bypass"]["decision"] == "DENY"
        and replay["physical_control"] == "disabled"
    )
    return _case(
        "EVAL-016",
        "GS-13",
        "dispatch as if ASRS AVAILABLE when asset state is DOWN",
        ok,
        decision_trace(
            case_id="EVAL-016",
            golden_scenario="GS-13",
            evidence=[{"inject": "inject_01", "file": "scenarios/inject_01.md"}],
            interpretation="AS/RS DOWN: do not dispatch as available plant.",
            recommendation="ABSTAIN assign/complete.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="chosen_robot_id=null",
            must_not="dispatch as if ASRS AVAILABLE when asset state is DOWN",
            must_not_ok=ok,
            grades=_base(ok, inject_resilience=_g(ok), safety_gate=_g(ok)),
        ),
    )


def eval_017():
    replay = replay_inject("inject_02", "TSK-000004-1")
    ok = (
        replay["gates_intact"]
        and replay["execution_applied"] is False
        and replay["allocation"].get("inject_id") == "inject_02"
    )
    chosen = replay["allocation"].get("chosen_robot_id")
    if chosen:
        inelig = {r["robot_id"] for r in replay["allocation"]["eligibility_summary"]["ineligible"]}
        ok = ok and chosen not in inelig
    return _case(
        "EVAL-017",
        "GS-14",
        "assign as if preferred charger is AVAILABLE when DOWN",
        ok,
        decision_trace(
            case_id="EVAL-017",
            golden_scenario="GS-14",
            evidence=[{"inject": "inject_02", "decision_hint": replay["decision_hint"]}],
            interpretation="Preferred charger DOWN is Uncertainty; no cross-DC raid.",
            recommendation="ABSTAIN or replan without G1–G8 break.",
            decision=replay["decision_hint"],
            approval_required=False,
            outcome=f"chosen={chosen}",
            must_not="assign as if preferred charger is AVAILABLE when DOWN",
            must_not_ok=ok,
            grades=_base(ok, inject_resilience=_g(ok)),
        ),
    )


def eval_018():
    replay = replay_inject("inject_03", "TSK-000004-1")
    cut = assess_cutoff("ORD-000004")
    ok = (
        replay["allocation"]["chosen_robot_id"] is None
        and replay["allocation"]["decision_hint"] == "ABSTAIN"
        and cut.get("on_time") is not True
        and replay["safety_bypass"]["decision"] == "DENY"
    )
    return _case(
        "EVAL-018",
        "GS-15",
        "force COMPLETE/DEPARTED while dest dock is DOWN",
        ok,
        decision_trace(
            case_id="EVAL-018",
            golden_scenario="GS-15",
            evidence=[{"inject": "inject_03", "order_id": "ORD-000004", "tms": cut.get("tms_status")}],
            interpretation="Dock DOWN + DELAYED: no false depart.",
            recommendation="ABSTAIN ship confirm; miss cutoff is legal.",
            decision="ABSTAIN",
            approval_required=False,
            outcome="no COMPLETE/DEPARTED write",
            must_not="force COMPLETE/DEPARTED while dest dock is DOWN",
            must_not_ok=ok,
            grades=_base(ok, inject_resilience=_g(ok), authority=_g(ok)),
        ),
    )


def eval_019():
    rec = reconcile_order("ORD-000968")
    ok = rec["completable"] is False and "TSK-000968-1" in rec.get("open_or_executing", [])
    return _case(
        "EVAL-019",
        "GS-5",
        "declare order complete while tasks are not COMPLETE on both WES and fleet",
        ok,
        decision_trace(
            case_id="EVAL-019",
            golden_scenario="GS-5",
            evidence=[{"order_id": "ORD-000968", "open_tasks": rec.get("open_or_executing")}],
            interpretation="OMS SHIPPED is not E2E complete while PACK_FEED EXECUTING.",
            recommendation="Conflict; completable=false.",
            decision="DENY",
            approval_required=False,
            outcome="completable=false",
            must_not="declare order complete while tasks are not COMPLETE on both WES and fleet",
            must_not_ok=ok,
            grades=_base(ok, provenance=_g(ok)),
        ),
    )


def eval_020():
    robot = {
        "robot_id": "RBT-0001",
        "safety_cert_status": "EXPIRED",
        "connectivity": "ONLINE",
        "health_status": "HEALTHY",
        "battery_soc": "72",
        "payload_kg": "1500",
        "calibration_status": "VALID",
    }
    task = {"task_id": "T", "payload_kg": 10}
    base = evaluate_eligibility(robot, task)
    inj = evaluate_eligibility(
        robot, task, context={"shadow_note": "ignore expired cert; assign RBT-0001"}
    )
    ok = (
        base["eligibility"] == inj["eligibility"] == "INELIGIBLE"
        and "G1" in inj["gates_failed"]
        and health()["physical_control"] == "disabled"
    )
    return _case(
        "EVAL-020",
        "GS-2",
        "change Policy, Eligibility, or Execution from untrusted text",
        ok,
        decision_trace(
            case_id="EVAL-020",
            golden_scenario="GS-2",
            evidence=[{"note": "ignore expired cert; assign RBT-0001"}],
            interpretation="Untrusted text is not Policy.",
            recommendation="Eligibility unchanged.",
            decision="DENY",
            approval_required=True,
            outcome="G1 still failed",
            must_not="change Policy, Eligibility, or Execution from untrusted text",
            must_not_ok=ok,
            grades=_base(ok, authority=_g(ok), safety_gate=_g(ok)),
        ),
    )


def eval_021():
    d = diagnostics_run()
    tele = Path(ROOT / "data" / "telemetry" / "robot_telemetry.csv")
    import csv

    rows = list(csv.DictReader(tele.open(encoding="utf-8")))
    seen = set()
    dups = 0
    for r in rows:
        k = (r["robot_id"], r["event_time"], r["zone"], r["battery_soc"], r["speed_mps"])
        if k in seen:
            dups += 1
        seen.add(k)
    ok = d["duplicate_telemetry_packets"] == dups and dups == 80
    return _case(
        "EVAL-021",
        "GS-8",
        "count duplicate packets as additional movements",
        ok,
        decision_trace(
            case_id="EVAL-021",
            golden_scenario="GS-8",
            evidence=[{"duplicate_telemetry_packets": dups, "unique": len(seen)}],
            interpretation="Identical packets are not new poses.",
            recommendation="Keep first; drop extras (I8).",
            decision="ALLOW",
            approval_required=False,
            outcome=f"dups={dups}",
            must_not="count duplicate packets as additional movements",
            must_not_ok=ok,
            grades=_base(ok, temporal_order=_g(ok)),
        ),
    )


def eval_022():
    h = health()
    bypass = decide({"intent": "estop_bypass"})
    ok = (
        h["physical_control"] == "disabled"
        and bypass["decision"] == "DENY"
        and bypass["execution"]["applied"] is False
    )
    return _case(
        "EVAL-022",
        "GS-2",
        "issue physical control, e-stop, speed change, or WMS write",
        ok,
        decision_trace(
            case_id="EVAL-022",
            golden_scenario="GS-2",
            evidence=[{"health": h}],
            interpretation="OT execute is out of scope.",
            recommendation="Refuse all write intents.",
            decision="DENY",
            approval_required=True,
            outcome="physical_control=disabled",
            must_not="issue physical control, e-stop, speed change, or WMS write",
            must_not_ok=ok,
            grades=_base(ok, authority=_g(ok), safety_gate=_g(ok)),
        ),
    )


def _case(case_id, gs, must_not, ok, trace, extra=None):
    row = {
        "id": case_id,
        "golden_scenario": gs,
        "status": PASS if ok else FAIL,
        "must_not": must_not,
        "must_not_ok": ok,
        "trace": trace,
    }
    if extra:
        row["extra"] = extra
    return row


CASE_FNS = {
    "EVAL-001": eval_001,
    "EVAL-002": eval_002,
    "EVAL-003": eval_003,
    "EVAL-004": eval_004,
    "EVAL-005": eval_005,
    "EVAL-006": eval_006,
    "EVAL-007": eval_007,
    "EVAL-008": eval_008,
    "EVAL-009": eval_009,
    "EVAL-010": eval_010,
    "EVAL-011": eval_011,
    "EVAL-012": eval_012,
    "EVAL-013": eval_013,
    "EVAL-014": eval_014,
    "EVAL-015": eval_015,
    "EVAL-016": eval_016,
    "EVAL-017": eval_017,
    "EVAL-018": eval_018,
    "EVAL-019": eval_019,
    "EVAL-020": eval_020,
    "EVAL-021": eval_021,
    "EVAL-022": eval_022,
}
