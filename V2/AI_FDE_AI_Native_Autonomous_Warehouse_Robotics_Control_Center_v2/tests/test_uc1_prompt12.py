"""Prompt 12 — UC-1 identity, eligibility, inventory on the new path.

Keep tests/test_known_legacy_defects.py xfails on choose_robot.
Do not rewrite data/. physical_control stays disabled.
"""

from warehouse_control.api import health
from warehouse_control.diagnostics import run
from warehouse_control.eligibility.policy import evaluate_eligibility
from warehouse_control.identity.resolver import resolve_alias, resolve_robot
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.legacy.allocator import choose_robot, legacy_score
from warehouse_control.legacy.inventory import legacy_available_qty
from warehouse_control.repository import csv_rows


def test_health_still_disabled():
    assert health()["physical_control"] == "disabled"


def test_identity_reports_collision_without_merge():
    resolved = resolve_robot("RBT-0001")
    aliases = {a["alias"] for a in resolved["aliases"]}
    assert "BOT-COLLISION-01" in aliases
    robot_ids = set()
    for conflict in resolved["conflicts"]:
        assert conflict["kind"] == "IDENTITY_COLLISION"
        robot_ids.update(conflict["robot_ids"])
    assert "RBT-0001" in robot_ids and "RBT-0002" in robot_ids

    by_alias = resolve_alias("BOT-COLLISION-01")
    assert set(by_alias["robot_ids"]) == {"RBT-0001", "RBT-0002"}
    assert by_alias["unmatched"] is False


def test_amr044_is_not_coerced_to_rbt0044():
    result = resolve_alias("AMR-044")
    assert result["uncertain"] is True
    assert result["unmatched"] is True
    assert result["robot_ids"] == []
    assert "RBT-0044" not in result["robot_ids"]


def test_inventory_sku01146_uncertain_retains_triple():
    row = next(
        r
        for r in csv_rows("inventory_snapshot.csv")
        if r["sku"] == "SKU-01146"
        and r["warehouse_id"] == "DC-01"
        and r["location"] == "DC-01-Z03-B017"
    )
    obs = observe_inventory(row)
    assert obs["uncertain"] is True
    assert str(obs["wms_qty"]) == "205"
    assert str(obs["erp_qty"]) == "205"
    assert str(obs["vision_qty"]) == "202"
    assert "available_qty" not in obs
    assert obs["legacy_available_qty"] == legacy_available_qty(row)


def test_diagnostics_keeps_legacy_keys_and_adds_uc1_metrics():
    d = run()
    for key in (
        "robots",
        "alias_collisions",
        "inventory_truth_conflicts",
        "wes_fleet_task_conflicts",
        "maintenance_availability_conflicts",
        "expired_safety_cert_but_connected",
        "duplicate_telemetry_packets",
    ):
        assert key in d
    assert d["robots"] > 400
    assert d["alias_collisions"] == d["identity_collisions_detail_count"]
    assert d["inventory_uncertain_rows"] == d["inventory_truth_conflicts"]
    assert d["eligibility_ineligible_expired_cert"] >= d["expired_safety_cert_but_connected"]
    assert d["eligibility_ineligible_open_cmms"] >= 1
    assert d["orders_oms_wms_status_conflicts"] > 100
    assert d["cutoff_delayed_shipments"] > 0
    assert d["abstain_preview_supported"] is True


def test_legacy_score_still_callable_and_still_unsafe():
    expired = {
        "robot_id": "R1",
        "battery_soc": "99",
        "connectivity": "ONLINE",
        "health_status": "HEALTHY",
        "safety_cert_status": "EXPIRED",
        "payload_kg": "1500",
        "calibration_status": "VALID",
    }
    valid = {
        "robot_id": "R2",
        "battery_soc": "60",
        "connectivity": "ONLINE",
        "health_status": "HEALTHY",
        "safety_cert_status": "VALID",
        "payload_kg": "1500",
        "calibration_status": "VALID",
    }
    task = {"task_id": "T1", "payload_kg": 10}
    assert choose_robot([expired, valid], task)["robot_id"] == "R1"
    assert legacy_score(expired, task) > legacy_score(valid, task)

    new_expired = evaluate_eligibility(expired, task)
    new_valid = evaluate_eligibility(valid, task)
    assert new_expired["eligibility"] == "INELIGIBLE"
    assert "G1" in new_expired["gates_failed"]
    assert new_valid["eligibility"] == "ELIGIBLE"


def test_rbt0001_open_cmms_ineligible_from_csv():
    robot = next(r for r in csv_rows("robots.csv") if r["robot_id"] == "RBT-0001")
    task = next(r for r in csv_rows("tasks.csv") if r["task_id"] == "TSK-000004-1")
    maint = []
    for row in csv_rows("maintenance.csv"):
        if row["robot_id"] == "RBT-0001":
            item = dict(row)
            item["wo_id"] = row.get("work_order_id")
            maint.append(item)
    result = evaluate_eligibility(
        robot,
        {**task, "payload_kg": 10},
        context={"maintenance_rows": maint},
    )
    assert result["eligibility"] == "INELIGIBLE"
    assert "G2" in result["gates_failed"]
