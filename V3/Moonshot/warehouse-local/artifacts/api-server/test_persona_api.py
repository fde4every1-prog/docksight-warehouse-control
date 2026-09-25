"""Isolated persona regressions against V2 fulfillment work."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent))
import fulfillment_api as fulfillment  # noqa: E402
import persona_api as persona  # noqa: E402


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    original = fulfillment._raw_source_rows

    def rows(dataset):
        source = original(dataset)
        if dataset == "inventory":
            return tuple({**row, "weight_kg": "1"} for row in source)
        return source

    rows.cache_clear = original.cache_clear
    monkeypatch.setattr(fulfillment, "_raw_source_rows", rows)
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "fulfillment.sqlite")
    clock = {"now": datetime(2030, 1, 1, tzinfo=timezone.utc)}
    monkeypatch.setattr(fulfillment, "utc_now", lambda: clock["now"])
    fulfillment._init_db()
    persona._ensure_schema()
    return clock


def make_order(clock, quantity=1):
    return fulfillment.create_order(
        fulfillment.OrderInput(
            warehouse_id="DC-01",
            priority="standard",
            ship_by=(clock["now"] + timedelta(hours=4)).isoformat().replace("+00:00", "Z"),
            lines=[fulfillment.OrderLineInput(sku="SKU-01146", quantity=quantity)],
            request_id=str(uuid.uuid4()),
        )
    )


def intervention(kind, warehouse, entity, role="fleet"):
    return persona.create_intervention(
        persona.InterventionCreate(
            kind=kind,
            warehouse_id=warehouse,
            entity_id=entity,
            description="Isolated V2 persona regression",
        ),
        role,
    )


def internal_intervention(kind, warehouse, entity, owner="fleet"):
    """Create internal recovery history without exercising the retired public report path."""
    now = fulfillment.iso(fulfillment.utc_now())
    intervention_id = f"INT-{uuid.uuid4()}"
    with persona._tx() as db:
        db.execute(
            "INSERT INTO persona_interventions "
            "(id,dedupe_key,kind,warehouse_id,entity_id,title,description,owner,status,"
            "evidence_json,proposed_action_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                intervention_id,
                None,
                kind,
                warehouse,
                entity,
                f"{kind.replace('_', ' ').title()}: {entity}",
                "Internal isolated recovery fixture",
                owner,
                "open",
                "{}",
                None,
                now,
                now,
            ),
        )
        row = persona._fetch(db, intervention_id)
        persona._add_event(
            db, row, "system", "detected", "Internal recovery fixture created", {}
        )
        return persona._intervention_json(db, persona._fetch(db, intervention_id), owner)


@pytest.mark.parametrize(
    "kind", ["fleet_readiness", "control_asset_readiness", "resource_failure"]
)
def test_fleet_manual_reports_are_rejected(isolated_db, kind):
    with pytest.raises(HTTPException) as caught:
        intervention(kind, "DC-01", "MANUAL-FLEET-REPORT")
    assert caught.value.status_code == 403
    assert "manual reports are retired" in caught.value.detail
    with fulfillment._read_db() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM persona_interventions WHERE entity_id=?",
            ("MANUAL-FLEET-REPORT",),
        ).fetchone()[0] == 0


def test_retired_fleet_reports_workspace_section_is_invalid(isolated_db):
    with pytest.raises(HTTPException) as caught:
        persona._workspace("fleet", section="fleet_reports")
    assert caught.value.status_code == 422
    assert caught.value.detail == "The fleet_reports workspace section is retired"


def test_supervisor_manual_resource_failure_reporting_remains_available(isolated_db):
    item = intervention(
        "resource_failure", "DC-01", "SUPERVISOR-REPORTED-FAILURE", "supervisor"
    )
    assert item["kind"] == "resource_failure"
    assert item["owner"] == "supervisor"
    assert item["status"] == "open"


def action(item, name, role, *, value=None, evidence=None, assigned_to=None):
    return persona.intervention_action(
        item["id"],
        persona.InterventionAction(
            action=name,
            reason=f"V2 regression {name}",
            value=value,
            evidence=evidence,
            assigned_to=assigned_to,
        ),
        role,
    )


def approve_robot_hold(robot):
    item = internal_intervention(
        "fleet_readiness", robot["warehouse_id"], robot["robot_id"]
    )
    action(item, "investigate", "fleet")
    action(
        item,
        "propose",
        "fleet",
        value="hold",
        evidence={"finding": "unsafe during simulation", "source": "test"},
    )
    action(item, "handoff", "fleet")
    action(item, "approve", "supervisor")
    return item


def test_historic_scalar_overlay_is_readable_but_not_operational(isolated_db):
    clock = isolated_db
    order = make_order(clock)
    sub = order["sub_orders"][0]
    with fulfillment._read_db() as db:
        before = fulfillment.available_to_promise(db, "DC-01", "SKU-01146")
    item = intervention("inventory_mismatch", "DC-01", "SKU-01146@historic", "supervisor")
    with fulfillment.db_transaction() as db:
        db.execute(
            "INSERT INTO persona_inventory_overlays"
            "(warehouse_id,sku,physical_qty,intervention_id,created_at) VALUES (?,?,?,?,?)",
            ("DC-01", "SKU-01146", 0, item["id"], fulfillment.iso(clock["now"])),
        )
    with fulfillment._read_db() as db:
        after = fulfillment.available_to_promise(db, "DC-01", "SKU-01146")
        assert db.execute(
            "SELECT physical_qty FROM persona_inventory_overlays WHERE intervention_id=?",
            (item["id"],),
        ).fetchone()[0] == 0
    assert sub["warehouse_id"] == "DC-01"
    assert after == before


def test_v2_safety_hold_pauses_running_pick_without_second_stock_debit(isolated_db):
    clock = isolated_db
    order = make_order(clock, quantity=2)
    with fulfillment._read_db() as db:
        inventory_id = db.execute(
            "SELECT inventory_row_id FROM sub_order_allocations "
            "WHERE sub_order_id IN (SELECT id FROM sub_orders WHERE order_id=?)",
            (order["id"],),
        ).fetchone()[0]
        accepted = tuple(db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
            "FROM inventory_snapshot WHERE id=?", (inventory_id,)
        ).fetchone())
    fulfillment.run_executor_once(clock["now"])
    with fulfillment._read_db() as db:
        running = db.execute(
            "SELECT * FROM tasks WHERE order_id=? AND stage='pick' AND status='running'",
            (order["id"],),
        ).fetchone()
    robot = next(
        row for row in fulfillment.source_rows("robots")
        if row["robot_id"] == running["resource_id"]
    )
    approve_robot_hold(robot)
    clock["now"] += timedelta(seconds=45)
    assert fulfillment.run_executor_once(clock["now"]) == 0
    with fulfillment._read_db() as db:
        assert db.execute(
            "SELECT status FROM tasks WHERE id=?", (running["id"],)
        ).fetchone()[0] == "paused"
        held_state = tuple(db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
            "FROM inventory_snapshot WHERE id=?", (inventory_id,)
        ).fetchone())
    assert held_state == accepted


def test_v2_hold_release_recovers_and_pick_debits_sources_only_at_acceptance(isolated_db):
    clock = isolated_db
    order = make_order(clock, quantity=2)
    fulfillment.run_executor_once(clock["now"])
    with fulfillment._read_db() as db:
        running = db.execute(
            "SELECT * FROM tasks WHERE order_id=? AND stage='pick' AND status='running'",
            (order["id"],),
        ).fetchone()
        allocation = db.execute(
            "SELECT inventory_row_id FROM sub_order_allocations WHERE id=?",
            (running["allocation_id"],),
        ).fetchone()
        accepted_free = tuple(db.execute(
            "SELECT wms_qty,erp_qty,vision_qty FROM inventory_snapshot WHERE id=?",
            (allocation["inventory_row_id"],),
        ).fetchone())
        accepted_accounting = tuple(db.execute(
            "SELECT reserved_qty,picked_qty FROM inventory_snapshot WHERE id=?",
            (allocation["inventory_row_id"],),
        ).fetchone())
    robot = next(
        row for row in fulfillment.source_rows("robots")
        if row["robot_id"] == running["resource_id"]
    )
    approve_robot_hold(robot)
    release = internal_intervention("fleet_readiness", "DC-01", robot["robot_id"])
    action(release, "investigate", "fleet")
    action(
        release,
        "propose",
        "fleet",
        value="release",
        evidence={"finding": "inspection passed", "source": "test"},
    )
    action(release, "handoff", "fleet")
    action(release, "approve", "supervisor")
    # A released safety pause is admitted again only on the assignment cadence.
    clock["now"] += timedelta(seconds=60)
    fulfillment.run_executor_once(clock["now"])
    clock["now"] += timedelta(seconds=45)
    assert fulfillment.run_executor_once(clock["now"]) == 1
    with fulfillment._read_db() as db:
        current = db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
            "FROM inventory_snapshot WHERE id=?", (allocation["inventory_row_id"],)
        ).fetchone()
    assert tuple(current[:3]) == accepted_free
    assert tuple(current[3:]) == (
        accepted_accounting[0] - 2,
        accepted_accounting[1] + 2,
    )


def test_v2_robot_eligibility_keeps_persona_hold_and_source_safety(isolated_db):
    with fulfillment._read_db() as db:
        robot = next(
            row for row in fulfillment.source_rows("robots")
            if fulfillment.v2_robot_eligibility(db, row, "DC-01", "pick", 1)[0]
        )
    approve_robot_hold(robot)
    with fulfillment._read_db() as db:
        safe, reasons = fulfillment.v2_robot_eligibility(db, robot, "DC-01", "pick", 1)
    assert not safe
    assert any("hold" in reason.lower() for reason in reasons)


def test_role_scope_is_still_enforced(isolated_db):
    item = intervention(
        "inventory_mismatch", "DC-01", "SKU-01146@DC-01-Z03-B017", "supervisor"
    )
    with pytest.raises(HTTPException) as caught:
        action(item, "investigate", "fleet")
    assert caught.value.status_code == 403