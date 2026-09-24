"""Focused Control Tower v2 persona correction contract tests."""

from datetime import datetime, timezone
import asyncio
import json
import uuid
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI, HTTPException

import fulfillment_api as fulfillment
import persona_api as persona


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "persona-v2.sqlite")
    monkeypatch.setattr(
        fulfillment, "utc_now", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    fulfillment._init_db()
    persona._ensure_schema()


@pytest.fixture
def api_client(isolated_db):
    app = FastAPI()
    app.include_router(persona.router)
    return ASGIClient(app)


class ASGIResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return json.loads(self._body)


class ASGIClient:
    """Minimal real ASGI request harness; the project intentionally lacks httpx."""

    def __init__(self, app):
        self.app = app

    def get(self, path, *, params=None, headers=None):
        return self._request("GET", path, params=params, headers=headers)

    def post(self, path, *, params=None, headers=None, json=None):
        return self._request("POST", path, params=params, headers=headers, json_body=json)

    def _request(self, method, path, *, params=None, headers=None, json_body=None):
        async def invoke():
            body = (
                json.dumps(json_body).encode()
                if json_body is not None
                else b""
            )
            messages = []
            sent = False

            async def receive():
                nonlocal sent
                if sent:
                    return {"type": "http.disconnect"}
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}

            async def send(message):
                messages.append(message)

            normalized_headers = {
                key.lower(): value for key, value in (headers or {}).items()
            }
            if body:
                normalized_headers["content-type"] = "application/json"
                normalized_headers["content-length"] = str(len(body))
            await self.app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": method,
                    "scheme": "http",
                    "path": path,
                    "raw_path": path.encode(),
                    "query_string": urlencode(params or {}).encode(),
                    "headers": [
                        (key.encode(), value.encode())
                        for key, value in normalized_headers.items()
                    ],
                    "client": ("test", 1),
                    "server": ("testserver", 80),
                    "root_path": "",
                },
                receive,
                send,
            )
            start = next(message for message in messages if message["type"] == "http.response.start")
            response_body = b"".join(
                message.get("body", b"")
                for message in messages
                if message["type"] == "http.response.body"
            )
            return ASGIResponse(start["status"], response_body)

        return asyncio.run(invoke())


def act(item_id, action, role="supervisor", *, value=None, evidence=None):
    return persona.intervention_action(
        item_id,
        persona.InterventionAction(
            action=action,
            reason=f"test {action}",
            value=value,
            evidence=evidence,
        ),
        role,
    )


def inventory_item(row, kind="inventory_mismatch"):
    return persona.create_intervention(
        persona.InterventionCreate(
            kind=kind,
            warehouse_id=row["warehouse_id"],
            entity_id=f"{row['sku']}@{row['location']}",
            description="authoritative correction test",
        ),
        "supervisor",
    )


def internal_fleet_intervention(kind, warehouse_id, entity_id):
    """Seed internal fleet recovery history without using public manual creation."""
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
                warehouse_id,
                entity_id,
                f"{kind.replace('_', ' ').title()}: {entity_id}",
                "Internal fleet recovery fixture",
                "fleet",
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
        return persona._intervention_json(db, persona._fetch(db, intervention_id), "fleet")


def mismatch_with_two_equal(db):
    for row in fulfillment.inventory_rows(db):
        values = [row["wms_qty"], row["erp_qty"], row["vision_qty"]]
        if len(set(values)) == 2:
            for source in ("wms", "erp", "vision"):
                others = [
                    row[f"{name}_qty"]
                    for name in ("wms", "erp", "vision")
                    if name != source
                ]
                if others[0] == others[1] and row[f"{source}_qty"] != others[0]:
                    return row, source, others[0]
    pytest.skip("fixture has no single-source discrepancy")


def test_source_specific_inventory_correction_revision_and_recurrence(isolated_db):
    with fulfillment._read_db() as db:
        row, source, corrected_quantity = mismatch_with_two_equal(db)
        reserved_before = row["reserved_qty"]
        picked_before = row["picked_qty"]
    persona.workspace("supervisor")
    with fulfillment._read_db() as db:
        detected_id = db.execute(
            "SELECT id FROM persona_interventions WHERE dedupe_key=?",
            (
                f"v2:inventory_mismatch:{row['warehouse_id']}:"
                f"{row['sku']}@{row['location']}",
            ),
        ).fetchone()["id"]
    item = persona.get_intervention(detected_id, "supervisor")
    act(item["id"], "investigate")
    act(
        item["id"],
        "propose",
        value={
            "source": source,
            "quantity": corrected_quantity,
            "basis": "free",
            "revision": row["revision"],
            "location": row["location"],
        },
        evidence={
            "count_method": "cycle_count",
            "verified_by": "supervisor",
            "units": "each",
        },
    )
    approved = act(item["id"], "approve")
    assert approved["proposed_action"]["after"][f"{source}_qty"] == corrected_quantity
    with fulfillment._read_db() as db:
        after = next(
            value
            for value in fulfillment.inventory_rows(
                db, row["warehouse_id"], row["sku"]
            )
            if value["inventory_row_id"] == row["inventory_row_id"]
        )
    assert after["reserved_qty"] == reserved_before
    assert after["picked_qty"] == picked_before
    resolved = act(
        item["id"],
        "verify",
        evidence={
            "verified_by": "supervisor",
            "current_observations": {
                "revision": after["revision"],
                "basis": "free",
                "wms_qty": after["wms_qty"],
                "erp_qty": after["erp_qty"],
                "vision_qty": after["vision_qty"],
                "attestation": "Current modeled source observations reviewed",
            },
        },
    )
    assert resolved["status"] == "resolved"

    # A later authoritative change recreating disagreement reopens the same
    # source-identity issue rather than silently leaving it dismissed.
    with fulfillment.db_transaction() as db:
        fulfillment.correct_inventory(
            db,
            row["inventory_row_id"],
            {f"{source}_qty": corrected_quantity + 1},
            "free",
            after["revision"],
            "recurrence test",
            "test",
        )
    # Detection is refresh-driven.
    persona.workspace("supervisor")
    reopened = persona.get_intervention(item["id"], "supervisor")
    assert reopened["status"] == "open"
    assert reopened["recurrence_count"] == 1


def test_total_on_hand_conversion_and_stale_revision(isolated_db):
    with fulfillment.db_transaction() as db:
        row = fulfillment.inventory_rows(db)[0]
        db.execute(
            "UPDATE inventory_snapshot SET reserved_qty=2,picked_qty=1 WHERE id=?",
            (row["inventory_row_id"],),
        )
    with fulfillment._read_db() as db:
        row = fulfillment.inventory_rows(
            db, row["warehouse_id"], row["sku"]
        )[0]
    item = inventory_item(row, "replenishment_alert")
    act(item["id"], "investigate")
    proposed = act(
        item["id"],
        "propose",
        value={
            "source": "wms",
            "quantity": 12,
            "basis": "total",
            "revision": row["revision"],
            "location": row["location"],
        },
        evidence={
            "count_method": "receiving_observation",
            "verified_by": "supervisor",
            "units": "each",
        },
    )
    assert proposed["proposed_action"]["basis"] == "total_on_hand"
    approved = act(item["id"], "approve")
    assert approved["proposed_action"]["after"]["wms_qty"] == 9
    stale = inventory_item(row)
    act(stale["id"], "investigate")
    with pytest.raises(HTTPException) as caught:
        act(
            stale["id"],
            "propose",
            value={
                "source": "erp",
                "quantity": 12,
                "basis": "free",
                "revision": row["revision"],
                "location": row["location"],
            },
            evidence={
                "count_method": "stale",
                "verified_by": "supervisor",
                "units": "each",
            },
        )
    assert caught.value.status_code == 409


def test_held_null_warehouse_makes_inventory_issue_p1(isolated_db):
    with fulfillment._read_db() as db:
        stock = fulfillment.inventory_rows(db)[0]
    fulfillment.create_order(
        fulfillment.OrderInput(
            warehouse_id=None,
            priority="standard",
            lines=[
                fulfillment.OrderLineInput(
                    sku=stock["sku"], quantity=10**7
                )
            ],
            request_id=str(uuid.uuid4()),
            source_order_id=f"FBZ-{uuid.uuid4()}",
            order_service="Same_Day",
            order_source="fde_bazaar",
            order_created_at="2030-01-01T00:00:00Z",
        )
    )
    workspace = persona.workspace("supervisor")
    linked = [
        issue
        for issue in workspace["issues"]
        if issue["kind"] in {"inventory_mismatch", "replenishment_alert"}
        and issue["evidence"].get("sku") == stock["sku"]
        and issue["linked_work"]
    ]
    assert linked
    assert all(issue["priority"] == "P1" for issue in linked)


def test_fleet_workspace_excludes_inventory_and_unsafe_verify_is_rejected(isolated_db):
    robot = next(
        row
        for row in fulfillment.source_rows("robots")
        if row.get("health_status") != "HEALTHY"
    )
    item = internal_fleet_intervention(
        "fleet_readiness", robot["warehouse_id"], robot["robot_id"]
    )
    act(item["id"], "investigate", "fleet")
    act(
        item["id"],
        "propose",
        "fleet",
        value={
            "entity_type": "robot",
            "field": "connectivity",
            "value": "ONLINE",
            "revision": 0,
        },
        evidence={"source": "modeled fleet registry", "verified_by": "fleet"},
    )
    act(item["id"], "handoff", "fleet")
    act(item["id"], "approve")
    with pytest.raises(HTTPException) as caught:
        act(
            item["id"],
            "verify",
            evidence={
                "verified_by": "supervisor",
                "observed_entity_id": robot["robot_id"],
                "observation_source": "modeled fleet registry",
            },
        )
    assert caught.value.status_code == 409
    fleet = persona.workspace("fleet")
    assert all(issue["kind"] not in {"inventory_mismatch", "replenishment_alert"}
               for issue in fleet["issues"])


def test_v2_running_hold_pauses_without_releasing_accepted_inventory(isolated_db):
    with fulfillment._read_db() as db:
        stock = next(
            row
            for row in fulfillment.inventory_rows(db)
            if row["allocatable_qty"] > 0 and row.get("weight_kg")
        )
    order = fulfillment.create_order(
        fulfillment.OrderInput(
            warehouse_id=None,
            priority="standard",
            lines=[fulfillment.OrderLineInput(sku=stock["sku"], quantity=1)],
            request_id=str(uuid.uuid4()),
            source_order_id=f"FBZ-{uuid.uuid4()}",
            order_service="Same_Day",
            order_source="fde_bazaar",
            order_created_at="2030-01-01T00:00:00Z",
        )
    )
    with fulfillment.db_transaction() as db:
        task = db.execute(
            "SELECT tasks.*,sub_orders.warehouse_id AS site FROM tasks "
            "JOIN sub_orders ON sub_orders.id=tasks.sub_order_id "
            "WHERE tasks.order_id=? AND tasks.stage='pick' LIMIT 1",
            (order["id"],),
        ).fetchone()
        robot = next(
            item
            for item in fulfillment.source_rows("robots")
            if item["warehouse_id"] == task["site"]
        )
        db.execute(
            "UPDATE tasks SET status='running',resource_id=?,resource_type='robot',"
            "started_at='2030-01-01T00:00:00Z',due_at='2030-01-01T00:00:45Z' WHERE id=?",
            (robot["robot_id"], task["id"]),
        )
    with fulfillment._read_db() as db:
        running = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
        before = db.execute(
            "SELECT SUM(reserved_qty) AS reserved FROM inventory_snapshot"
        ).fetchone()["reserved"]
        movement_count = db.execute(
            "SELECT COUNT(*) AS n FROM inventory_movements WHERE order_id=?",
            (order["id"],),
        ).fetchone()["n"]
    hold = internal_fleet_intervention(
        "fleet_readiness", robot["warehouse_id"], robot["robot_id"]
    )
    act(hold["id"], "investigate", "fleet")
    act(
        hold["id"],
        "propose",
        "fleet",
        value="hold",
        evidence={"finding": "unsafe", "source": "modeled evidence"},
    )
    act(hold["id"], "handoff", "fleet")
    act(hold["id"], "approve")
    with fulfillment._read_db() as db:
        assert db.execute(
            "SELECT status FROM tasks WHERE id=?", (running["id"],)
        ).fetchone()["status"] == "paused"
        assert db.execute(
            "SELECT SUM(reserved_qty) AS reserved FROM inventory_snapshot"
        ).fetchone()["reserved"] == before
        assert db.execute(
            "SELECT COUNT(*) AS n FROM inventory_movements WHERE order_id=?",
            (order["id"],),
        ).fetchone()["n"] == movement_count


def test_api_fleet_issue_direct_atomic_correction_flow(api_client):
    fleet_headers = {"X-Demo-Persona": "fleet"}
    supervisor_headers = {"X-Demo-Persona": "supervisor"}
    workspace = api_client.get(
        "/api/personas/fleet/issues",
        params={"limit": 100},
        headers=fleet_headers,
    )
    assert workspace.status_code == 200
    issue = next(
        item
        for item in workspace.json()["items"]
        if item["kind"] == "fleet_readiness"
        and any(
            context["entity_type"] == "maintenance"
            and context["values"]["cmms_status"] in {"OPEN", "IN_PROGRESS"}
            for context in item["contexts"]
        )
    )
    contexts = []
    for context in issue["contexts"]:
        values = dict(context["values"])
        if context["entity_type"] == "robot":
            values.update(
                health_status="HEALTHY",
                safety_cert_status="VALID",
                connectivity="ONLINE",
            )
        else:
            values.update(cmms_status="CLOSED", fleet_availability="AVAILABLE")
        contexts.append(
            {
                "entity_type": context["entity_type"],
                "entity_id": context["entity_id"],
                "revision": context["revision"],
                "values": values,
            }
        )
    verified = api_client.post(
        f"/api/personas/fleet/issues/{issue['id']}/repair",
        headers=fleet_headers,
        json={"fingerprint": issue["fingerprint"], "contexts": contexts},
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "resolved"
    assert api_client.get(
        "/api/personas/fleet/issues", headers=supervisor_headers
    ).status_code == 403


def test_api_zero_revision_inventory_issue_requires_current_observations(api_client):
    headers = {"X-Demo-Persona": "supervisor"}
    # Trigger full-catalog detection, then select the exact persisted issue
    # without depending on its position in a paginated response.
    assert api_client.get(
        "/api/personas/workspace", headers=headers
    ).status_code == 200
    with fulfillment._read_db() as db:
        row, source, quantity = mismatch_with_two_equal(db)
        issue_id = db.execute(
            "SELECT id FROM persona_interventions WHERE dedupe_key=?",
            (
                f"v2:inventory_mismatch:{row['warehouse_id']}:"
                f"{row['sku']}@{row['location']}",
            ),
        ).fetchone()["id"]
    detail_url = f"/api/personas/interventions/{issue_id}"
    action_url = detail_url + "/actions"
    issue = api_client.get(detail_url, headers=headers).json()
    assert issue["evidence"]["current_state"]["revision"] == 0
    assert api_client.post(
        action_url,
        headers=headers,
        json={"action": "investigate", "reason": "Review source discrepancy"},
    ).status_code == 200
    value = {
        "source": source,
        "quantity": quantity,
        "basis": "free",
        "revision": 0,
        "location": row["location"],
    }
    missing = api_client.post(
        action_url,
        headers=headers,
        json={
            "action": "propose",
            "reason": "Incomplete evidence",
            "evidence": {"count_method": "cycle_count"},
            "value": value,
        },
    )
    assert missing.status_code == 422
    proposed = api_client.post(
        action_url,
        headers=headers,
        json={
            "action": "propose",
            "reason": "Correct one observed source",
            "evidence": {
                "count_method": "cycle_count",
                "verified_by": "inventory-lead",
                "units": "each",
            },
            "value": value,
        },
    )
    assert proposed.status_code == 200
    assert proposed.json()["proposed_action"]["revision"] == 0
    approved = api_client.post(
        action_url,
        headers=headers,
        json={"action": "approve", "reason": "Approve source correction"},
    )
    assert approved.status_code == 200
    after = approved.json()["proposed_action"]["after"]
    missing_verify = api_client.post(
        action_url,
        headers=headers,
        json={
            "action": "verify",
            "reason": "Missing current observations",
            "evidence": {"verified_by": "operations-supervisor"},
        },
    )
    assert missing_verify.status_code == 422
    verified = api_client.post(
        action_url,
        headers=headers,
        json={
            "action": "verify",
            "reason": "Attest current effective free observations",
            "evidence": {
                "verified_by": "operations-supervisor",
                "current_observations": {
                    "revision": after["revision"],
                    "basis": "free",
                    "wms_qty": after["wms_qty"],
                    "erp_qty": after["erp_qty"],
                    "vision_qty": after["vision_qty"],
                    "attestation": "Current source observations reviewed",
                },
            },
        },
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "resolved"


def test_api_verify_cannot_clear_unmapped_legacy_opening_anomaly(api_client):
    headers = {"X-Demo-Persona": "supervisor"}
    with fulfillment.db_transaction() as db:
        row = fulfillment.inventory_rows(db)[0]
        db.execute(
            "UPDATE inventory_snapshot SET blocked_allocation=1,"
            "opening_discrepancy='Legacy reservation is not reconcilable' WHERE id=?",
            (row["inventory_row_id"],),
        )
    created = api_client.post(
        "/api/personas/interventions",
        headers=headers,
        json={
            "kind": "inventory_mismatch",
            "warehouse_id": row["warehouse_id"],
            "entity_id": f"{row['sku']}@{row['location']}",
            "description": "Unmapped legacy anomaly cannot be attested away",
        },
    )
    assert created.status_code == 200
    action_url = (
        f"/api/personas/interventions/{created.json()['id']}/actions"
    )
    assert api_client.post(
        action_url,
        headers=headers,
        json={"action": "investigate", "reason": "Inspect legacy anomaly"},
    ).status_code == 200
    assert api_client.post(
        action_url,
        headers=headers,
        json={
            "action": "propose",
            "reason": "Record current WMS source",
            "evidence": {
                "count_method": "cycle_count",
                "verified_by": "inventory-lead",
                "units": "each",
            },
            "value": {
                "source": "wms",
                "quantity": row["wms_qty"],
                "basis": "free",
                "revision": row["revision"],
                "location": row["location"],
            },
        },
    ).status_code == 200
    approved = api_client.post(
        action_url,
        headers=headers,
        json={"action": "approve", "reason": "Approve recorded observation"},
    )
    after = approved.json()["proposed_action"]["after"]
    protected = after["reserved_qty"] + after["picked_qty"]
    rejected = api_client.post(
        action_url,
        headers=headers,
        json={
            "action": "verify",
            "reason": "Attempt mapped opening attestation",
            "evidence": {
                "verified_by": "operations-supervisor",
                "current_observations": {
                    "revision": after["revision"],
                    "basis": "total_on_hand",
                    "wms_qty": after["wms_qty"] + protected,
                    "erp_qty": after["erp_qty"] + protected,
                    "vision_qty": after["vision_qty"] + protected,
                    "attestation": "Current totals observed",
                },
            },
        },
    )
    assert rejected.status_code == 409
    with fulfillment._read_db() as db:
        persisted = db.execute(
            "SELECT blocked_allocation,opening_discrepancy "
            "FROM inventory_snapshot WHERE id=?",
            (row["inventory_row_id"],),
        ).fetchone()
    assert persisted["blocked_allocation"] == 1
    assert "Legacy reservation" in persisted["opening_discrepancy"]