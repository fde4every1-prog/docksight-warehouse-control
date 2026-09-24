"""Policy-v2 core regressions. Every mutation uses an isolated temporary DB."""

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sys
import uuid

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))
import fulfillment_api as fulfillment  # noqa: E402
import fulfillment_v2  # noqa: E402
import demand_forecast  # noqa: E402
from test_persona_spec import ASGIClient  # noqa: E402


@pytest.fixture
def v2db(tmp_path, monkeypatch):
    clock = {"now": datetime(2030, 1, 1, tzinfo=timezone.utc)}
    inventory = (
        {
            "warehouse_id": "W1", "sku": "A", "location": "W1-Z1-B1",
            "wms_qty": "100", "erp_qty": "100", "vision_qty": "100",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "1",
        },
        {
            "warehouse_id": "W2", "sku": "B", "location": "W2-Z2-B1",
            "wms_qty": "8", "erp_qty": "8", "vision_qty": "8",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "2",
        },
        {
            "warehouse_id": "W1", "sku": "C", "location": "W1-Z3-B1",
            "wms_qty": "2", "erp_qty": "2", "vision_qty": "2",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "1",
        },
        {
            "warehouse_id": "W1", "sku": "MULTI", "location": "W1-Z4-B1",
            "wms_qty": "5", "erp_qty": "5", "vision_qty": "5",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "1",
        },
        {
            "warehouse_id": "W1", "sku": "MULTI", "location": "W1-Z5-B1",
            "wms_qty": "5", "erp_qty": "5", "vision_qty": "5",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "1",
        },
        {
            "warehouse_id": "W1", "sku": "BLOCK", "location": "W1-Z6-B1",
            "wms_qty": "5", "erp_qty": "5", "vision_qty": "5",
            "reserved_qty": "10", "inventory_status": "AVAILABLE", "weight_kg": "1",
        },
        {
            "warehouse_id": "W1", "sku": "LEGACY", "location": "W1-Z7-B1",
            "wms_qty": "5", "erp_qty": "5", "vision_qty": "5",
            "reserved_qty": "10", "inventory_status": "AVAILABLE", "weight_kg": "1",
        },
    )
    robots = (
        {
            "robot_id": "R1", "warehouse_id": "W1", "robot_type": "AMR",
            "battery_soc": "90", "health_status": "HEALTHY", "payload_kg": "500",
            "safety_cert_status": "VALID", "calibration_status": "VALID",
            "connectivity": "INTERMITTENT",
        },
        {
            "robot_id": "R2", "warehouse_id": "W2", "robot_type": "AMR",
            "battery_soc": "90", "health_status": "HEALTHY", "payload_kg": "500",
            "safety_cert_status": "VALID", "calibration_status": "VALID",
            "connectivity": "ONLINE",
        },
    )
    maintenance = tuple(
        {
            "robot_id": robot["robot_id"], "warehouse_id": robot["warehouse_id"],
            "cmms_status": "CLOSED", "fleet_availability": "AVAILABLE",
        }
        for robot in robots
    )
    assets = tuple(
        {
            "asset_id": f"{warehouse}-{kind}", "warehouse_id": warehouse,
            "asset_type": kind, "state": "AVAILABLE", "maintenance_state": "CLEAR",
        }
        for warehouse in ("W1", "W2")
        for kind in ("CONVEYOR", "DOCK_DOOR", "PACK_STATION")
    )
    fixtures = {
        "inventory": inventory,
        "skus": tuple(
            {"sku": sku} for sku in ("A", "B", "C", "MULTI", "BLOCK", "LEGACY")
        ),
        "warehouses": ({"warehouse_id": "W1"}, {"warehouse_id": "W2"}),
        "robots": robots,
        "maintenance": maintenance,
        "control_assets": assets,
        "labor_capacity": (),
    }

    def rows(dataset):
        return fixtures.get(dataset, ())

    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "v2.sqlite")
    monkeypatch.setattr(fulfillment, "utc_now", lambda: clock["now"])
    monkeypatch.setattr(fulfillment, "_raw_source_rows", rows)
    monkeypatch.setattr(fulfillment, "source_rows", rows)
    fulfillment._init_db()
    return clock


def order(
    lines, request_id=None, service="Same_Day", warehouse_id="W1",
    order_source="fde_bazaar",
):
    return fulfillment.OrderInput(
        warehouse_id=warehouse_id,
        priority="high",
        lines=[fulfillment.OrderLineInput(sku=sku, quantity=quantity) for sku, quantity in lines],
        request_id=request_id or str(uuid.uuid4()),
        source_order_id=f"FBZ-{uuid.uuid4()}",
        order_service=service,
        order_source=order_source,
        order_created_at="2030-01-01T00:00:00Z",
    )


def effective(sku):
    with fulfillment._read_db() as db:
        return fulfillment.inventory_rows(db, sku=sku)[0]


def test_light_order_page_and_rejected_detail(v2db):
    first = fulfillment.create_order(order([("A", 1)]))
    second = fulfillment.create_order(order([("C", 8)], order_source="core"))
    with fulfillment.db_transaction() as db:
        db.execute("UPDATE orders SET status='rejected',created_at='2030-01-02T00:00:00Z' WHERE id=?", (second["id"],))
        db.execute("UPDATE sub_orders SET status='rejected',hold_reason='INVENTORY_SHORTAGE: C' WHERE order_id=?", (second["id"],))
    page = fulfillment.list_orders(limit=1)
    assert page["total"] == 2
    assert page["items"][0]["id"] == second["id"]
    assert page["items"][0]["fulfillment_status"] == "Rejected"
    assert page["items"][0]["hold_reason"] == "INVENTORY_SHORTAGE: C"
    assert "fulfillment_history" not in page["items"][0]
    assert "tasks" not in page["items"][0]["sub_orders"][0]
    assert fulfillment.list_orders(limit=1, offset=1)["items"][0]["id"] == first["id"]
    assert fulfillment.list_orders(search=second["source_order_id"])["total"] == 1
    assert fulfillment.list_orders(status="rejected")["total"] == 1
    assert fulfillment.list_orders(warehouse="W2")["total"] == 0
    state = fulfillment.state(limit=1)
    assert state["summary"]["rejected"] == 1
    assert state["total_orders"] == 2
    assert state["has_more"]
    detail = fulfillment.get_order(second["id"])
    assert detail["fulfillment_status"] == "Rejected"
    assert detail["sub_orders"][0]["hold_reason"] == "INVENTORY_SHORTAGE: C"


def test_order_detail_omits_ledger_without_removing_accounting(v2db, monkeypatch):
    created = fulfillment.create_order(order([("A", 2)], warehouse_id="W1"))
    queries = []
    read_db = fulfillment._read_db

    @contextmanager
    def traced_read_db():
        with read_db() as db:
            db.set_trace_callback(queries.append)
            yield db

    monkeypatch.setattr(fulfillment, "_read_db", traced_read_db)
    detail = fulfillment.get_order(created["id"])
    assert "inventory_movements" not in detail
    assert detail["id"] == created["id"]
    assert detail["sub_orders"][0]["allocations"]
    assert detail["tasks"]
    assert "events" in detail
    assert not any("inventory_movements" in query.lower() for query in queries)
    with fulfillment._read_db() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM inventory_movements WHERE order_id=?",
            (created["id"],),
        ).fetchone()[0] > 0


def test_free_stock_is_not_double_subtracted_and_replay_is_atomic(v2db):
    request_id = str(uuid.uuid4())
    first = fulfillment.create_order(order([("A", 60)], request_id))
    row = effective("A")
    assert (row["wms_qty"], row["reserved_qty"], row["allocatable_qty"]) == (40, 60, 40)
    assert fulfillment.create_order(order([("A", 30)]))["status"] == "active"
    row = effective("A")
    assert (row["wms_qty"], row["erp_qty"], row["vision_qty"]) == (10, 10, 10)
    assert row["reserved_qty"] == 90
    replay_payload = order([("A", 60)], request_id)
    replay_payload.source_order_id = first["source_order_id"]
    assert fulfillment.create_order(replay_payload)["id"] == first["id"]
    with pytest.raises(Exception, match="different payload"):
        fulfillment.create_order(order([("A", 59)], request_id))


def test_explicit_warehouse_draft_uses_v2_and_honors_constraint(v2db):
    payload = fulfillment.OrderInput(
        warehouse_id="W1",
        priority="high",
        ship_by="2030-01-01T12:00:00Z",
        lines=[fulfillment.OrderLineInput(sku="A", quantity=3)],
        request_id=str(uuid.uuid4()),
    )
    created = fulfillment.create_order(payload)
    assert created["policy_version"] == 2
    assert created["warehouse_id"] == "W1"
    assert created["order_service"] == "Standard"
    assert created["sub_orders"][0]["warehouse_id"] == "W1"

    wrong_warehouse = payload.copy(
        update={
            "warehouse_id": "W2",
            "request_id": str(uuid.uuid4()),
        }
    )
    held = fulfillment.create_order(wrong_warehouse)
    assert held["status"] == "held"
    assert held["sub_orders"][0]["warehouse_id"] is None

    # W1 has stock, but neither retry nor an unrelated warehouse correction
    # may bypass the W2 constraint preserved on the parent order.
    retried = fulfillment.command_order(held["id"], "retry")
    assert retried["status"] == "held"
    assert retried["sub_orders"][0]["warehouse_id"] is None
    assert retried["sub_orders"][0]["allocations"] == []

    current = effective("A")
    with fulfillment.db_transaction() as db:
        fulfillment.correct_inventory(
            db, current["inventory_row_id"],
            {"wms_qty": 110, "erp_qty": 110, "vision_qty": 110},
            "free", current["revision"], "Verified stock in W1", "test",
        )
    after_correction = fulfillment.get_order(held["id"])
    assert after_correction["status"] == "held"
    assert after_correction["sub_orders"][0]["warehouse_id"] is None
    assert after_correction["sub_orders"][0]["allocations"] == []
    assert after_correction["tasks"] == []
    assert effective("A")["reserved_qty"] == 3
    assert effective("A")["wms_qty"] == 110


def test_bazaar_requires_known_warehouse_and_shortage_rolls_back_every_line(v2db):
    unknown = order([("A", 1)], warehouse_id="NO-SUCH-WAREHOUSE")
    with pytest.raises(Exception, match="Unknown warehouse_id"):
        fulfillment.create_order(unknown)

    # B has enough stock in W2, but the selected W1 must neither fall back nor
    # leave A's otherwise feasible line partially persisted or reserved.
    request = order([("A", 4), ("B", 4)], warehouse_id="W1")
    with pytest.raises(fulfillment.HTTPException) as shortage:
        fulfillment.create_order(request)
    assert shortage.value.status_code == 422
    assert shortage.value.detail == {
        "code": "INVENTORY_SHORTAGE",
        "warehouse_id": "W1",
        "sku": "B",
        "requested": 4,
        "available": 0,
        "message": "Warehouse W1 cannot allocate SKU B: requested 4, available 0",
    }
    with fulfillment._read_db() as db:
        for table in (
            "orders", "order_lines", "sub_orders", "sub_order_allocations",
            "tasks", "events", "inventory_movements",
        ):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        a = fulfillment.inventory_rows(db, "W1", "A")[0]
        b = fulfillment.inventory_rows(db, "W2", "B")[0]
        assert (a["wms_qty"], a["reserved_qty"]) == (100, 0)
        assert (b["wms_qty"], b["reserved_qty"]) == (8, 0)


def test_historical_bazaar_message_without_warehouse_keeps_automatic_path(v2db):
    request_id = str(uuid.uuid4())
    historical = fulfillment.create_order(
        order(
            [("B", 4)], request_id=request_id, warehouse_id=None,
            order_source="fde_bazaar",
        )
    )
    assert historical["status"] == "active"
    assert historical["warehouse_id"] is None
    assert historical["sub_orders"][0]["warehouse_id"] == "W2"

    # Its immutable identity remains the original missing-warehouse payload.
    replay = order(
        [("B", 4)],
        request_id=request_id,
        warehouse_id=None,
        order_source="fde_bazaar",
    )
    replay.source_order_id = historical["source_order_id"]
    assert fulfillment.create_order(replay)["id"] == historical["id"]


def test_bazaar_selected_warehouse_combines_locations_and_replay_skips_stock_gate(v2db):
    request_id = str(uuid.uuid4())
    first = fulfillment.create_order(
        order([("MULTI", 10)], request_id=request_id, warehouse_id="W1")
    )
    allocations = first["sub_orders"][0]["allocations"]
    assert {item["zone"] for item in allocations} == {"W1-Z4", "W1-Z5"}
    assert sum(item["quantity"] for item in allocations) == 10

    replay = order([("MULTI", 10)], request_id=request_id, warehouse_id="W1")
    replay.source_order_id = first["source_order_id"]
    same = fulfillment.create_order(replay)
    assert same["id"] == first["id"]
    with fulfillment._read_db() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM inventory_movements WHERE order_id=?",
            (first["id"],),
        ).fetchone()[0] == 2


def test_concurrent_bazaar_orders_cannot_oversell_selected_warehouse(v2db):
    requests = [
        order([("A", 60)], warehouse_id="W1"),
        order([("A", 60)], warehouse_id="W1"),
    ]

    def submit(payload):
        try:
            return fulfillment.create_order(payload)
        except fulfillment.HTTPException as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, requests))
    accepted = [result for result in results if isinstance(result, dict)]
    rejected = [result for result in results if isinstance(result, fulfillment.HTTPException)]
    assert len(accepted) == len(rejected) == 1
    assert rejected[0].status_code == 422
    assert rejected[0].detail["requested"] == 60
    assert rejected[0].detail["available"] == 40
    with fulfillment._read_db() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        row = fulfillment.inventory_rows(db, "W1", "A")[0]
        assert (row["wms_qty"], row["reserved_qty"]) == (40, 60)


def test_retired_request_tombstone_prevents_stale_recreation(v2db):
    request_id = str(uuid.uuid4())
    digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    with fulfillment.db_transaction() as db:
        db.execute(
            "INSERT INTO retired_order_requests(request_digest) VALUES (?)",
            (digest,),
        )
    with pytest.raises(Exception, match="retired by the operational reset"):
        fulfillment.create_order(order([("A", 1)], request_id))
    with fulfillment._read_db() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_operational_availability_is_location_min_without_reservation_overlay(v2db):
    # One accepted unit on Jan 1 is canonical demand for a Jan 2 forecast:
    # one global history day => forecast_7d=7.
    fulfillment.create_order(order([("A", 1)]))
    row = effective("A")
    with fulfillment.db_transaction() as db:
        db.execute(
            """UPDATE inventory_snapshot
               SET wms_qty=100,erp_qty=7,vision_qty=9,reserved_qty=40
               WHERE id=?""",
            (row["inventory_row_id"],),
        )
        demand_forecast.generate(
            db,
            datetime(2030, 1, 2, tzinfo=timezone.utc).date(),
            datetime(2030, 1, 2, tzinfo=timezone.utc),
        )
        atp = fulfillment.available_to_promise(db, "W1", "A")
        alerts = fulfillment.stock_alerts(db)
    assert atp["available_to_promise"] == 7
    # Equality is not low stock, and reserved_qty is not deducted again.
    assert all(item["sku"] != "A" for item in alerts)

    with fulfillment.db_transaction() as db:
        db.execute(
            "UPDATE inventory_snapshot SET erp_qty=6 WHERE id=?",
            (row["inventory_row_id"],),
        )
        alerts = fulfillment.stock_alerts(db)
    assert next(item for item in alerts if item["sku"] == "A") == {
        "warehouse_id": "W1",
        "sku": "A",
        "available": 6,
        "threshold": 7,
        "forecast_7d": 7,
        "forecast_30d": 30,
        "forecast_date": "2030-01-02",
        "history_days": 1,
        "history_status": "short_history",
        "inventory_policy": "free_source_min_sum",
        "forecast_method": demand_forecast.METHOD,
    }


def test_per_sku_warehouses_partial_hold_and_fifo_correction(v2db):
    mixed = fulfillment.create_order(
        order(
            [("A", 4), ("B", 4), ("C", 5)],
            warehouse_id=None,
            order_source="legacy_automatic",
        )
    )
    assert mixed["status"] == "partially_fulfilled"
    by_sku = {item["sku"]: item for item in mixed["sub_orders"]}
    assert by_sku["A"]["warehouse_id"] == "W1"
    assert by_sku["B"]["warehouse_id"] == "W2"
    assert by_sku["C"]["status"] == "held"
    row = effective("C")
    with fulfillment.db_transaction() as db:
        corrected = fulfillment.correct_inventory(
            db, row["inventory_row_id"],
            {"wms_qty": 10, "erp_qty": 10, "vision_qty": 10},
            "free", row["revision"], "Replenished and verified", "test",
        )
    assert corrected["reserved_qty"] == 5
    recovered = fulfillment.get_order(mixed["id"])
    assert {item["status"] for item in recovered["sub_orders"]} <= {"queued", "running"}


def test_pick_exactly_once_and_cancellation_boundaries(v2db):
    clock = v2db
    before_pick = fulfillment.create_order(order([("A", 10)]))
    fulfillment.command_order(before_pick["id"], "cancel")
    assert effective("A")["wms_qty"] == 100

    picked = fulfillment.create_order(order([("A", 10)]))
    assert fulfillment.run_executor_once(clock["now"]) == 0
    assert effective("A")["reserved_qty"] == 10
    clock["now"] += timedelta(seconds=45)
    assert fulfillment.run_executor_once(clock["now"]) == 1
    assert fulfillment.run_executor_once(clock["now"]) == 0
    row = effective("A")
    assert (row["wms_qty"], row["reserved_qty"], row["picked_qty"]) == (90, 0, 10)
    cancelled = fulfillment.command_order(picked["id"], "cancel")
    assert cancelled["status"] == "recovery_required"
    row = effective("A")
    assert (row["wms_qty"], row["picked_qty"]) == (90, 10)


def test_cutoffs_and_shared_source_readiness(v2db):
    assert fulfillment.create_order(order([("A", 1)], service="Same_Day"))["cutoff_at"].endswith("06:00:00Z")
    assert fulfillment.create_order(
        order([("B", 1)], service="Next_Day", warehouse_id="W2")
    )["cutoff_at"].endswith("12:00:00Z")
    with fulfillment._read_db() as db:
        robot = fulfillment.source_rows("robots")[0]
        assert fulfillment.v2_robot_eligibility(db, robot, "W1", "pick", 1)[0]
        formerly_strict = {
            **robot,
            "battery_soc": "0",
            "calibration_status": "INVALID",
            "safety_cert_status": "UNKNOWN",
            "safety_cert_expires_at": "2000-01-01T00:00:00Z",
        }
        assert fulfillment.v2_robot_eligibility(
            db, formerly_strict, "W1", "pick", 1
        )[0]
        expired = {**robot, "safety_cert_status": "EXPIRED"}
        ok, reasons = fulfillment.v2_robot_eligibility(db, expired, "W1", "pick", 1)
        assert not ok and any("EXPIRED" in reason for reason in reasons)
        unknown = {**robot, "robot_id": "NO-EVIDENCE"}
        ok, reasons = fulfillment.v2_robot_eligibility(db, unknown, "W1", "pick", 1)
        assert not ok and any("unknown" in reason for reason in reasons)


def test_every_maintenance_row_must_be_ready(v2db):
    with fulfillment._read_db() as db:
        robot = fulfillment.source_rows("robots")[0]
        rows = (
            {
                "robot_id": "R1", "work_order_id": "OK",
                "cmms_status": "CLOSED", "fleet_availability": "AVAILABLE",
            },
            {
                "robot_id": "R1", "work_order_id": "BAD",
                "cmms_status": "", "fleet_availability": "UNAVAILABLE",
            },
        )
        ok, reasons = fulfillment_v2.robot_eligibility(
            db, robot, "W1", "pick", 1, set(), rows, v2db["now"]
        )
        assert not ok
        assert any("BAD" in reason and "unknown" in reason for reason in reasons)
        assert any("BAD" in reason and "not AVAILABLE" in reason for reason in reasons)


def test_asset_resource_block_is_independent_of_source_readiness(v2db):
    asset = fulfillment.source_rows("control_assets")[0]
    with fulfillment.db_transaction() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS persona_resource_blocks(
                 resource_id TEXT PRIMARY KEY, warehouse_id TEXT, reason TEXT,
                 intervention_id TEXT, created_at TEXT)"""
        )
        db.execute(
            "INSERT INTO persona_resource_blocks VALUES (?,?,?,?,?)",
            (asset["asset_id"], "W1", "independent hold", "I-1", "2030-01-01T00:00:00Z"),
        )
        assert fulfillment_v2.asset_readiness(asset)[0]
        ok, reasons = fulfillment.v2_asset_eligibility(
            asset, "W1", "pack_feed", db=db
        )
        assert not ok
        assert "Explicit resource block is active" in reasons


def test_resource_becoming_unsafe_pauses_due_pick_and_retains_stock(v2db):
    clock = v2db
    created = fulfillment.create_order(order([("A", 3)]))
    fulfillment.run_executor_once(clock["now"])
    robot = fulfillment.source_rows("robots")[0]
    robot["health_status"] = "DEGRADED"
    clock["now"] += timedelta(seconds=45)
    assert fulfillment.run_executor_once(clock["now"]) == 0
    row = effective("A")
    assert (row["wms_qty"], row["reserved_qty"], row["picked_qty"]) == (97, 3, 0)
    detail = fulfillment.get_order(created["id"])
    pick = next(task for task in detail["tasks"] if task["stage"] == "pick")
    assert pick["status"] == "paused"
    assert "became ineligible" in pick["wait_reason"]
    robot["health_status"] = "HEALTHY"
    # Repairs restore fitness immediately; new claims wait for the minute tick.
    clock["now"] += timedelta(seconds=15)
    fulfillment.run_executor_once(clock["now"])
    recovered = fulfillment.get_order(created["id"])
    pick = next(task for task in recovered["tasks"] if task["stage"] == "pick")
    assert pick["status"] == "running"


def test_schema_helper_preserves_transaction_and_allocation_failure_rolls_back(
    v2db, monkeypatch
):
    with fulfillment.db_transaction() as db:
        assert db.in_transaction
        fulfillment.ensure_inventory(db)
        assert db.in_transaction

    original_movement = fulfillment_v2._movement

    def fail_acceptance(*args, **kwargs):
        if kwargs.get("kind") == "accept_reserve":
            raise RuntimeError("injected movement failure")
        return original_movement(*args, **kwargs)

    monkeypatch.setattr(fulfillment_v2, "_movement", fail_acceptance)
    with pytest.raises(RuntimeError, match="injected movement failure"):
        fulfillment.create_order(order([("A", 4)]))
    with fulfillment._read_db() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM sub_orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM sub_order_allocations").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0
        row = fulfillment.inventory_rows(db, sku="A")[0]
        assert (row["wms_qty"], row["erp_qty"], row["vision_qty"]) == (100, 100, 100)
        assert row["reserved_qty"] == 0


def test_partial_location_pick_then_cancel_restores_only_unpicked(v2db):
    clock = v2db
    created = fulfillment.create_order(order([("MULTI", 10)]))
    picks = [task for task in created["sub_orders"][0]["tasks"] if task["stage"] == "pick"]
    assert len(picks) == 2
    assert all(task["allocation_id"] for task in picks)
    fulfillment.run_executor_once(clock["now"])
    clock["now"] += timedelta(seconds=45)
    assert fulfillment.run_executor_once(clock["now"]) == 1
    detail = fulfillment.get_order(created["id"])
    picks = [task for task in detail["tasks"] if task["stage"] == "pick"]
    assert sorted(task["status"] for task in picks) == ["completed", "queued"]
    assert next(task for task in detail["tasks"] if task["stage"] == "move")["status"] == "pending"
    cancelled = fulfillment.command_order(created["id"], "cancel")
    assert cancelled["status"] == "recovery_required"
    with fulfillment._read_db() as db:
        rows = fulfillment.inventory_rows(db, sku="MULTI")
        assert sum(row["wms_qty"] for row in rows) == 5
        assert sum(row["reserved_qty"] for row in rows) == 0
        assert sum(row["picked_qty"] for row in rows) == 5
        assert sum(row["completed_qty"] for row in rows) == 0


def test_verified_opening_external_reservation_clear_recovers_held_once(v2db):
    held = fulfillment.create_order(
        order([("BLOCK", 5)], order_source="control_tower")
    )
    assert held["status"] == "held"
    row = effective("BLOCK")
    assert row["blocked_allocation"] == 1
    assert row["reserved_qty"] == 10

    with fulfillment.db_transaction() as db:
        corrected = fulfillment_v2.correct_inventory(
            db,
            row["inventory_row_id"],
            {"wms_qty": 20, "erp_qty": 20, "vision_qty": 20},
            "total_on_hand",
            row["revision"],
            "All three source totals physically observed",
            "test-supervisor",
            v2db["now"],
        )
        assert corrected["blocked_allocation"] == 1
        assert corrected["allocatable_qty"] == 0
        evidence = {
            "revision": corrected["revision"],
            "basis": "total_on_hand",
            "wms_qty": 20,
            "erp_qty": 20,
            "vision_qty": 20,
            "attestation": "WMS, ERP, and vision totals jointly verified",
        }
        verified = fulfillment_v2.verify_opening_inventory(
            db,
            row["inventory_row_id"],
            "Opening external reservation reconciled",
            "test-supervisor",
            evidence,
        )
        assert verified["blocked_allocation"] == 0
        assert verified["opening_discrepancy"] is None
        # External 10 is protected; recovery reserves 5 and leaves free 5.
        assert verified["reserved_qty"] == 15
        assert verified["wms_qty"] == 5
        movement_count = db.execute(
            "SELECT COUNT(*) FROM inventory_movements WHERE order_id=?",
            (held["id"],),
        ).fetchone()[0]
        correction_count = db.execute(
            """SELECT COUNT(*) FROM inventory_corrections
               WHERE inventory_row_id=? AND basis='opening_verification'""",
            (row["inventory_row_id"],),
        ).fetchone()[0]
        duplicate = fulfillment_v2.verify_opening_inventory(
            db,
            row["inventory_row_id"],
            "Opening external reservation reconciled",
            "test-supervisor",
            evidence,
        )
        assert duplicate["reserved_qty"] == 15
        assert db.execute(
            "SELECT COUNT(*) FROM inventory_movements WHERE order_id=?",
            (held["id"],),
        ).fetchone()[0] == movement_count
        assert db.execute(
            """SELECT COUNT(*) FROM inventory_corrections
               WHERE inventory_row_id=? AND basis='opening_verification'""",
            (row["inventory_row_id"],),
        ).fetchone()[0] == correction_count == 1
    assert fulfillment.get_order(held["id"])["status"] == "active"


def test_opening_verification_never_clears_legacy_unmapped_anomaly(v2db):
    row = effective("LEGACY")
    with fulfillment.db_transaction() as db:
        db.execute(
            """UPDATE inventory_snapshot SET
               opening_discrepancy=opening_discrepancy ||
                 '; Legacy reservation OLD-1 has 5 units not reconcilable',
               revision=revision+1 WHERE id=?""",
            (row["inventory_row_id"],),
        )
        current = db.execute(
            "SELECT * FROM inventory_snapshot WHERE id=?", (row["inventory_row_id"],)
        ).fetchone()
        protected = current["reserved_qty"] + current["picked_qty"]
        evidence = {
            "revision": current["revision"],
            "basis": "total_on_hand",
            "wms_qty": current["wms_qty"] + protected,
            "erp_qty": current["erp_qty"] + protected,
            "vision_qty": current["vision_qty"] + protected,
            "attestation": "All observations checked, legacy anomaly still unresolved",
        }
        with pytest.raises(Exception, match="explicit reconciliation"):
            fulfillment_v2.verify_opening_inventory(
                db,
                row["inventory_row_id"],
                "Attempted verification",
                "test-supervisor",
                evidence,
            )
        still = db.execute(
            "SELECT blocked_allocation,opening_discrepancy FROM inventory_snapshot WHERE id=?",
            (row["inventory_row_id"],),
        ).fetchone()
        assert still["blocked_allocation"] == 1
        assert "Legacy reservation" in still["opening_discrepancy"]


def test_task_duration_default_migration_validation_and_persistence(v2db):
    with fulfillment.db_transaction() as db:
        assert fulfillment.config_values(db)["task_duration_seconds"] == 45
        db.execute("DELETE FROM config WHERE key='task_duration_seconds'")

    fulfillment._init_db()
    with fulfillment._read_db() as db:
        assert fulfillment_v2.task_duration_seconds(db) == 45

    for invalid in (0, 86_401, 1.5, True, False):
        with pytest.raises(ValidationError):
            fulfillment.ConfigInput(task_duration_seconds=invalid)

    assert fulfillment.ConfigInput(task_duration_seconds=1).task_duration_seconds == 1
    maximum = fulfillment.ConfigInput(task_duration_seconds=86_400)
    fulfillment.put_config(maximum, "admin")
    fulfillment._init_db()
    with fulfillment._read_db() as db:
        assert fulfillment.config_values(db)["task_duration_seconds"] == 86_400


def test_config_endpoint_is_admin_only_and_catalog_is_current(v2db):
    app = FastAPI()
    app.include_router(fulfillment.router)
    client = ASGIClient(app)

    for persona in (None, "fleet", "supervisor"):
        headers = {} if persona is None else {"X-Demo-Persona": persona}
        response = client._request(
            "PUT",
            "/api/fulfillment/config",
            headers=headers,
            json_body={"task_duration_seconds": 9},
        )
        assert response.status_code == 403

    response = client._request(
        "PUT",
        "/api/fulfillment/config",
        headers={"X-Demo-Persona": "admin"},
        json_body={"task_duration_seconds": 9},
    )
    assert response.status_code == 200
    assert response.json()["task_duration_seconds"] == 9
    assert fulfillment.catalog()["fulfillment_policies"]["stage_duration_seconds"] == 9


def test_duration_is_captured_at_creation_and_each_assignment(v2db):
    clock = v2db
    fulfillment.put_config(fulfillment.ConfigInput(task_duration_seconds=12), "admin")
    created = fulfillment.create_order(order([("A", 1)]))

    with fulfillment._read_db() as db:
        assert {
            row["duration_seconds"]
            for row in db.execute(
                "SELECT duration_seconds FROM tasks WHERE order_id=?", (created["id"],)
            )
        } == {12}

    fulfillment.run_executor_once(clock["now"])
    with fulfillment._read_db() as db:
        running = db.execute(
            "SELECT * FROM tasks WHERE order_id=? AND status='running'",
            (created["id"],),
        ).fetchone()
        original_due = running["due_at"]
        assert (
            fulfillment.parse_utc(running["due_at"])
            - fulfillment.parse_utc(running["started_at"])
        ).total_seconds() == 12

    fulfillment.put_config(fulfillment.ConfigInput(task_duration_seconds=30), "admin")
    with fulfillment._read_db() as db:
        unchanged = db.execute(
            "SELECT duration_seconds,due_at FROM tasks WHERE id=?", (running["id"],)
        ).fetchone()
        assert tuple(unchanged) == (12, original_due)

    clock["now"] += timedelta(seconds=12)
    fulfillment.run_executor_once(clock["now"])
    fulfillment.command_order(created["id"], "retry")
    with fulfillment._read_db() as db:
        next_running = db.execute(
            "SELECT * FROM tasks WHERE order_id=? AND status='running'",
            (created["id"],),
        ).fetchone()
        assert next_running["duration_seconds"] == 30
        assert (
            fulfillment.parse_utc(next_running["due_at"])
            - fulfillment.parse_utc(next_running["started_at"])
        ).total_seconds() == 30


def test_prompt_replacement_uses_latest_configured_duration(v2db):
    clock = v2db
    created = fulfillment.create_order(order([("A", 1)]))
    task_id = created["sub_orders"][0]["tasks"][0]["id"]
    fulfillment.put_config(fulfillment.ConfigInput(task_duration_seconds=7), "admin")

    with fulfillment.db_transaction() as db:
        resource = fulfillment_v2.replace_queued_task(
            db,
            task_id,
            clock["now"],
            fulfillment.source_rows,
            fulfillment._append_event,
        )
        assert resource
        task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        assert task["duration_seconds"] == 7
        assert (
            fulfillment.parse_utc(task["due_at"])
            - fulfillment.parse_utc(task["started_at"])
        ).total_seconds() == 7