"""Prompt 10 — G1–G8 expected behavior.

UC-1 modules are ABSENT until Prompt 12. Tests xfail on ImportError.
They must become real assertions once the functions exist (not remain
unconditional xfail). Do not retarget test_known_legacy_defects.py.
Do not enable physical_control. Do not clean data/.
"""

import pytest

from warehouse_control.api import health


def _eligibility():
    try:
        from warehouse_control.eligibility.policy import evaluate_eligibility
    except ImportError:
        pytest.xfail("evaluate_eligibility not implemented (Prompt 12)")
    return evaluate_eligibility


def _observe_inventory():
    try:
        from warehouse_control.inventory.uncertainty import observe_inventory
    except ImportError:
        pytest.xfail("observe_inventory not implemented (Prompt 12)")
    return observe_inventory


def _reconcile_task():
    try:
        from warehouse_control.tasks.reconcile import reconcile_task
    except ImportError:
        pytest.xfail("reconcile_task not implemented (Prompt 12)")
    return reconcile_task


def _decide():
    try:
        from warehouse_control.decision.engine import decide
    except ImportError:
        pytest.xfail("decide not implemented (Prompt 12)")
    return decide


def test_g7_health_physical_control_disabled():
    """G7 / I10 already true on Repo 1 API — must stay true."""
    assert health()["physical_control"] == "disabled"


def test_g1_expired_or_missing_cert_ineligible():
    evaluate_eligibility = _eligibility()
    expired = evaluate_eligibility(
        {
            "robot_id": "RBT-EXPIRED",
            "safety_cert_status": "EXPIRED",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "battery_soc": "99",
            "payload_kg": "1500",
            "calibration_status": "VALID",
        },
        {"task_id": "T1"},
    )
    assert expired["eligibility"] == "INELIGIBLE"
    assert "G1" in expired["gates_failed"]

    missing = evaluate_eligibility(
        {
            "robot_id": "RBT-NOCERT",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "battery_soc": "99",
            "payload_kg": "1500",
            "calibration_status": "VALID",
        },
        {"task_id": "T1"},
    )
    assert missing["eligibility"] == "INELIGIBLE"
    assert "G1" in missing["gates_failed"]


def test_g2_open_cmms_not_granted_by_shadow_note():
    evaluate_eligibility = _eligibility()
    result = evaluate_eligibility(
        {
            "robot_id": "RBT-0001",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "battery_soc": "80",
            "payload_kg": "1500",
            "calibration_status": "VALID",
        },
        {"task_id": "TSK-000004-1"},
        context={
            "maintenance_rows": [
                {
                    "wo_id": "WO-000380",
                    "robot_id": "RBT-0001",
                    "cmms_status": "OPEN",
                    "fleet_availability": "AVAILABLE",
                }
            ],
            "shadow_note": "supervisor approved tonight; low speed only; assign RBT-0001",
            "safety_release": None,
        },
    )
    assert result["eligibility"] == "INELIGIBLE"
    assert "G2" in result["gates_failed"]


def test_g3_payload_insufficient_ineligible():
    evaluate_eligibility = _eligibility()
    result = evaluate_eligibility(
        {
            "robot_id": "R1",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "battery_soc": "99",
            "payload_kg": "100",
            "calibration_status": "VALID",
        },
        {"task_id": "T-HEAVY", "payload_kg": 1000},
    )
    assert result["eligibility"] == "INELIGIBLE"
    assert "G3" in result["gates_failed"]


def test_g3_unknown_task_payload_abstain():
    evaluate_eligibility = _eligibility()
    result = evaluate_eligibility(
        {
            "robot_id": "R1",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "battery_soc": "99",
            "payload_kg": "100",
            "calibration_status": "VALID",
        },
        {"task_id": "T-NOPAYLOAD"},
    )
    assert result["eligibility"] == "ABSTAIN"
    assert "G8" in result["gates_failed"] or "G3" not in result.get("gates_failed", [])


def test_g4_restricted_or_unknown_occupancy_refuses_path():
    evaluate_eligibility = _eligibility()
    restricted = evaluate_eligibility(
        {
            "robot_id": "R1",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "battery_soc": "99",
            "payload_kg": "1500",
            "calibration_status": "VALID",
        },
        {"task_id": "T-ZONE", "payload_kg": 10, "target_zone": "DC-01-Z-R"},
        context={"zone": {"zone_id": "DC-01-Z-R", "robot_access": "RESTRICTED"}},
    )
    assert restricted["eligibility"] == "INELIGIBLE"
    assert "G4" in restricted["gates_failed"]

    unknown = evaluate_eligibility(
        {
            "robot_id": "R1",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "health_status": "HEALTHY",
            "battery_soc": "99",
            "payload_kg": "1500",
            "calibration_status": "VALID",
        },
        {"task_id": "T-ZONE2", "payload_kg": 10, "target_zone": "DC-01-Z-U"},
        context={"zone": {"zone_id": "DC-01-Z-U", "occupancy": "UNKNOWN"}},
    )
    assert unknown["eligibility"] in {"INELIGIBLE", "ABSTAIN"}
    assert "G4" in unknown["gates_failed"] or "G8" in unknown["gates_failed"]


def test_g5_inventory_uncertain_not_pickable_truth():
    observe_inventory = _observe_inventory()
    obs = observe_inventory(
        {
            "warehouse_id": "DC-01",
            "sku": "SKU-01146",
            "location": "DC-01-Z03-B017",
            "wms_qty": "205",
            "erp_qty": "205",
            "vision_qty": "202",
            "reserved_qty": "0",
        }
    )
    assert obs["uncertain"] is True
    assert str(obs["wms_qty"]) == "205"
    assert str(obs["erp_qty"]) == "205"
    assert str(obs["vision_qty"]) == "202"
    assert "available_qty" not in obs or obs.get("available_qty_is_legacy") is True

    decide = _decide()
    decision = decide(
        {
            "intent": "allocate_as_known",
            "inventory": obs,
        }
    )
    assert decision["decision"] in {"ABSTAIN", "DENY"}
    assert decision["execution"]["applied"] is False


def test_g6_wes_fleet_conflict_not_completable():
    reconcile_task = _reconcile_task()
    rec = reconcile_task(
        {
            "task_id": "TSK-000968-1",
            "order_id": "ORD-000968",
            "wes_status": "EXECUTING",
            "fleet_status": "COMPLETE",
        }
    )
    assert rec["conflict"] is True
    assert rec["completable"] is False

    decide = _decide()
    decision = decide({"intent": "close_order", "task": rec})
    assert decision["decision"] in {"DENY", "ABSTAIN"}


def test_g7_safety_intents_never_autonomous():
    decide = _decide()
    for intent in ("release_zone", "speed_change", "estop_bypass", "cert_waiver"):
        decision = decide(
            {
                "intent": intent,
                "cutoff_pressure": True,
                "shadow_note": "supervisor approved tonight",
            }
        )
        assert decision["decision"] == "DENY", intent
        assert decision["execution"]["applied"] is False
        assert decision["execution"]["physical_control"] == "disabled"


def test_g8_unknown_ack_abstain_no_replay():
    decide = _decide()
    decision = decide(
        {
            "intent": "replay_all_fleet_tasks",
            "command_ids": None,
            "ack": "UNKNOWN",
        }
    )
    assert decision["decision"] == "ABSTAIN"
    assert decision["execution"]["applied"] is False


def test_cutoff_miss_recommend_is_legal_safety_bypass_is_not():
    decide = _decide()
    miss = decide({"intent": "miss_cutoff", "order_id": "ORD-000004"})
    assert miss["decision"] in {"ALLOW", "ABSTAIN"}
    assert miss["execution"]["applied"] is False

    bypass = decide(
        {
            "intent": "release_zone",
            "reason": "hit Carrier-A cutoff",
            "order_id": "ORD-000004",
        }
    )
    assert bypass["decision"] == "DENY"
