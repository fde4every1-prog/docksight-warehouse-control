"""Isolated fleet readiness repair API regressions."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi import HTTPException

import fulfillment_api as fulfillment
import persona_api as persona


@pytest.fixture
def fleet_db(tmp_path, monkeypatch):
    data = {
        "inventory": (
            {
                "warehouse_id": "W-1",
                "sku": "SKU-1",
                "location": "W-1-Z1-B1",
                "wms_qty": "20",
                "erp_qty": "20",
                "vision_qty": "20",
                "reserved_qty": "0",
                "inventory_status": "AVAILABLE",
                "weight_kg": "1",
            },
        ),
        "skus": ({"sku": "SKU-1"},),
        "warehouses": ({"warehouse_id": "W-1"},),
        "labor_capacity": (),
        "robots": (
            {
                "robot_id": "R-1",
                "warehouse_id": "W-1",
                "robot_type": "AMR",
                "health_status": "DEGRADED",
                "safety_cert_status": "VALID",
                "connectivity": "ONLINE",
                "payload_kg": "100",
                "battery_soc": "90",
            },
        ),
        "maintenance": (
            {
                "work_order_id": "M-1",
                "robot_id": "R-1",
                "cmms_status": "OPEN",
                "fleet_availability": "UNAVAILABLE",
            },
        ),
        "control_assets": (
            {
                "asset_id": "A-1",
                "warehouse_id": "W-1",
                "asset_type": "CONVEYOR",
                "state": "OFFLINE",
                "maintenance_state": "DUE",
            },
        ),
    }

    def rows(dataset):
        return data.get(dataset, ())

    rows.cache_clear = lambda: None
    monkeypatch.setattr(persona, "_ORIGINAL_RAW_SOURCE_ROWS", rows)
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "fleet.sqlite")
    clock = {"now": datetime(2030, 1, 1, tzinfo=timezone.utc)}
    monkeypatch.setattr(fulfillment, "utc_now", lambda: clock["now"])
    fulfillment._init_db()
    persona._ensure_schema()
    data["_clock"] = clock
    return data


def repaired_contexts(issue):
    contexts = []
    for context in issue["contexts"]:
        values = dict(context["values"])
        if context["entity_type"] == "robot":
            values.update(
                health_status="HEALTHY",
                safety_cert_status="VALID",
                connectivity="ONLINE",
            )
        elif context["entity_type"] == "maintenance":
            values.update(cmms_status="CLOSED", fleet_availability="AVAILABLE")
        else:
            values.update(state="AVAILABLE", maintenance_state="CLEAR")
        contexts.append(
            {
                "entity_type": context["entity_type"],
                "entity_id": context["entity_id"],
                "revision": context["revision"],
                "values": values,
            }
        )
    return contexts


def partial_contexts(issue, edited_type, values):
    return [
        {
            "entity_type": context["entity_type"],
            "entity_id": context["entity_id"],
            "revision": context["revision"],
            "values": values if context["entity_type"] == edited_type else {},
        }
        for context in issue["contexts"]
    ]


def create_test_order():
    return fulfillment.create_order(
        fulfillment.OrderInput(
            priority="high",
            lines=[fulfillment.OrderLineInput(sku="SKU-1", quantity=2)],
            request_id=str(uuid.uuid4()),
            source_order_id=f"FBZ-{uuid.uuid4()}",
            order_service="Same_Day",
            order_source="fde_bazaar",
            order_created_at="2030-01-01T00:00:00Z",
        )
    )


def test_direct_atomic_repair_and_persistent_effective_reads(fleet_db):
    result = persona._fleet_issues("fleet", 10, 0, "")
    assert result["pagination"] == {"limit": 10, "offset": 0, "total": 2}
    issue = next(item for item in result["items"] if item["entity_id"] == "R-1")
    repaired = persona.repair_fleet_issue(
        issue["id"],
        persona.FleetRepairRequest(
            fingerprint=issue["fingerprint"], contexts=repaired_contexts(issue)
        ),
        "fleet",
    )
    assert repaired["status"] == "resolved"
    assert repaired["blockers"] == []
    assert persona._fleet_issues("fleet")["pagination"]["total"] == 1
    # No active transaction: durable corrections still win on normal readers.
    robot = fulfillment.source_rows("robots")[0]
    maintenance = fulfillment.source_rows("maintenance")[0]
    assert robot["health_status"] == "HEALTHY"
    assert maintenance["fleet_availability"] == "AVAILABLE"
    assert any(event["action"] == "repaired" for event in repaired["events"])


def test_dynamic_priority_search_detail_page_and_downgrade(fleet_db):
    created = create_test_order()
    task = created["sub_orders"][0]["tasks"][0]

    result = persona._fleet_issues("fleet", 1, 0, "")
    assert result["items"][0]["entity_id"] == "R-1"
    assert result["items"][0]["priority"] == "P1"
    assert result["items"][0]["impacted_orders"] == [
        {"order_id": created["id"], "task_ids": [task["id"]]}
    ]
    assert result["items"][0]["priority_reason"]
    assert persona._fleet_issues("fleet", 10, 0, created["id"])["pagination"]["total"] == 1
    detail = persona.fleet_issue(result["items"][0]["id"], "fleet")
    assert detail["impacted_orders"] == result["items"][0]["impacted_orders"]

    with fulfillment.db_transaction() as db:
        db.execute(
            "UPDATE tasks SET status='completed',completed_at=? WHERE id=?",
            ("2030-01-01T00:01:00Z", task["id"]),
        )
    downgraded = persona.fleet_issue(result["items"][0]["id"], "fleet")
    assert downgraded["priority"] == "P2"
    assert downgraded["priority_reason"] is None
    assert downgraded["impacted_orders"] == []


def test_unassigned_compatibility_and_assigned_owner_are_exact(fleet_db):
    extra_robots = (
        {
            "robot_id": "R-WRONG-WH",
            "warehouse_id": "W-2",
            "robot_type": "AMR",
            "health_status": "DEGRADED",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "payload_kg": "100",
            "battery_soc": "90",
        },
        {
            "robot_id": "R-WRONG-TYPE",
            "warehouse_id": "W-1",
            "robot_type": "DRONE",
            "health_status": "DEGRADED",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "payload_kg": "100",
            "battery_soc": "90",
        },
        {
            "robot_id": "R-TOO-SMALL",
            "warehouse_id": "W-1",
            "robot_type": "AMR",
            "health_status": "DEGRADED",
            "safety_cert_status": "VALID",
            "connectivity": "ONLINE",
            "payload_kg": "1",
            "battery_soc": "90",
        },
    )
    fleet_db["robots"] += extra_robots
    fleet_db["maintenance"] += tuple(
        {
            "work_order_id": f"M-{robot['robot_id']}",
            "robot_id": robot["robot_id"],
            "cmms_status": "OPEN",
            "fleet_availability": "UNAVAILABLE",
        }
        for robot in extra_robots
    )
    created = create_test_order()
    task = created["sub_orders"][0]["tasks"][0]
    issues = {
        item["entity_id"]: item for item in persona._fleet_issues("fleet", 100)["items"]
    }
    assert issues["R-1"]["priority"] == "P1"
    for robot_id in ("R-WRONG-WH", "R-WRONG-TYPE", "R-TOO-SMALL"):
        assert issues[robot_id]["priority"] == "P2"

    with fulfillment.db_transaction() as db:
        db.execute(
            "UPDATE tasks SET status='paused',resource_id='R-WRONG-TYPE',"
            "resource_type='robot' WHERE id=?",
            (task["id"],),
        )
    issues = {
        item["entity_id"]: item for item in persona._fleet_issues("fleet", 100)["items"]
    }
    assert issues["R-WRONG-TYPE"]["priority"] == "P1"
    assert issues["R-1"]["priority"] == "P2"


def test_fingerprint_and_context_revision_reject_stale_entire_snapshot(fleet_db):
    issue = next(
        item
        for item in persona._fleet_issues("fleet")["items"]
        if item["entity_id"] == "R-1"
    )
    with fulfillment.db_transaction() as db:
        db.execute(
            "INSERT INTO registered_resources(dataset,row_id,values_json,registered_at) "
            "VALUES ('maintenance','M-2',?,?)",
            (
                '{"work_order_id":"M-2","robot_id":"R-1","cmms_status":"OPEN",'
                '"fleet_availability":"UNAVAILABLE"}',
                "2030-01-01T00:00:00Z",
            ),
        )
    with pytest.raises(HTTPException) as stale:
        persona.repair_fleet_issue(
            issue["id"],
            persona.FleetRepairRequest(
                fingerprint=issue["fingerprint"], contexts=repaired_contexts(issue)
            ),
            "fleet",
        )
    assert stale.value.status_code == 409


def test_missing_maintenance_can_be_explicitly_registered(tmp_path, monkeypatch):
    def rows(dataset):
        if dataset == "robots":
            return (
                {
                    "robot_id": "R-MISSING",
                    "warehouse_id": "W-1",
                    "health_status": "HEALTHY",
                    "safety_cert_status": "VALID",
                    "connectivity": "ONLINE",
                },
            )
        return ()

    rows.cache_clear = lambda: None
    monkeypatch.setattr(persona, "_ORIGINAL_RAW_SOURCE_ROWS", rows)
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "missing.sqlite")
    fulfillment._init_db()
    persona._ensure_schema()
    issue = persona._fleet_issues("fleet")["items"][0]
    missing = next(context for context in issue["contexts"] if context.get("missing"))
    assert missing["values"] == {"cmms_status": None, "fleet_availability": None}
    repaired = persona.repair_fleet_issue(
        issue["id"],
        persona.FleetRepairRequest(
            fingerprint=issue["fingerprint"], contexts=repaired_contexts(issue)
        ),
        "fleet",
    )
    assert repaired["status"] == "resolved"
    registered = fulfillment.source_rows("maintenance")
    assert registered[0]["work_order_id"] == "MAINT-R-MISSING"
    assert registered[0]["warehouse_id"] == "W-1"
    assert fulfillment.maintenance_exclusions("W-1")[0]["robot_id"] == "R-MISSING"


def test_admin_read_only_and_supervisor_forbidden(fleet_db):
    issue = persona._fleet_issues("admin")["items"][0]
    with pytest.raises(HTTPException) as forbidden:
        persona._fleet_issues("supervisor")
    assert forbidden.value.status_code == 403
    with pytest.raises(HTTPException) as read_only:
        persona.repair_fleet_issue(
            issue["id"],
            persona.FleetRepairRequest(
                fingerprint=issue["fingerprint"], contexts=repaired_contexts(issue)
            ),
            "admin",
        )
    assert read_only.value.status_code == 403


def test_invalid_multi_context_repair_rolls_back(fleet_db):
    issue = next(
        item
        for item in persona._fleet_issues("fleet")["items"]
        if item["entity_id"] == "R-1"
    )
    contexts = repaired_contexts(issue)
    contexts[-1]["values"]["fleet_availability"] = "NOT_A_VALUE"
    with pytest.raises(HTTPException) as invalid:
        persona.repair_fleet_issue(
            issue["id"],
            persona.FleetRepairRequest(
                fingerprint=issue["fingerprint"], contexts=contexts
            ),
            "fleet",
        )
    assert invalid.value.status_code == 422
    assert fulfillment.source_rows("robots")[0]["health_status"] == "DEGRADED"


def test_partial_robot_only_repair_accepts_unchanged_maintenance_context(fleet_db):
    issue = next(
        item
        for item in persona._fleet_issues("fleet")["items"]
        if item["entity_id"] == "R-1"
    )
    updated = persona.repair_fleet_issue(
        issue["id"],
        persona.FleetRepairRequest(
            fingerprint=issue["fingerprint"],
            contexts=partial_contexts(
                issue,
                "robot",
                {
                    "health_status": "HEALTHY",
                    "safety_cert_status": "VALID",
                    "connectivity": "ONLINE",
                },
            ),
        ),
        "fleet",
    )
    assert updated["status"] == "open"
    assert fulfillment.source_rows("robots")[0]["health_status"] == "HEALTHY"
    assert fulfillment.source_rows("maintenance")[0]["cmms_status"] == "OPEN"


def test_partial_maintenance_only_repair_accepts_unchanged_robot_context(fleet_db):
    issue = next(
        item
        for item in persona._fleet_issues("fleet")["items"]
        if item["entity_id"] == "R-1"
    )
    updated = persona.repair_fleet_issue(
        issue["id"],
        persona.FleetRepairRequest(
            fingerprint=issue["fingerprint"],
            contexts=partial_contexts(
                issue,
                "maintenance",
                {"cmms_status": "CLOSED", "fleet_availability": "AVAILABLE"},
            ),
        ),
        "fleet",
    )
    assert updated["status"] == "open"
    assert fulfillment.source_rows("robots")[0]["health_status"] == "DEGRADED"
    assert fulfillment.source_rows("maintenance")[0]["cmms_status"] == "CLOSED"


def test_missing_maintenance_empty_context_can_remain_missing(tmp_path, monkeypatch):
    def rows(dataset):
        if dataset == "robots":
            return (
                {
                    "robot_id": "R-PARTIAL",
                    "warehouse_id": "W-1",
                    "health_status": "DEGRADED",
                    "safety_cert_status": "VALID",
                    "connectivity": "ONLINE",
                },
            )
        return ()

    rows.cache_clear = lambda: None
    monkeypatch.setattr(persona, "_ORIGINAL_RAW_SOURCE_ROWS", rows)
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "missing-partial.sqlite")
    fulfillment._init_db()
    persona._ensure_schema()
    issue = persona._fleet_issues("fleet")["items"][0]
    updated = persona.repair_fleet_issue(
        issue["id"],
        persona.FleetRepairRequest(
            fingerprint=issue["fingerprint"],
            contexts=partial_contexts(
                issue,
                "robot",
                {
                    "health_status": "HEALTHY",
                    "safety_cert_status": "VALID",
                    "connectivity": "ONLINE",
                },
            ),
        ),
        "fleet",
    )
    assert updated["status"] == "open"
    assert any(context.get("missing") for context in updated["contexts"])
    assert fulfillment.source_rows("maintenance") == ()


def test_duplicate_context_is_rejected(fleet_db):
    issue = next(
        item
        for item in persona._fleet_issues("fleet")["items"]
        if item["entity_id"] == "R-1"
    )
    contexts = repaired_contexts(issue)
    contexts[-1] = contexts[0]
    with pytest.raises(HTTPException) as duplicate:
        persona.repair_fleet_issue(
            issue["id"],
            persona.FleetRepairRequest(
                fingerprint=issue["fingerprint"], contexts=contexts
            ),
            "fleet",
        )
    assert duplicate.value.status_code == 409


def test_identityless_maintenance_row_gets_stable_editable_identity(
    tmp_path, monkeypatch
):
    def rows(dataset):
        if dataset == "robots":
            return (
                {
                    "robot_id": "R-NO-WO",
                    "warehouse_id": "W-1",
                    "health_status": "HEALTHY",
                    "safety_cert_status": "VALID",
                    "connectivity": "ONLINE",
                },
            )
        if dataset == "maintenance":
            return (
                {
                    "robot_id": "R-NO-WO",
                    "cmms_status": "OPEN",
                    "fleet_availability": "UNAVAILABLE",
                },
            )
        return ()

    rows.cache_clear = lambda: None
    monkeypatch.setattr(persona, "_ORIGINAL_RAW_SOURCE_ROWS", rows)
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "identityless.sqlite")
    fulfillment._init_db()
    persona._ensure_schema()
    issue = persona._fleet_issues("fleet")["items"][0]
    maintenance = next(
        context
        for context in issue["contexts"]
        if context["entity_type"] == "maintenance"
    )
    assert maintenance["entity_id"] == "MAINT-R-NO-WO-ROW-1"
    assert not maintenance.get("missing")
    repaired = persona.repair_fleet_issue(
        issue["id"],
        persona.FleetRepairRequest(
            fingerprint=issue["fingerprint"],
            contexts=partial_contexts(
                issue,
                "maintenance",
                {"cmms_status": "CLOSED", "fleet_availability": "AVAILABLE"},
            ),
        ),
        "fleet",
    )
    assert repaired["status"] == "resolved"


def test_saved_correction_is_final_overlay_after_scenario_value(fleet_db):
    issue = next(
        item
        for item in persona._fleet_issues("fleet")["items"]
        if item["entity_id"] == "R-1"
    )
    persona.repair_fleet_issue(
        issue["id"],
        persona.FleetRepairRequest(
            fingerprint=issue["fingerprint"], contexts=repaired_contexts(issue)
        ),
        "fleet",
    )
    with fulfillment.db_transaction() as db:
        db.execute(
            "INSERT INTO scenario_overrides(dataset,row_index,values_json) "
            "VALUES ('robots',0,'{\"health_status\":\"FAILED\"}')"
        )
        db.execute("UPDATE scenario_state SET revision=revision+1 WHERE id=1")
    assert fulfillment.source_rows("robots")[0]["health_status"] == "HEALTHY"


def test_endpoint_repairs_resume_auto_mapped_v2_stages_exactly_once(fleet_db):
    clock = fleet_db["_clock"]
    created = fulfillment.create_order(
        fulfillment.OrderInput(
            priority="high",
            lines=[fulfillment.OrderLineInput(sku="SKU-1", quantity=2)],
            request_id=str(uuid.uuid4()),
            source_order_id=f"FBZ-{uuid.uuid4()}",
            order_service="Same_Day",
            order_source="fde_bazaar",
            order_created_at="2030-01-01T00:00:00Z",
        )
    )
    assert created["warehouse_id"] is None
    assert created["sub_orders"][0]["warehouse_id"] == "W-1"
    assert [task["stage"] for task in created["sub_orders"][0]["tasks"]] == [
        "pick",
        "move",
        "pack_feed",
        "stage",
    ]
    assert fulfillment.run_executor_once(clock["now"]) == 0

    for issue in list(persona._fleet_issues("fleet")["items"]):
        persona.repair_fleet_issue(
            issue["id"],
            persona.FleetRepairRequest(
                fingerprint=issue["fingerprint"],
                contexts=repaired_contexts(issue),
            ),
            "fleet",
        )
    for _ in range(10):
        fulfillment.run_executor_once(clock["now"])
        clock["now"] += timedelta(seconds=45)
    detail = fulfillment.get_order(created["id"])
    assert detail["status"] == "completed"
    assert all(task["status"] == "completed" for task in detail["tasks"])
    with fulfillment._read_db() as db:
        stock = fulfillment.inventory_rows(db, warehouse_id="W-1", sku="SKU-1")[0]
        movements = db.execute(
            "SELECT COUNT(*) FROM inventory_movements "
                "WHERE movement_type='pick_complete' AND sub_order_id=?",
            (created["sub_orders"][0]["id"],),
        ).fetchone()[0]
    assert (stock["wms_qty"], stock["picked_qty"], stock["completed_qty"]) == (18, 0, 2)
    assert movements == 1
    assert fulfillment.run_executor_once(clock["now"]) == 0