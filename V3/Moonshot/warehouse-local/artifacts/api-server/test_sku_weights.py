"""V2 inventory-backed synthetic SKU weight regressions."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import fulfillment_api as fulfillment  # noqa: E402


@pytest.fixture
def weighted_db(tmp_path, monkeypatch):
    inventory = (
        {
            "warehouse_id": "W1", "sku": "A", "location": "W1-Z1-A",
            "wms_qty": "20", "erp_qty": "20", "vision_qty": "20",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "0.1",
        },
        {
            "warehouse_id": "W1", "sku": "B", "location": "W1-Z1-B",
            "wms_qty": "20", "erp_qty": "20", "vision_qty": "20",
            "reserved_qty": "0", "inventory_status": "AVAILABLE", "weight_kg": "0.2",
        },
    )
    fixtures = {
        "inventory": inventory,
        "skus": ({"sku": "A"}, {"sku": "B"}),
        "warehouses": ({"warehouse_id": "W1"},),
        "robots": (),
        "maintenance": (),
        "control_assets": (),
        "labor_capacity": (),
    }
    monkeypatch.setattr(fulfillment, "_raw_source_rows", lambda name: fixtures.get(name, ()))
    monkeypatch.setattr(fulfillment, "source_rows", lambda name: fixtures.get(name, ()))
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "weights.sqlite")
    monkeypatch.setattr(
        fulfillment, "utc_now", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    fulfillment._init_db()


def order(lines, request_id=None):
    return fulfillment.OrderInput(
        warehouse_id="W1",
        priority="standard",
        ship_by="2030-01-01T04:00:00Z",
        lines=[
            fulfillment.OrderLineInput(sku=sku, quantity=quantity)
            for sku, quantity in lines
        ],
        request_id=request_id or str(uuid.uuid4()),
    )


def test_v2_task_payloads_use_exact_location_sku_weights(weighted_db):
    created = fulfillment.create_order(order([("A", 3), ("B", 7)]))
    assert created["status"] == "active"
    by_sku = {sub["sku"]: sub for sub in created["sub_orders"]}
    assert by_sku["A"]["tasks"][0]["payload_kg"] == pytest.approx(0.3)
    assert by_sku["B"]["tasks"][0]["payload_kg"] == pytest.approx(1.4)
    with pytest.raises(Exception, match="Duplicate SKU A"):
        fulfillment.create_order(order([("A", 1), ("A", 2)]))


@pytest.mark.parametrize("weight", [None, 0, -1, float("nan"), float("inf")])
def test_invalid_current_inventory_weight_rolls_back_acceptance(weighted_db, weight):
    with fulfillment.db_transaction() as db:
        db.execute("UPDATE inventory_snapshot SET weight_kg=? WHERE sku='A'", (weight,))
        before = tuple(db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty FROM inventory_snapshot WHERE sku='A'"
        ).fetchone())
    with pytest.raises(Exception, match="weight_kg"):
        fulfillment.create_order(order([("A", 1)]))
    with fulfillment._read_db() as db:
        after = tuple(db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty FROM inventory_snapshot WHERE sku='A'"
        ).fetchone())
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    assert after == before


def test_inconsistent_current_location_weights_roll_back_atomically(weighted_db):
    with fulfillment.db_transaction() as db:
        original = db.execute("SELECT * FROM inventory_snapshot WHERE sku='A'").fetchone()
        db.execute(
            """INSERT INTO inventory_snapshot(
              source_row_index,warehouse_id,sku,location,zone,inventory_status,
              wms_qty,erp_qty,vision_qty,weight_kg,created_at,updated_at)
              VALUES (99,'W1','A','W1-Z2-A','W1-Z2','AVAILABLE',5,5,5,2,?,?)""",
            (original["created_at"], original["updated_at"]),
        )
    with pytest.raises(Exception, match="consistent positive"):
        fulfillment.create_order(order([("A", 1)]))
    with fulfillment._read_db() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_large_payload_waits_for_eligible_resource_without_manual_fallback(weighted_db):
    with fulfillment.db_transaction() as db:
        db.execute("UPDATE inventory_snapshot SET weight_kg=1000 WHERE sku='A'")
    created = fulfillment.create_order(order([("A", 1)]))
    assert created["status"] == "active"
    fulfillment.run_executor_once()
    current = fulfillment.get_order(created["id"])
    pick = next(task for task in current["tasks"] if task["stage"] == "pick")
    assert pick["status"] == "queued"
    assert pick["payload_kg"] == 1000
    assert "WAITING_FOR_RESOURCE" in pick["wait_reason"]


def test_idempotent_replay_keeps_saved_task_weight(weighted_db):
    request_id = str(uuid.uuid4())
    payload = order([("A", 2)], request_id)
    created = fulfillment.create_order(payload)
    with fulfillment.db_transaction() as db:
        db.execute("UPDATE inventory_snapshot SET weight_kg=3 WHERE sku='A'")
    replay = fulfillment.create_order(payload)
    assert replay["id"] == created["id"]
    assert replay["sub_orders"][0]["tasks"][0]["payload_kg"] == pytest.approx(0.2)