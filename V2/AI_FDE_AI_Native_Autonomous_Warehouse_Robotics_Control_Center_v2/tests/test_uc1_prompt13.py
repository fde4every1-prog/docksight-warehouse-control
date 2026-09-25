"""Prompt 13 — filter-then-score, cutoff, inject replay.

legacy choose_robot xfails stay in test_known_legacy_defects.py.
No LLM. physical_control disabled. Do not rewrite data/.
"""

from warehouse_control.allocator.filter_score import allocate, allocate_for_task, rejection_reasons
from warehouse_control.api import health
from warehouse_control.decision.engine import decide
from warehouse_control.fulfillment.cutoff import assess_cutoff
from warehouse_control.injects.replay import replay_inject
from warehouse_control.legacy.allocator import choose_robot, legacy_score


def _base_robot(robot_id, battery, **extra):
    row = {
        "robot_id": robot_id,
        "battery_soc": battery,
        "connectivity": "ONLINE",
        "health_status": "HEALTHY",
        "safety_cert_status": "VALID",
        "calibration_status": "VALID",
        "payload_kg": "1500",
        "warehouse_id": "DC-01",
    }
    row.update(extra)
    return row


def test_uc1_allocator_rejects_expired_cert():
    robots = [
        _base_robot("R1", "99", safety_cert_status="EXPIRED"),
        _base_robot("R2", "60"),
    ]
    result = allocate(robots, {"task_id": "T1", "payload_kg": 10, "warehouse_id": "DC-01"})
    assert result["chosen_robot_id"] == "R2"
    assert result["legacy_choice_robot_id"] == "R1"
    assert result["score_path"] == "filter_then_score"
    assert result["physical_control"] == "disabled"
    assert result["execution_applied"] is False


def test_uc1_allocator_respects_payload():
    robots = [
        _base_robot("R1", "99", payload_kg="100"),
        _base_robot("R2", "60", payload_kg="1500"),
    ]
    result = allocate(robots, {"task_id": "T1", "payload_kg": 1000, "warehouse_id": "DC-01"})
    assert result["chosen_robot_id"] == "R2"
    ineligible_ids = {r["robot_id"] for r in result["eligibility_summary"]["ineligible"]}
    assert "R1" in ineligible_ids


def test_uc1_allocator_avoids_blocked_zone():
    robots = [
        _base_robot("R1", "99", zone="Z1"),
        _base_robot("R2", "60", zone="Z2"),
    ]
    result = allocate(
        robots,
        {"task_id": "T1", "payload_kg": 10, "blocked_zone": "Z1", "warehouse_id": "DC-01"},
    )
    assert result["chosen_robot_id"] == "R2"


def test_uc1_does_not_choose_rbt0001_open_cmms():
    result = allocate_for_task("TSK-000004-1")
    assert result["score_path"] == "filter_then_score"
    ineligible = {r["robot_id"]: r for r in result["eligibility_summary"]["ineligible"]}
    assert "RBT-0001" in ineligible
    assert "G2" in ineligible["RBT-0001"]["gates_failed"]
    assert result["chosen_robot_id"] != "RBT-0001"
    assert result["physical_control"] == "disabled"
    assert choose_robot is not None and legacy_score is not None


def test_cutoff_ord000004_not_on_time_from_oms():
    cut = assess_cutoff("ORD-000004")
    assert cut["tms_status"] == "DELAYED"
    assert cut["carrier"] == "Carrier-A"
    assert cut["on_time"] is not True
    assert any(c["kind"] == "CUTOFF_STALE" for c in cut["conflicts"])
    assert cut["shadow_carrier_cutoff_mentioned"] is True
    miss = decide({"intent": "miss_cutoff", "order_id": "ORD-000004"})
    bypass = decide({"intent": "release_zone", "reason": "hit Carrier-A cutoff"})
    assert miss["decision"] in {"ALLOW", "ABSTAIN"}
    assert bypass["decision"] == "DENY"


def test_rejection_reasons_rbt0001():
    reasons = rejection_reasons("RBT-0001", "TSK-000004-1")
    assert reasons["eligibility"] == "INELIGIBLE"
    assert "G2" in reasons["gates_failed"]
    assert reasons["physical_control"] == "disabled"


def test_inject_02_charging_abstains_or_replans_without_gate_break():
    replay = replay_inject("inject_02", "TSK-000004-1")
    assert replay["gates_intact"] is True
    assert replay["safety_bypass"]["decision"] == "DENY"
    assert replay["physical_control"] == "disabled"
    assert replay["execution_applied"] is False
    alloc = replay["allocation"]
    assert alloc["decision_hint"] in {"ABSTAIN", "ALLOW"}
    if alloc["chosen_robot_id"]:
        ineligible = {r["robot_id"] for r in alloc["eligibility_summary"]["ineligible"]}
        assert alloc["chosen_robot_id"] not in ineligible
        assert alloc["chosen_robot_id"] != "RBT-0001"


def test_inject_03_dock_closure_abstains_without_safety_bypass():
    replay = replay_inject("inject_03", "TSK-000004-1")
    assert replay["allocation"]["outbound_blocked"] is True
    assert replay["allocation"]["chosen_robot_id"] is None
    assert replay["allocation"]["decision_hint"] == "ABSTAIN"
    assert replay["safety_bypass"]["decision"] == "DENY"
    assert replay["miss_cutoff_recommend"]["decision"] in {"ALLOW", "ABSTAIN"}
    assert replay["miss_cutoff_recommend"]["execution"]["applied"] is False
    assert health()["physical_control"] == "disabled"
