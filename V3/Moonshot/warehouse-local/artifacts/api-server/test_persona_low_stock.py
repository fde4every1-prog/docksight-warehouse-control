"""Focused grouped low-stock workspace contract tests."""

import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import fulfillment_api as fulfillment
import persona_api as persona
import demand_forecast


@pytest.fixture
def low_stock_db(tmp_path, monkeypatch):
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "low-stock.sqlite")
    monkeypatch.setattr(
        fulfillment, "utc_now", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    fulfillment._init_db()
    with fulfillment.db_transaction() as db:
        demand_forecast.generate(
            db,
            datetime(2030, 1, 1, tzinfo=timezone.utc).date(),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
    persona._ensure_schema()
    monkeypatch.setattr(persona, "_detect_all", lambda db: None)
    monkeypatch.setattr(persona, "_detect_v2", lambda db: None)
    return monkeypatch


@pytest.fixture
def detected_low_stock_db(tmp_path, monkeypatch):
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "detected-low-stock.sqlite")
    monkeypatch.setattr(
        fulfillment, "utc_now", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    fulfillment._init_db()
    with fulfillment.db_transaction() as db:
        source = dict(fulfillment.inventory_rows(db)[0])
        result = demand_forecast.generate(
            db, datetime(2030, 1, 1, tzinfo=timezone.utc).date(),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        db.execute(
            "UPDATE demand_forecasts SET forecast_7d=?,forecast_30d=? "
            "WHERE run_id=? AND warehouse_id=? AND sku=?",
            (
                int(source["allocatable_qty"]) + 1,
                int(source["allocatable_qty"]) + 1,
                result["run_id"],
                source["warehouse_id"],
                source["sku"],
            ),
        )
    persona._ensure_schema()
    return monkeypatch


def set_forecast_threshold(db, warehouse, sku, threshold):
    run = demand_forecast.latest_run(db)
    if run is None:
        result = demand_forecast.generate(
            db, datetime(2030, 1, 1, tzinfo=timezone.utc).date(),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        run_id = result["run_id"]
    else:
        run_id = run["id"]
    db.execute(
        "UPDATE demand_forecasts SET forecast_7d=?,forecast_30d=? "
        "WHERE run_id=? AND warehouse_id=? AND sku=?",
        (threshold, threshold, run_id, warehouse, sku),
    )


def add_replenishment(
    intervention_id,
    warehouse,
    sku,
    location,
    *,
    title=None,
    status="open",
    linked=False,
):
    evidence = {
        "sku": sku,
        "location": location,
        "available": 1,
        "threshold": 5,
        "linked_work": [{"id": "ORDER-1"}] if linked else [],
    }
    with fulfillment.db_transaction() as db:
        db.execute(
            "INSERT INTO persona_interventions "
            "(id,dedupe_key,kind,warehouse_id,entity_id,title,description,owner,"
            "status,evidence_json,proposed_action_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                intervention_id,
                intervention_id,
                "replenishment_alert",
                warehouse,
                f"{sku}@{location}",
                title or f"Replenishment alert: {sku} at {location}",
                "Free allocatable stock is below threshold",
                "supervisor",
                status,
                json.dumps(evidence),
                '{"approved":true}' if status == "investigating" else None,
                f"2030-01-01T00:00:{intervention_id[-2:] if intervention_id[-2:].isdigit() else '00'}Z",
                "2030-01-01T00:00:00Z",
            ),
        )


def test_full_grouping_paging_search_and_location_only(low_stock_db):
    alerts = [
        {"warehouse_id": "W1", "sku": f"SKU-{index:02d}", "available": index, "threshold": 20}
        for index in range(24)
    ]
    low_stock_db.setattr(fulfillment, "stock_alerts", lambda db: [dict(row) for row in alerts])
    add_replenishment("INT-01", "W1", "SKU-01", "BIN-A", linked=True)
    add_replenishment("INT-02", "W1", "SKU-01", "BIN-B")
    add_replenishment(
        "INT-03", "W2", "LOCATION-ONLY", "SPECIAL-BIN",
        title="Search-after-page-one marker",
        status="investigating",
    )
    add_replenishment("INT-04", "W2", "FIXED-WORKFLOW", "BIN-C", status="investigating")

    first = persona._low_stock("supervisor", 10, 0)
    second = persona._low_stock("supervisor", 10, 10)
    assert first["pagination"]["total"] == second["pagination"]["total"] == 26
    assert len(first["items"]) == len(second["items"]) == 10
    assert {item["id"] for item in first["items"]}.isdisjoint(
        item["id"] for item in second["items"]
    )

    combined = persona._low_stock("supervisor", 500, 0)
    grouped = next(item for item in combined["items"] if item["id"] == "W1:SKU-01")
    assert grouped["aggregate_alert"] == {
        "available": 1,
        "threshold": 20,
    }
    assert grouped["priority"] == "P1"
    assert {row["evidence"]["location"] for row in grouped["interventions"]} == {
        "BIN-A",
        "BIN-B",
    }
    assert len([item for item in combined["items"] if item["id"] == "W1:SKU-01"]) == 1

    location_only = next(
        item for item in combined["items"] if item["id"] == "W2:LOCATION-ONLY"
    )
    assert location_only["aggregate_alert"] is None
    assert location_only["interventions"][0]["status"] == "investigating"
    fixed = next(item for item in combined["items"] if item["id"] == "W2:FIXED-WORKFLOW")
    assert fixed["aggregate_alert"] is None
    assert fixed["interventions"]

    searched = persona._low_stock("supervisor", 10, 0, "after-page-one")
    assert searched["pagination"]["total"] == 1
    assert [item["id"] for item in searched["items"]] == ["W2:LOCATION-ONLY"]
    assert persona._low_stock("supervisor", 10, 0, "special-bin")["pagination"]["total"] == 1


def test_missing_forecast_is_unavailable_and_preserves_existing_shortage(low_stock_db):
    add_replenishment("INT-NO-FORECAST", "W1", "SKU-A", "BIN-A")
    with fulfillment.db_transaction() as db:
        db.execute("DELETE FROM demand_forecasts")
        db.execute("DELETE FROM demand_forecast_runs")
    with pytest.raises(HTTPException) as unavailable:
        persona._low_stock("supervisor")
    assert unavailable.value.status_code == 503
    assert "no valid demand forecast" in unavailable.value.detail
    with fulfillment._read_db() as db:
        retained = db.execute(
            "SELECT status,evidence_json FROM persona_interventions "
            "WHERE id='INT-NO-FORECAST'"
        ).fetchone()
    assert retained["status"] == "open"
    assert "condition_recovered" not in json.loads(retained["evidence_json"])


def test_aggregate_contract_exactly_matches_state_alerts(low_stock_db):
    state_alerts = fulfillment.state()["alerts"]
    first = persona._low_stock("supervisor", 500, 0)
    results = list(first["items"])
    for offset in range(500, first["pagination"]["total"], 500):
        results.extend(persona._low_stock("supervisor", 500, offset)["items"])
    grouped = {
        (item["warehouse_id"], item["sku"]): item["aggregate_alert"]
        for item in results
        if item["aggregate_alert"] is not None
    }
    expected = {
        (alert["warehouse_id"], alert["sku"]): {
            key: alert[key]
            for key in ("available", "threshold", "inventory_policy")
            if key in alert
        }
        for alert in state_alerts
    }
    assert grouped == expected


def test_low_stock_roles_and_deterministic_order(low_stock_db):
    low_stock_db.setattr(
        fulfillment,
        "stock_alerts",
        lambda db: [
            {"warehouse_id": "W2", "sku": "B", "available": 0, "threshold": 5},
            {"warehouse_id": "W1", "sku": "A", "available": 0, "threshold": 5},
        ],
    )
    assert [item["id"] for item in persona._low_stock("supervisor")["items"]] == [
        "W1:A",
        "W2:B",
    ]
    assert persona._low_stock("admin")["pagination"]["total"] == 2
    with pytest.raises(HTTPException) as caught:
        persona._low_stock("fleet")
    assert caught.value.status_code == 403


def _action(intervention_id, fingerprint, *, role="supervisor", reason="Reviewed shortage"):
    payload = persona.InterventionAction(
        action="manual_close",
        reason=reason,
        evidence={"condition_fingerprint": fingerprint},
    )
    with fulfillment.db_transaction() as db:
        return persona._action(role, intervention_id, payload, db)


def _operational_state():
    with fulfillment._read_db() as db:
        inventory = [
            tuple(row)
            for row in db.execute(
                "SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty,"
                "revision FROM inventory_snapshot ORDER BY id"
            )
        ]
        orders = [tuple(row) for row in db.execute("SELECT * FROM orders ORDER BY id")]
        tasks = [tuple(row) for row in db.execute("SELECT * FROM tasks ORDER BY id")]
        corrections = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_corrections"
        ).fetchone()["n"]
    return inventory, orders, tasks, corrections


def test_aggregate_alert_direct_close_is_durable_non_mutating_and_recurrence_safe(
    low_stock_db,
):
    alerts = [{
        "warehouse_id": "W1",
        "sku": "SKU-A",
        "available": 1,
        "threshold": 5,
        "forecast_7d": 5,
        "forecast_30d": 20,
        "forecast_date": "2029-12-31",
        "history_days": 30,
        "history_status": "observed",
        "forecast_method": demand_forecast.METHOD,
        "inventory_policy": "free_source_min_sum",
    }]
    low_stock_db.setattr(fulfillment, "stock_alerts", lambda db: [dict(row) for row in alerts])

    initial = persona._low_stock("supervisor")
    item = initial["items"][0]
    alert = item["alert"]
    assert alert["entity_id"] == "SKU-A"
    assert "manual_close" in alert["allowed_actions"]
    token = alert["evidence"]["condition_fingerprint"]
    before = _operational_state()

    closed = _action(alert["id"], token, reason="  Shortage reviewed; no replenishment requested  ")
    assert closed["status"] == "resolved"
    closure = closed["evidence"]["manual_closure"]
    assert closure["comment"] == "Shortage reviewed; no replenishment requested"
    assert closure["closed_by"] == "supervisor"
    assert closure["affected_alert"] == {"warehouse_id": "W1", "sku": "SKU-A"}
    assert closure["fingerprint"] == token
    assert "inventory_sync" not in closure
    assert _operational_state() == before

    assert persona._low_stock("supervisor")["items"] == []
    retained = persona._low_stock("supervisor", status="closed")["items"][0]["alert"]
    assert retained["id"] == alert["id"]
    assert retained["events"][-1]["action"] == "manual_close"
    assert retained["events"][-1]["reason"] == closure["comment"]
    assert retained["evidence"]["manual_closure"] == closure
    assert persona._low_stock("supervisor")["items"] == []
    with pytest.raises(HTTPException) as duplicate:
        _action(alert["id"], token)
    assert duplicate.value.status_code == 409

    # A new daily snapshot with identical stock/predictions refreshes evidence
    # but is not a new condition epoch and must not reopen acknowledgement.
    alerts[0]["forecast_date"] = "2030-01-01"
    assert persona._low_stock("supervisor")["items"] == []
    unchanged = persona._low_stock("supervisor", status="closed")["items"][0]["alert"]
    assert unchanged["evidence"]["condition_fingerprint"] == token
    assert unchanged["evidence"]["current_state"]["forecast_date"] == "2030-01-01"

    # A changed seven-day prediction is a changed condition and must reopen.
    alerts[0]["forecast_7d"] = alerts[0]["threshold"] = 6
    reopened = persona._low_stock("supervisor")["items"][0]["alert"]
    assert reopened["id"] == alert["id"]
    assert reopened["status"] == "open"
    assert reopened["recurrence_count"] == 1
    assert reopened["events"][-1]["action"] == "reopened"
    assert reopened["evidence"]["condition_fingerprint"] != token
    with pytest.raises(HTTPException) as stale:
        _action(reopened["id"], token)
    assert stale.value.status_code == 409
    assert _operational_state() == before


def test_aggregate_alert_recovery_resolves_history_and_same_condition_recurs(
    low_stock_db,
):
    alerts = [{"warehouse_id": "W1", "sku": "SKU-A", "available": 1, "threshold": 5}]
    low_stock_db.setattr(fulfillment, "stock_alerts", lambda db: [dict(row) for row in alerts])
    first = persona._low_stock("supervisor")["items"][0]["alert"]
    token = first["evidence"]["condition_fingerprint"]

    alerts.clear()
    assert persona._low_stock("supervisor")["items"] == []
    recovered = persona._low_stock("supervisor", status="closed")["items"][0]["alert"]
    assert recovered["id"] == first["id"]
    assert recovered["status"] == "resolved"
    assert recovered["recurrence_count"] == 0
    assert recovered["events"][-1]["action"] == "recovered"
    assert recovered["evidence"]["condition_recovered"] == {
        "at": "2030-01-01T00:00:00Z",
        "reason": "Low-stock condition is no longer active",
        "condition_fingerprint": token,
        "affected_alert": {"warehouse_id": "W1", "sku": "SKU-A"},
    }
    with pytest.raises(HTTPException) as stale_close:
        _action(first["id"], token)
    assert stale_close.value.status_code == 409

    alerts.append(
        {"warehouse_id": "W1", "sku": "SKU-A", "available": 1, "threshold": 5}
    )
    recurring = persona._low_stock("supervisor")["items"][0]["alert"]
    assert recurring["id"] == first["id"]
    assert recurring["status"] == "open"
    assert recurring["recurrence_count"] == 1
    assert recurring["evidence"]["condition_fingerprint"] == token
    assert "condition_recovered" not in recurring["evidence"]
    assert recurring["events"][-1]["action"] == "reopened"


def test_manually_closed_aggregate_reopens_after_recovery_epoch(low_stock_db):
    alerts = [{"warehouse_id": "W1", "sku": "SKU-A", "available": 1, "threshold": 5}]
    low_stock_db.setattr(fulfillment, "stock_alerts", lambda db: [dict(row) for row in alerts])
    first = persona._low_stock("supervisor")["items"][0]["alert"]
    token = first["evidence"]["condition_fingerprint"]
    _action(first["id"], token)

    alerts.clear()
    persona._low_stock("supervisor")
    recovered = persona._low_stock("supervisor", status="closed")["items"][0]["alert"]
    assert recovered["evidence"]["manual_closure"]["fingerprint"] == token
    assert recovered["evidence"]["condition_recovered"]["condition_fingerprint"] == token

    alerts.append(
        {"warehouse_id": "W1", "sku": "SKU-A", "available": 1, "threshold": 5}
    )
    recurring = persona._low_stock("supervisor")["items"][0]["alert"]
    assert recurring["id"] == first["id"]
    assert recurring["recurrence_count"] == 1
    assert recurring["evidence"]["condition_fingerprint"] == token
    assert "manual_closure" not in recurring["evidence"]


def test_replenishment_close_requires_comment_token_and_supervisor(low_stock_db):
    alerts = [{"warehouse_id": "W1", "sku": "SKU-A", "available": 1, "threshold": 5}]
    low_stock_db.setattr(fulfillment, "stock_alerts", lambda db: [dict(row) for row in alerts])
    alert = persona._low_stock("supervisor")["items"][0]["alert"]
    token = alert["evidence"]["condition_fingerprint"]

    with pytest.raises(HTTPException) as missing_token:
        _action(alert["id"], "", reason="reviewed")
    assert missing_token.value.status_code == 422
    with pytest.raises(HTTPException) as blank:
        _action(alert["id"], token, reason=" \t ")
    assert blank.value.status_code == 422
    with pytest.raises(HTTPException) as admin:
        _action(alert["id"], token, role="admin")
    assert admin.value.status_code == 403
    with pytest.raises(HTTPException) as fleet:
        _action(alert["id"], token, role="fleet")
    assert fleet.value.status_code == 403
    with pytest.raises(Exception):
        persona.InterventionAction(
            action="manual_close",
            reason="x" * 2001,
            evidence={"condition_fingerprint": token},
        )


def test_location_alert_close_preserves_inventory_and_remains_discoverable(low_stock_db):
    low_stock_db.setattr(fulfillment, "stock_alerts", lambda db: [])
    with fulfillment._read_db() as db:
        source = dict(fulfillment.inventory_rows(db)[0])
    add_replenishment(
        "INT-LOCATION",
        source["warehouse_id"],
        source["sku"],
        source["location"],
        title="Location shortage",
    )
    with fulfillment.db_transaction() as db:
        set_forecast_threshold(
            db,
            source["warehouse_id"],
            source["sku"],
            int(source["allocatable_qty"]) + 1,
        )
        row = db.execute(
            "SELECT * FROM persona_interventions WHERE id='INT-LOCATION'"
        ).fetchone()
        evidence = json.loads(row["evidence_json"])
        evidence["inventory_row_id"] = source["inventory_row_id"]
        evidence["condition_fingerprint"] = persona._current_location_low_stock_evidence(
            db, row
        )["condition_fingerprint"]
        db.execute(
            "UPDATE persona_interventions SET evidence_json=? WHERE id=?",
            (json.dumps(evidence), row["id"]),
        )

    issue = persona._low_stock("supervisor")["items"][0]["interventions"][0]
    before = _operational_state()
    closed = _action(issue["id"], issue["evidence"]["condition_fingerprint"])
    assert closed["status"] == "resolved"
    assert closed["evidence"]["manual_closure"]["affected_alert"]["location"] == source["location"]
    assert "inventory_sync" not in closed["evidence"]["manual_closure"]
    assert _operational_state() == before
    historical = persona._low_stock("supervisor", status="closed")["items"][0]
    assert historical["interventions"][0]["id"] == issue["id"]


def test_full_catalog_aggregate_evidence_uses_bulk_inventory_and_held_work(
    low_stock_db,
):
    alerts = [
        {
            "warehouse_id": f"W{index % 3}",
            "sku": f"SKU-{index:03d}",
            "available": index % 4,
            "threshold": 5,
        }
        for index in range(60)
    ]
    low_stock_db.setattr(fulfillment, "stock_alerts", lambda db: [dict(row) for row in alerts])
    original_inventory_rows = fulfillment.inventory_rows
    calls = 0

    def counted_inventory_rows(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_inventory_rows(*args, **kwargs)

    low_stock_db.setattr(fulfillment, "inventory_rows", counted_inventory_rows)
    low_stock_db.setattr(
        persona.persona_v2,
        "linked_held_work",
        lambda *args, **kwargs: pytest.fail("per-alert held-work query used"),
    )

    response = persona._low_stock("supervisor", limit=500)
    assert response["pagination"]["total"] == len(alerts)
    assert calls == 1


def test_detected_location_alert_token_closes_without_mutation(
    detected_low_stock_db,
):
    response = persona._low_stock("supervisor", limit=500)
    issue = next(
        intervention
        for item in response["items"]
        for intervention in item["interventions"]
        if intervention["evidence"].get("location")
    )
    token = issue["evidence"]["condition_fingerprint"]
    with fulfillment._read_db() as db:
        stored = db.execute(
            "SELECT * FROM persona_interventions WHERE id=?", (issue["id"],)
        ).fetchone()
        assert token == persona._current_location_low_stock_evidence(
            db, stored
        )["condition_fingerprint"]
    before = _operational_state()

    closed = _action(issue["id"], token, reason="Detector-backed location reviewed")
    assert closed["status"] == "resolved"
    assert closed["evidence"]["manual_closure"]["fingerprint"] == token
    assert _operational_state() == before

    active_ids = {
        intervention["id"]
        for item in persona._low_stock("supervisor", limit=500)["items"]
        for intervention in item["interventions"]
    }
    assert issue["id"] not in active_ids
    closed_ids = {
        intervention["id"]
        for item in persona._low_stock(
            "supervisor", limit=500, status="closed"
        )["items"]
        for intervention in item["interventions"]
    }
    assert issue["id"] in closed_ids


def test_legacy_detected_location_without_token_is_backfilled_before_close(
    detected_low_stock_db,
):
    response = persona._low_stock("supervisor", limit=500)
    issue = next(
        intervention
        for item in response["items"]
        for intervention in item["interventions"]
        if intervention["evidence"].get("location")
    )
    with fulfillment.db_transaction() as db:
        row = db.execute(
            "SELECT * FROM persona_interventions WHERE id=?", (issue["id"],)
        ).fetchone()
        evidence = json.loads(row["evidence_json"])
        evidence.pop("condition_fingerprint", None)
        db.execute(
            "UPDATE persona_interventions SET evidence_json=? WHERE id=?",
            (json.dumps(evidence), issue["id"]),
        )
        detection = db.execute(
            "SELECT fingerprint FROM persona_v2_detection_state WHERE id=1"
        ).fetchone()
        legacy_fingerprint = json.loads(detection["fingerprint"])
        legacy_fingerprint["format_version"] = 3
        db.execute(
            "UPDATE persona_v2_detection_state SET fingerprint=? WHERE id=1",
            (json.dumps(legacy_fingerprint, separators=(",", ":")),),
        )
        stale = db.execute(
            "SELECT * FROM persona_interventions WHERE id=?", (issue["id"],)
        ).fetchone()
        assert "manual_close" not in persona._intervention_json(
            db, stale, "supervisor"
        )["allowed_actions"]

    refreshed = persona._low_stock("supervisor", limit=500)
    upgraded = next(
        intervention
        for item in refreshed["items"]
        for intervention in item["interventions"]
        if intervention["id"] == issue["id"]
    )
    assert upgraded["evidence"]["condition_fingerprint"]
    assert "manual_close" in upgraded["allowed_actions"]


def test_location_threshold_recovery_stale_close_and_identical_recurrence(
    detected_low_stock_db,
):
    response = persona._low_stock("supervisor", limit=500)
    issue = next(
        intervention
        for item in response["items"]
        for intervention in item["interventions"]
        if intervention["evidence"].get("location")
    )
    token = issue["evidence"]["condition_fingerprint"]
    original_threshold = int(issue["evidence"]["forecast_7d"])
    forecast_sku = issue["evidence"]["sku"]

    with fulfillment.db_transaction() as db:
        set_forecast_threshold(
            db, issue["warehouse_id"], forecast_sku, 0
        )
    with pytest.raises(HTTPException) as stale:
        _action(issue["id"], token)
    assert stale.value.status_code == 409
    assert "no longer active" in stale.value.detail

    after_recovery = persona._low_stock("supervisor", limit=500)
    assert all(
        intervention["id"] != issue["id"]
        for item in after_recovery["items"]
        for intervention in item["interventions"]
    )
    recovered = next(
        intervention
        for item in persona._low_stock(
            "supervisor", limit=500, status="closed"
        )["items"]
        for intervention in item["interventions"]
        if intervention["id"] == issue["id"]
    )
    assert recovered["events"][-1]["action"] == "recovered"
    assert recovered["evidence"]["condition_recovered"]["condition_fingerprint"] == token

    with fulfillment.db_transaction() as db:
        set_forecast_threshold(
            db, issue["warehouse_id"], forecast_sku, original_threshold
        )
    recurring = next(
        intervention
        for item in persona._low_stock("supervisor", limit=500)["items"]
        for intervention in item["interventions"]
        if intervention["id"] == issue["id"]
    )
    assert recurring["recurrence_count"] == 1
    assert recurring["evidence"]["condition_fingerprint"] == token

    _action(recurring["id"], token)
    unchanged = persona._low_stock("supervisor", limit=500)
    assert all(
        intervention["id"] != issue["id"]
        for item in unchanged["items"]
        for intervention in item["interventions"]
    )

    with fulfillment.db_transaction() as db:
        set_forecast_threshold(db, issue["warehouse_id"], forecast_sku, 0)
    persona._low_stock("supervisor", limit=500)
    with fulfillment.db_transaction() as db:
        set_forecast_threshold(
            db, issue["warehouse_id"], forecast_sku, original_threshold
        )
    recurring_after_manual_close = next(
        intervention
        for item in persona._low_stock("supervisor", limit=500)["items"]
        for intervention in item["interventions"]
        if intervention["id"] == issue["id"]
    )
    assert recurring_after_manual_close["recurrence_count"] == 2
    assert recurring_after_manual_close["evidence"]["condition_fingerprint"] == token
    assert "manual_closure" not in recurring_after_manual_close["evidence"]


def test_location_context_uses_warehouse_sku_aggregate_and_other_location_recovers(
    detected_low_stock_db,
):
    with fulfillment.db_transaction() as db:
        original = db.execute(
            "SELECT * FROM inventory_snapshot ORDER BY id LIMIT 1"
        ).fetchone()
        assert original is not None
        warehouse, sku = original["warehouse_id"], original["sku"]
        db.execute(
            """INSERT INTO inventory_snapshot(
                 source_row_index,warehouse_id,sku,location,zone,inventory_status,
                 wms_qty,erp_qty,vision_qty,reserved_qty,external_reserved_qty,
                 picked_qty,completed_qty,weight_kg,revision,opening_discrepancy,
                 blocked_allocation,created_at,updated_at)
               SELECT (SELECT MAX(source_row_index)+1 FROM inventory_snapshot),
                 warehouse_id,sku,location||'-EXTRA',zone,inventory_status,
                 wms_qty,erp_qty,vision_qty,0,0,0,0,weight_kg,0,NULL,0,
                 created_at,updated_at
               FROM inventory_snapshot WHERE id=?""",
            (original["id"],),
        )
        rows = db.execute(
            "SELECT id FROM inventory_snapshot WHERE warehouse_id=? AND sku=? ORDER BY id",
            (warehouse, sku),
        ).fetchall()
        db.execute(
            """UPDATE inventory_snapshot
               SET wms_qty=3,erp_qty=3,vision_qty=3,revision=revision+1
               WHERE warehouse_id=? AND sku=?""",
            (warehouse, sku),
        )
        # Every location (3) is below this forecast, but their aggregate is
        # above it. Per-warehouse/SKU scope must therefore emit no shortage.
        threshold = len(rows) * 3 - 1
        set_forecast_threshold(db, warehouse, sku, threshold)

    initial = persona._low_stock("supervisor", limit=500)
    assert all(
        not (
            item["warehouse_id"] == warehouse
            and item["sku"] == sku
        )
        for item in initial["items"]
    )

    with fulfillment.db_transaction() as db:
        db.execute(
            """UPDATE inventory_snapshot
               SET wms_qty=1,erp_qty=1,vision_qty=1,revision=revision+1
               WHERE id=?""",
            (rows[0]["id"],),
        )
    shortage = next(
        item
        for item in persona._low_stock("supervisor", limit=500)["items"]
        if item["warehouse_id"] == warehouse and item["sku"] == sku
    )
    assert shortage["aggregate_alert"]["available"] == len(rows) * 3 - 2
    assert shortage["aggregate_alert"]["forecast_7d"] == threshold
    assert shortage["interventions"]
    assert all(
        intervention["evidence"]["available"] == len(rows) * 3 - 2
        for intervention in shortage["interventions"]
    )

    # Replenishing a different location restores aggregate equality and closes
    # every location-context intervention for this warehouse/SKU condition.
    with fulfillment.db_transaction() as db:
        db.execute(
            """UPDATE inventory_snapshot
               SET wms_qty=5,erp_qty=5,vision_qty=5,revision=revision+1
               WHERE id=?""",
            (rows[1]["id"],),
        )
    recovered = persona._low_stock("supervisor", limit=500)
    assert all(
        not (item["warehouse_id"] == warehouse and item["sku"] == sku)
        for item in recovered["items"]
    )
