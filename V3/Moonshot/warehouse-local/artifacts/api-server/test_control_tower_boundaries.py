"""Cross-cutting accounting boundaries; all work is isolated from demo history."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from test_fulfillment_v2 import effective, fulfillment, order, v2db  # noqa: F401


def test_concurrent_acceptance_cannot_oversell(v2db):
    # Existing non-Bazaar callers retain their accepted/held behavior.
    requests = [
        order([("A", 80)], order_source="control_tower"),
        order([("A", 80)], order_source="control_tower"),
    ]
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(fulfillment.create_order, requests))
    assert sorted(result["status"] for result in results) == ["active", "held"]
    row = effective("A")
    assert (row["wms_qty"], row["reserved_qty"], row["picked_qty"]) == (20, 80, 0)


def test_cancel_and_pick_race_has_one_conserved_outcome(v2db):
    created = fulfillment.create_order(order([("A", 10)]))
    fulfillment.run_executor_once(v2db["now"])
    due = v2db["now"] + timedelta(seconds=45)
    with ThreadPoolExecutor(max_workers=2) as workers:
        cancellation = workers.submit(fulfillment.command_order, created["id"], "cancel")
        pick = workers.submit(fulfillment.run_executor_once, due)
        cancellation.result()
        pick.result()
    row = effective("A")
    assert (row["wms_qty"], row["reserved_qty"], row["picked_qty"]) in {
        (100, 0, 0), (90, 0, 10),
    }
    assert row["wms_qty"] + row["reserved_qty"] + row["picked_qty"] == 100


def test_reinitialization_and_lost_response_retain_identity(v2db):
    request = order([("A", 10)], service="Standard")
    created = fulfillment.create_order(request)
    fulfillment._init_db()
    replay = fulfillment.create_order(request)
    assert replay["id"] == created["id"]
    assert replay["cutoff_at"] == "2030-01-02T00:00:00Z"
    assert replay["sub_orders"][0]["id"] == created["sub_orders"][0]["id"]
    assert len(fulfillment.get_order(replay["id"])["inventory_movements"]) == 1
    assert effective("A")["reserved_qty"] == 10


def test_opening_external_reservations_are_not_released_by_new_order(v2db):
    raw = fulfillment._raw_source_rows("inventory")[0]
    raw["reserved_qty"] = "30"
    with fulfillment.db_transaction() as db:
        db.execute("DROP TABLE inventory_snapshot")
        fulfillment.ensure_inventory(db)
    row = effective("A")
    assert (row["wms_qty"], row["reserved_qty"], row["external_reserved_qty"]) == (70, 30, 30)
    created = fulfillment.create_order(order([("A", 10)]))
    fulfillment.command_order(created["id"], "cancel")
    row = effective("A")
    assert (row["wms_qty"], row["reserved_qty"], row["external_reserved_qty"]) == (70, 30, 30)
    fulfillment._init_db()
    assert effective("A")["wms_qty"] == 70


def test_source_disagreement_survives_acceptance_and_stale_correction_rejects(v2db):
    row = effective("A")
    with fulfillment.db_transaction() as db:
        fulfillment.correct_inventory(
            db, row["inventory_row_id"], {"vision_qty": 90}, "free",
            row["revision"], "Verified modeled vision count", "test",
        )
    fulfillment.create_order(order([("A", 10)]))
    current = effective("A")
    assert (current["wms_qty"], current["erp_qty"], current["vision_qty"]) == (90, 90, 80)
    assert current["reserved_qty"] == 10
    with pytest.raises(Exception, match="revision"):
        with fulfillment.db_transaction() as db:
            fulfillment.correct_inventory(
                db, row["inventory_row_id"], {"wms_qty": 100}, "free",
                row["revision"], "Stale observation", "test",
            )
    assert effective("A")["wms_qty"] == 90


def test_maintenance_block_wins_over_release_and_preserves_reservation(v2db):
    maintenance = fulfillment.source_rows("maintenance")[0]
    maintenance.update(cmms_status="OPEN", safety_release_recorded="Y")
    created = fulfillment.create_order(order([("A", 10)]))
    fulfillment.run_executor_once(v2db["now"])
    detail = fulfillment.get_order(created["id"])
    assert detail["sub_orders"][0]["status"] == "reserved"
    assert detail["sub_orders"][0]["hold_reason"].startswith("WAITING_FOR_RESOURCE")
    assert (effective("A")["wms_qty"], effective("A")["reserved_qty"]) == (90, 10)
    maintenance.update(cmms_status="CLOSED", fleet_availability="UNAVAILABLE")
    with fulfillment._read_db() as db:
        robot = fulfillment.source_rows("robots")[0]
        assert not fulfillment.v2_robot_eligibility(db, robot, "W1", "pick", 10)[0]


@pytest.mark.parametrize("changes", [
    {"health_status": "DEGRADED"},
    {"safety_cert_status": ""},
    {"safety_cert_status": "EXPIRED"},
    {"connectivity": "OFFLINE"},
    {"payload_kg": "9"},
    {"battery_soc": "0"},
    {"battery_soc": "10"},
])
def test_source_readiness_and_capacity_blockers_are_enforced(v2db, changes):
    with fulfillment._read_db() as db:
        robot = {**fulfillment.source_rows("robots")[0], **changes}
        eligible, reasons = fulfillment.v2_robot_eligibility(db, robot, "W1", "pick", 10)
        assert not eligible
        assert reasons


@pytest.mark.parametrize("changes", [
    {"safety_cert_status": "UNKNOWN"},
    {"safety_cert_expires_at": "2029-12-31T00:00:00Z"},
    {"safety_cert_expires_at": "2031-01-01T00:00:00"},
    {"calibration_status": "EXPIRED"},
])
def test_informational_robot_fields_do_not_block_eligibility(v2db, changes):
    with fulfillment._read_db() as db:
        robot = {**fulfillment.source_rows("robots")[0], **changes}
        assert fulfillment.v2_robot_eligibility(db, robot, "W1", "pick", 10)[0]


def test_intermittent_connectivity_is_eligible_but_missing_maintenance_is_not(v2db):
    with fulfillment._read_db() as db:
        robot = {**fulfillment.source_rows("robots")[0], "connectivity": "INTERMITTENT"}
        assert fulfillment.v2_robot_eligibility(db, robot, "W1", "pick", 10)[0]
        fulfillment.source_rows("maintenance")[0]["cmms_status"] = ""
        assert not fulfillment.v2_robot_eligibility(db, robot, "W1", "pick", 10)[0]


def test_asset_requires_both_available_and_clear(v2db):
    candidates = fulfillment.source_rows("control_assets")
    good = next(
        asset for asset in candidates
        if fulfillment.v2_asset_eligibility(asset, "W1", "pack_feed")[0]
    )
    for field, value in (("state", "BLOCKED"), ("maintenance_state", "OPEN")):
        assert not fulfillment.v2_asset_eligibility(
            {**good, field: value}, "W1", "pack_feed",
        )[0]