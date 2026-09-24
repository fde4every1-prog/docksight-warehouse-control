"""Additive happy-path slice ORD-009999. Brownfield FAIL IDs stay."""

from warehouse_control.eligibility.policy import evaluate_eligibility
from warehouse_control.fulfillment.cutoff import assess_cutoff
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.repository import csv_rows
from warehouse_control.tasks.reconcile import reconcile_order, reconcile_task


def test_happy_order_header_agrees_and_is_completable():
    order = next(o for o in csv_rows("orders.csv") if o["order_id"] == "ORD-009999")
    assert order["oms_status"] == "SHIPPED"
    assert order["wms_status"] == "SHIPPED"
    rec = reconcile_order("ORD-009999")
    assert rec["completable"] is True
    assert rec["task_count"] == 1


def test_happy_task_fleet_and_wes_complete_same_site():
    task = next(t for t in csv_rows("tasks.csv") if t["task_id"] == "TSK-009999-1")
    robot = next(r for r in csv_rows("robots.csv") if r["robot_id"] == "RBT-0012")
    assert task["wes_status"] == "COMPLETE"
    assert task["fleet_status"] == "COMPLETE"
    assert task["assigned_robot"] == "RBT-0012"
    assert task["warehouse_id"] == robot["warehouse_id"] == "DC-01"
    rec = reconcile_task(task)
    assert rec["conflict"] is False
    assert rec["completable"] is True


def test_happy_robot_passes_hard_gates():
    robot = next(r for r in csv_rows("robots.csv") if r["robot_id"] == "RBT-0012")
    task = next(t for t in csv_rows("tasks.csv") if t["task_id"] == "TSK-009999-1")
    maint = [m for m in csv_rows("maintenance.csv") if m["robot_id"] == "RBT-0012"]
    elig = evaluate_eligibility(robot, task, {"maintenance_rows": maint})
    assert "G1" not in elig["gates_failed"]
    assert "G2" not in elig["gates_failed"]
    assert "I2" not in elig["gates_failed"]
    assert elig["eligibility"] != "INELIGIBLE"


def test_happy_inventory_not_uncertain():
    row = next(
        r
        for r in csv_rows("inventory_snapshot.csv")
        if r["sku"] == "SKU-09999" and r["location"] == "DC-01-Z02-B099"
    )
    obs = observe_inventory(row)
    assert obs["uncertain"] is False
    assert str(obs["wms_qty"]) == str(obs["erp_qty"]) == str(obs["vision_qty"]) == "40"


def test_happy_shipment_not_delayed():
    ship = next(s for s in csv_rows("shipments.csv") if s["order_id"] == "ORD-009999")
    cut = assess_cutoff("ORD-009999")
    assert ship["tms_status"] == "DEPARTED"
    assert ship["actual_departure"].strip() != ""
    assert cut["tms_status"] != "DELAYED"


def test_brownfield_fail_ids_still_present():
    bad_order = next(o for o in csv_rows("orders.csv") if o["order_id"] == "ORD-000004")
    bad_inv = next(
        r
        for r in csv_rows("inventory_snapshot.csv")
        if r["sku"] == "SKU-01146" and r["location"] == "DC-01-Z03-B017"
    )
    assert bad_order["oms_status"] != bad_order["wms_status"]
    assert observe_inventory(bad_inv)["uncertain"] is True
    assert len(csv_rows("robots.csv")) == 712
