import hashlib
import json
import sqlite3

import pytest

from maintenance_lock import runtime_lock
from operational_order_reset import RESET_KEY, reset_operational_orders


FULFILLMENT_SCHEMA = """
CREATE TABLE orders(id TEXT PRIMARY KEY, request_id TEXT);
CREATE TABLE order_lines(order_id TEXT, sku TEXT, quantity INTEGER);
CREATE TABLE reservations(id TEXT, order_id TEXT);
CREATE TABLE tasks(id TEXT PRIMARY KEY, order_id TEXT);
CREATE TABLE task_resources(task_id TEXT, resource_id TEXT);
CREATE TABLE events(id INTEGER, order_id TEXT);
CREATE TABLE stock_effects(task_id TEXT);
CREATE TABLE inventory_snapshot(
 id INTEGER PRIMARY KEY, warehouse_id TEXT, sku TEXT, location TEXT,
 wms_qty INTEGER, erp_qty INTEGER, vision_qty INTEGER, reserved_qty INTEGER,
 external_reserved_qty INTEGER, picked_qty INTEGER, completed_qty INTEGER,
 revision INTEGER, updated_at TEXT, opening_discrepancy TEXT);
CREATE TABLE sub_orders(id TEXT PRIMARY KEY, order_id TEXT);
CREATE TABLE sub_order_allocations(
 id TEXT, sub_order_id TEXT, inventory_row_id INTEGER, quantity INTEGER,
 reserved_qty INTEGER, picked_qty INTEGER, completed_qty INTEGER);
CREATE TABLE legacy_inventory_allocations(
 reservation_id TEXT, inventory_row_id INTEGER, quantity INTEGER,
 reserved_qty INTEGER, picked_qty INTEGER, completed_qty INTEGER);
CREATE TABLE inventory_movements(id TEXT, order_id TEXT);
CREATE TABLE inventory_corrections(id TEXT, reason TEXT);
CREATE TABLE persona_interventions(
 id TEXT PRIMARY KEY, dedupe_key TEXT, kind TEXT, entity_id TEXT, title TEXT, description TEXT,
 evidence_json TEXT, proposed_action_json TEXT);
CREATE TABLE persona_intervention_events(
 id INTEGER PRIMARY KEY, intervention_id TEXT, reason TEXT, details_json TEXT);
CREATE TABLE persona_audit_events(
 id INTEGER PRIMARY KEY, entity_id TEXT, reason TEXT, details_json TEXT);
CREATE TABLE persona_task_pauses(task_id TEXT);
CREATE TABLE persona_resource_blocks(resource_id TEXT, intervention_id TEXT);
CREATE TABLE persona_safety_holds(robot_id TEXT, intervention_id TEXT);
CREATE TABLE persona_inventory_overlays(warehouse_id TEXT, intervention_id TEXT);
CREATE TABLE persona_source_corrections(dataset TEXT, intervention_id TEXT);
CREATE TABLE persona_detection_state(id INTEGER);
CREATE TABLE persona_v2_detection_state(id INTEGER);
"""

BAZAAR_SCHEMA = """
CREATE TABLE orders(id TEXT PRIMARY KEY, request_id TEXT);
CREATE TABLE order_lines(order_id TEXT, sku TEXT);
CREATE TABLE outbox(order_id TEXT, payload_json TEXT);
"""


def _fixture(tmp_path):
    fulfillment = tmp_path / "fulfillment.sqlite"
    bazaar = tmp_path / "bazaar.sqlite"
    with sqlite3.connect(fulfillment) as db:
        db.executescript(FULFILLMENT_SCHEMA)
        db.execute("INSERT INTO orders VALUES ('ORDER-OLD','fulfillment-request')")
        db.execute("INSERT INTO order_lines VALUES ('ORDER-OLD','SKU-1',15)")
        db.execute("INSERT INTO reservations VALUES ('RES-OLD','ORDER-OLD')")
        db.execute("INSERT INTO tasks VALUES ('TASK-OLD','ORDER-OLD')")
        db.execute("INSERT INTO task_resources VALUES ('TASK-OLD','ROBOT-1')")
        db.execute("INSERT INTO events VALUES (1,'ORDER-OLD')")
        db.execute("INSERT INTO stock_effects VALUES ('TASK-OLD')")
        db.execute(
            "INSERT INTO inventory_snapshot VALUES "
            "(1,'WH-1','SKU-1','LOC-1',85,84,83,15,5,3,2,0,'old',"
            "'Reservation RES-OLD requires review')"
        )
        db.execute("INSERT INTO sub_orders VALUES ('SUB-OLD','ORDER-OLD')")
        db.execute(
            "INSERT INTO sub_order_allocations VALUES "
            "('ALLOC-OLD','SUB-OLD',1,10,6,3,1)"
        )
        db.execute(
            "INSERT INTO legacy_inventory_allocations VALUES "
            "('RES-OLD',1,5,4,0,1)"
        )
        db.execute("INSERT INTO inventory_movements VALUES ('MOV-OLD','ORDER-OLD')")
        db.execute(
            "INSERT INTO inventory_corrections VALUES "
            "('CORR-KEEP','verified after ORDER-OLD review')"
        )
        db.execute(
            "INSERT INTO persona_interventions VALUES "
            "('INT-INVENTORY','inventory:SKU-1','inventory_mismatch','SKU-1@LOC-1','Inventory issue',"
            "'Unrelated correction',?,NULL)",
            (json.dumps({
                "linked_work": [{
                    "order_id": "ORDER-OLD",
                    "task_id": "TASK-OLD",
                    "sku": "SKU-1",
                }],
                "current_state": {
                    "sku": "SKU-1",
                    "note": "Previously checked ORDER-OLD",
                },
            }),),
        )
        db.execute(
            "INSERT INTO persona_interventions VALUES "
            "('INT-ORDER','priority:ORDER-OLD','priority_override','ORDER-OLD','Old order','ORDER-OLD',?,NULL)",
            (json.dumps({"target_order_id": "ORDER-OLD"}),),
        )
        db.execute(
            "INSERT INTO persona_interventions VALUES "
            "('INT-SAFETY','resource:TASK-OLD','resource_failure','ROBOT-1','Safety','Preserve hold',?,NULL)",
            (json.dumps({"linked_work": [{"task_id": "TASK-OLD"}]}),),
        )
        db.execute(
            "INSERT INTO persona_intervention_events VALUES "
            "(1,'INT-INVENTORY','reviewed','{\"order_id\":\"ORDER-OLD\"}')"
        )
        db.execute(
            "INSERT INTO persona_audit_events VALUES "
            "(1,'ORDER-OLD','old order','{\"order_id\":\"ORDER-OLD\"}')"
        )
        db.execute(
            "INSERT INTO persona_audit_events VALUES "
            "(2,'SKU-1','correction kept','{\"correction\":\"CORR-KEEP\"}')"
        )
        db.execute("INSERT INTO persona_task_pauses VALUES ('TASK-OLD')")
        db.execute("INSERT INTO persona_resource_blocks VALUES ('ROBOT-1','INT-SAFETY')")
        db.execute("INSERT INTO persona_safety_holds VALUES ('ROBOT-1','INT-SAFETY')")
        db.execute("INSERT INTO persona_source_corrections VALUES ('robots','INT-SAFETY')")
        db.execute("INSERT INTO persona_detection_state VALUES (1)")
        db.execute("INSERT INTO persona_v2_detection_state VALUES (1)")
    with sqlite3.connect(bazaar) as db:
        db.executescript(BAZAAR_SCHEMA)
        db.execute("INSERT INTO orders VALUES ('BZ-OLD','bazaar-request')")
        db.execute("INSERT INTO order_lines VALUES ('BZ-OLD','SKU-1')")
        db.execute("INSERT INTO outbox VALUES ('BZ-OLD','{\"id\":\"BZ-OLD\"}')")
    return fulfillment, bazaar


def _run(fulfillment, bazaar, tmp_path, **kwargs):
    return reset_operational_orders(
        fulfillment,
        bazaar,
        backup_dir=tmp_path / "backups",
        development=True,
        **kwargs,
    )


def test_reset_releases_only_unpicked_and_preserves_non_order_balances(tmp_path):
    fulfillment, bazaar = _fixture(tmp_path)
    result = _run(fulfillment, bazaar, tmp_path)
    assert result["released_unpicked_qty"] == 10
    with sqlite3.connect(fulfillment) as db:
        inventory = db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty,external_reserved_qty,"
            "picked_qty,completed_qty FROM inventory_snapshot"
        ).fetchone()
        assert inventory == (95, 94, 93, 5, 5, 3, 2)
        baseline = db.execute(
            "SELECT released_unpicked_qty,picked_qty,completed_qty "
            "FROM operational_reset_inventory_baseline WHERE reset_key=?",
            (RESET_KEY,),
        ).fetchone()
        assert baseline == (10, 3, 2)
        assert db.execute("SELECT COUNT(*) FROM inventory_corrections").fetchone()[0] == 1
        correction = db.execute("SELECT reason FROM inventory_corrections").fetchone()[0]
        discrepancy = db.execute(
            "SELECT opening_discrepancy FROM inventory_snapshot"
        ).fetchone()[0]
        assert "ORDER-OLD" not in correction
        assert discrepancy and "RES-OLD" not in discrepancy
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0
        digest = db.execute("SELECT request_digest FROM retired_order_requests").fetchone()[0]
        assert digest == hashlib.sha256(b"fulfillment-request").hexdigest()
        assert "fulfillment-request" not in digest
    with sqlite3.connect(bazaar) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        digest = db.execute("SELECT request_digest FROM retired_order_requests").fetchone()[0]
        assert digest == hashlib.sha256(b"bazaar-request").hexdigest()


def test_reset_removes_dangling_order_references_but_keeps_safety_state(tmp_path):
    fulfillment, bazaar = _fixture(tmp_path)
    _run(fulfillment, bazaar, tmp_path)
    with sqlite3.connect(fulfillment) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM persona_interventions WHERE id='INT-ORDER'"
        ).fetchone()[0] == 0
        evidence = db.execute(
            "SELECT evidence_json FROM persona_interventions WHERE id='INT-INVENTORY'"
        ).fetchone()[0]
        assert "ORDER-OLD" not in evidence and "TASK-OLD" not in evidence
        assert json.loads(evidence)["linked_work"] == []
        safety = db.execute(
            "SELECT evidence_json FROM persona_interventions WHERE id='INT-SAFETY'"
        ).fetchone()[0]
        assert "TASK-OLD" not in safety
        assert db.execute("SELECT COUNT(*) FROM persona_resource_blocks").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM persona_safety_holds").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM persona_source_corrections").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM persona_task_pauses").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM persona_detection_state").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM persona_v2_detection_state").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM persona_audit_events").fetchone()[0] == 1


def test_cross_database_failure_rolls_back_and_backups_are_recoverable(tmp_path):
    fulfillment, bazaar = _fixture(tmp_path)

    def fail(phase):
        if phase == "after_bazaar_delete":
            raise ValueError("injected failure")

    with pytest.raises(ValueError, match="injected failure"):
        _run(fulfillment, bazaar, tmp_path, failpoint=fail)
    with sqlite3.connect(fulfillment) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        assert db.execute("SELECT reserved_qty FROM inventory_snapshot").fetchone()[0] == 15
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='maintenance_resets'"
        ).fetchone()
    with sqlite3.connect(bazaar) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
    backups = sorted((tmp_path / "backups").glob("*.sqlite"))
    assert len(backups) == 2
    for backup in backups:
        with sqlite3.connect(backup) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_reset_fails_closed_before_releasing_external_reservation(tmp_path):
    fulfillment, bazaar = _fixture(tmp_path)
    with sqlite3.connect(fulfillment) as db:
        # Only three units are internally reserved, but allocations claim ten.
        db.execute(
            "UPDATE inventory_snapshot SET reserved_qty=8,external_reserved_qty=5"
        )
    with pytest.raises(RuntimeError, match="inconsistent reserved balance"):
        _run(fulfillment, bazaar, tmp_path)
    with sqlite3.connect(fulfillment) as db:
        assert db.execute(
            "SELECT reserved_qty,external_reserved_qty FROM inventory_snapshot"
        ).fetchone() == (8, 5)
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='maintenance_resets'"
        ).fetchone()


def test_cancelled_allocations_do_not_double_release_or_restore_picked_stock(tmp_path):
    fulfillment, bazaar = _fixture(tmp_path)
    with sqlite3.connect(fulfillment) as db:
        db.executemany(
            "INSERT INTO inventory_snapshot("
            "id,warehouse_id,sku,location,wms_qty,erp_qty,vision_qty,reserved_qty,"
            "external_reserved_qty,picked_qty,completed_qty,revision,updated_at,"
            "opening_discrepancy) VALUES (?,'WH-1','SKU-1',?,?,?,?,?,?,?,?,?,?,NULL)",
            [
                (2, "LOC-CANCELLED", 90, 90, 90, 0, 0, 0, 0, 0, "old"),
                (3, "LOC-PARTIAL", 90, 90, 90, 0, 0, 3, 0, 0, "old"),
            ],
        )
        db.executemany(
            "INSERT INTO sub_order_allocations VALUES (?,?,?,?,?,?,?)",
            [
                ("ALLOC-CANCELLED", "SUB-OLD", 2, 10, 0, 0, 0),
                ("ALLOC-PARTIAL", "SUB-OLD", 3, 10, 0, 3, 0),
            ],
        )
    result = _run(fulfillment, bazaar, tmp_path)
    # Only the original fixture's still-outstanding 10 units are released.
    assert result["released_unpicked_qty"] == 10
    with sqlite3.connect(fulfillment) as db:
        cancelled = db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
            "FROM inventory_snapshot WHERE id=2"
        ).fetchone()
        partial = db.execute(
            "SELECT wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
            "FROM inventory_snapshot WHERE id=3"
        ).fetchone()
        assert cancelled == (90, 90, 90, 0, 0)
        assert partial == (90, 90, 90, 0, 3)
        baselines = db.execute(
            "SELECT inventory_row_id,released_unpicked_qty,picked_qty "
            "FROM operational_reset_inventory_baseline WHERE inventory_row_id IN (2,3) "
            "ORDER BY inventory_row_id"
        ).fetchall()
        assert baselines == [(2, 0, 0), (3, 0, 3)]


def test_durable_marker_makes_rerun_leave_new_orders_untouched(tmp_path):
    fulfillment, bazaar = _fixture(tmp_path)
    _run(fulfillment, bazaar, tmp_path)
    with sqlite3.connect(fulfillment) as db:
        db.execute("INSERT INTO orders(id,request_id) VALUES ('ORDER-NEW','new-request')")
    with sqlite3.connect(bazaar) as db:
        db.execute("INSERT INTO orders(id,request_id) VALUES ('BZ-NEW','new-bazaar-request')")
    result = _run(fulfillment, bazaar, tmp_path)
    assert result == {"applied": False, "reason": "already_applied"}
    with sqlite3.connect(fulfillment) as db:
        assert db.execute("SELECT id FROM orders").fetchone()[0] == "ORDER-NEW"
    with sqlite3.connect(bazaar) as db:
        assert db.execute("SELECT id FROM orders").fetchone()[0] == "BZ-NEW"
    assert len(list((tmp_path / "backups").glob("*.sqlite"))) == 2


def test_runtime_writer_lock_excludes_offline_reset(tmp_path):
    fulfillment, bazaar = _fixture(tmp_path)
    with runtime_lock(tmp_path):
        with pytest.raises(RuntimeError, match="database is in use"):
            _run(fulfillment, bazaar, tmp_path)
    assert not (tmp_path / "backups").exists()
    with sqlite3.connect(fulfillment) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1