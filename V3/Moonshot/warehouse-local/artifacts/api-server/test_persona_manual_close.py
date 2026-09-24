"""Isolated ASGI contract tests for manual inventory mismatch closure."""

import asyncio
from datetime import datetime, timezone
import json
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI

import fulfillment_api as fulfillment
import persona_api as persona


class Client:
    def __init__(self, app):
        self.app = app

    def request(self, method, path, *, role="supervisor", body=None):
        async def invoke():
            encoded = json.dumps(body).encode() if body is not None else b""
            messages = []
            sent = False

            async def receive():
                nonlocal sent
                if sent:
                    return {"type": "http.disconnect"}
                sent = True
                return {"type": "http.request", "body": encoded, "more_body": False}

            async def send(message):
                messages.append(message)

            headers = [(b"x-demo-persona", role.encode())]
            if encoded:
                headers.extend(
                    [(b"content-type", b"application/json"),
                     (b"content-length", str(len(encoded)).encode())]
                )
            await self.app(
                {
                    "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                    "method": method, "scheme": "http", "path": path,
                    "raw_path": path.encode(), "query_string": urlencode({}).encode(),
                    "headers": headers, "client": ("test", 1), "server": ("test", 80),
                    "root_path": "",
                },
                receive,
                send,
            )
            start = next(item for item in messages if item["type"] == "http.response.start")
            response = b"".join(
                item.get("body", b"")
                for item in messages if item["type"] == "http.response.body"
            )
            return start["status"], json.loads(response)

        return asyncio.run(invoke())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "manual-close.sqlite")
    monkeypatch.setattr(
        fulfillment, "utc_now", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    fulfillment._init_db()
    persona._ensure_schema()
    app = FastAPI()
    app.include_router(persona.router)
    return Client(app)


def mismatch(client):
    status, workspace = client.request("GET", "/api/personas/workspace")
    assert status == 200
    return next(item for item in workspace["issues"] if item["kind"] == "inventory_mismatch")


def close(client, item, comment="Reviewed and corrected in upstream WMS"):
    return client.request(
        "POST",
        f"/api/personas/interventions/{item['id']}/actions",
        body={"action": "manual_close", "reason": comment},
    )


def inventory_state():
    with fulfillment._read_db() as db:
        quantities = [
            tuple(row)
            for row in db.execute(
                "SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
                "FROM inventory_snapshot ORDER BY id"
            )
        ]
        corrections = db.execute("SELECT COUNT(*) AS n FROM inventory_corrections").fetchone()["n"]
    return quantities, corrections


def test_close_syncs_exact_row_audits_and_stays_closed_on_unchanged_poll(client):
    item = mismatch(client)
    assert "manual_close" in item["allowed_actions"]
    row_id = item["evidence"]["inventory_row_id"]
    with fulfillment.db_transaction() as db:
        db.execute(
            "UPDATE inventory_snapshot SET wms_qty=3,erp_qty=9,vision_qty=5,"
            "reserved_qty=4,picked_qty=2,blocked_allocation=1,"
            "opening_discrepancy='preserve safety',revision=revision+1 WHERE id=?",
            (row_id,),
        )
        before_other = [
            tuple(row)
            for row in db.execute(
                "SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
                "FROM inventory_snapshot WHERE id<>? ORDER BY id",
                (row_id,),
            )
        ]
    status, closed = close(client, item, "  Upstream cycle count reviewed and corrected  ")
    assert status == 200
    closure = closed["evidence"]["manual_closure"]
    assert closed["status"] == "resolved"
    assert closure["comment"] == "Upstream cycle count reviewed and corrected"
    assert closure["closed_by"] == "supervisor"
    assert closure["at"] == "2030-01-01T00:00:00Z"
    assert closure["fingerprint"]
    assert closure["inventory_sync"] == [
        {
            "inventory_row_id": row_id,
            "location": item["evidence"]["location"],
            "before": {"wms_qty": 3, "erp_qty": 9, "vision_qty": 5},
            "after": {"wms_qty": 9, "erp_qty": 9, "vision_qty": 9},
        }
    ]
    assert {
        key: closed["current_state"][key]
        for key in ("wms_qty", "erp_qty", "vision_qty", "reserved_qty", "picked_qty")
    } == {
        "wms_qty": 9, "erp_qty": 9, "vision_qty": 9, "reserved_qty": 4, "picked_qty": 2
    }
    assert closed["current_state"]["blocked_allocation"] == 1
    assert closed["current_state"]["opening_discrepancy"] == "preserve safety"
    assert closed["events"][-1]["action"] == "manual_close"
    assert closed["events"][-1]["details"]["inventory_sync"] == closure["inventory_sync"]

    status, fetched = client.request(
        "GET", f"/api/personas/interventions/{item['id']}"
    )
    assert status == 200
    assert fetched["evidence"]["manual_closure"] == closure
    status, audit = client.request("GET", "/api/personas/audit", role="admin")
    assert status == 200
    audit_event = next(
        event
        for event in audit["events"]
        if event["entity_id"] == item["id"] and event["action"] == "manual_close"
    )
    assert audit_event["reason"] == closure["comment"]
    assert audit_event["details"]["inventory_sync"] == closure["inventory_sync"]

    with fulfillment.db_transaction() as db:
        stored = dict(db.execute("SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)).fetchone())
        assert (stored["wms_qty"], stored["erp_qty"], stored["vision_qty"]) == (9, 9, 9)
        assert (stored["reserved_qty"], stored["picked_qty"]) == (4, 2)
        assert stored["blocked_allocation"] == 1
        correction = db.execute(
            "SELECT * FROM inventory_corrections WHERE inventory_row_id=?", (row_id,)
        ).fetchone()
        assert correction["basis"] == "free"
        assert correction["actor"] == "persona-supervisor"
        assert json.loads(correction["before_json"])["erp_qty"] == 9
        assert json.loads(correction["after_json"])["wms_qty"] == 9
        assert [
            tuple(row)
            for row in db.execute(
                "SELECT id,wms_qty,erp_qty,vision_qty,reserved_qty,picked_qty "
                "FROM inventory_snapshot WHERE id<>? ORDER BY id",
                (row_id,),
            )
        ] == before_other
    for _ in range(2):
        status, workspace = client.request("GET", "/api/personas/workspace")
        assert status == 200
        retained = next(row for row in workspace["interventions"] if row["id"] == item["id"])
        assert retained["status"] == "resolved"
        assert retained["evidence"]["manual_closure"] == closure
    after_first_close = inventory_state()
    status, _ = close(client, item, "repeat")
    assert status == 409
    assert inventory_state() == after_first_close


def test_blank_comment_rejected(client):
    item = mismatch(client)
    status, response = close(client, item, " \t ")
    assert status == 422
    assert "comment is required" in response["detail"]


def test_role_and_kind_rejection(client):
    item = mismatch(client)
    status, _ = client.request(
        "POST", f"/api/personas/interventions/{item['id']}/actions", role="fleet",
        body={"action": "manual_close", "reason": "reviewed"},
    )
    assert status == 403

    status, created = client.request(
        "POST", "/api/personas/interventions",
        body={
            "kind": "priority_override", "warehouse_id": "DC-01",
            "entity_id": "ORDER-X", "description": "manual issue",
        },
    )
    assert status == 200
    status, _ = client.request(
        "POST", f"/api/personas/interventions/{created['id']}/actions",
        body={"action": "manual_close", "reason": "reviewed"},
    )
    assert status == 409
    status, _ = close(client, item, "reviewed by admin")
    assert status == 200
    status, _ = client.request(
        "POST", f"/api/personas/interventions/{item['id']}/actions", role="admin",
        body={"action": "manual_close", "reason": "admin"},
    )
    assert status == 403


def test_changed_source_condition_reopens(client):
    item = mismatch(client)
    status, closed = close(client, item)
    assert status == 200
    old_fingerprint = closed["evidence"]["manual_closure"]["fingerprint"]
    with fulfillment.db_transaction() as db:
        db.execute(
            "UPDATE inventory_snapshot SET vision_qty=vision_qty+1,revision=revision+1,"
            "updated_at=? WHERE id=?",
            ("2030-01-01T00:02:00Z", item["evidence"]["inventory_row_id"]),
        )
    status, workspace = client.request("GET", "/api/personas/workspace")
    assert status == 200
    reopened = next(row for row in workspace["interventions"] if row["id"] == item["id"])
    assert reopened["status"] == "open"
    assert "manual_closure" not in reopened["evidence"]
    assert reopened["recurrence_count"] == 1
    assert reopened["events"][-1]["action"] == "reopened"
    assert old_fingerprint


def test_vision_highest_is_used_and_no_work_is_recovered(client):
    item = mismatch(client)
    row_id = item["evidence"]["inventory_row_id"]
    with fulfillment.db_transaction() as db:
        db.execute(
            "UPDATE inventory_snapshot SET wms_qty=2,erp_qty=4,vision_qty=11,"
            "reserved_qty=3,picked_qty=1,revision=revision+1 WHERE id=?",
            (row_id,),
        )
        work = [
            tuple(row)
            for row in db.execute(
                "SELECT id,status FROM orders ORDER BY id"
            )
        ], [
            tuple(row)
            for row in db.execute(
                "SELECT id,status FROM tasks ORDER BY id"
            )
        ]
    status, closed = close(client, item)
    assert status == 200
    assert closed["evidence"]["manual_closure"]["inventory_sync"][0]["after"] == {
        "wms_qty": 11, "erp_qty": 11, "vision_qty": 11
    }
    with fulfillment._read_db() as db:
        row = db.execute("SELECT * FROM inventory_snapshot WHERE id=?", (row_id,)).fetchone()
        assert (row["reserved_qty"], row["picked_qty"]) == (3, 1)
        assert work == (
            [tuple(row) for row in db.execute("SELECT id,status FROM orders ORDER BY id")],
            [tuple(row) for row in db.execute("SELECT id,status FROM tasks ORDER BY id")],
        )


def test_historical_locationless_issue_uses_independent_per_row_max(client):
    with fulfillment.db_transaction() as db:
        grouped = db.execute(
            "SELECT warehouse_id,sku FROM inventory_snapshot "
            "GROUP BY warehouse_id,sku HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        if not grouped:
            grouped = db.execute(
                "SELECT warehouse_id,sku,location FROM inventory_snapshot ORDER BY id LIMIT 1"
            ).fetchone()
            other = db.execute(
                "SELECT id FROM inventory_snapshot WHERE location<>? ORDER BY id LIMIT 1",
                (grouped["location"],),
            ).fetchone()
            assert other is not None
            db.execute(
                "UPDATE inventory_snapshot SET warehouse_id=?,sku=? WHERE id=?",
                (grouped["warehouse_id"], grouped["sku"], other["id"]),
            )
        rows = db.execute(
            "SELECT id FROM inventory_snapshot WHERE warehouse_id=? AND sku=? ORDER BY id",
            (grouped["warehouse_id"], grouped["sku"]),
        ).fetchall()
        expected = {}
        for index, row in enumerate(rows):
            values = (index + 1, index + 4, index + 2)
            expected[row["id"]] = max(values)
            db.execute(
                "UPDATE inventory_snapshot SET wms_qty=?,erp_qty=?,vision_qty=?,revision=revision+1 "
                "WHERE id=?",
                (*values, row["id"]),
            )
    status, created = client.request(
        "POST",
        "/api/personas/interventions",
        body={
            "kind": "inventory_mismatch",
            "warehouse_id": grouped["warehouse_id"],
            "entity_id": grouped["sku"],
            "description": "historical locationless mismatch",
            "evidence": {"sku": grouped["sku"]},
        },
    )
    assert status == 200
    status, closed = close(client, created)
    assert status == 200
    sync = closed["evidence"]["manual_closure"]["inventory_sync"]
    assert {entry["inventory_row_id"] for entry in sync} == set(expected)
    assert {
        entry["inventory_row_id"]: entry["after"]["wms_qty"] for entry in sync
    } == expected
    with fulfillment._read_db() as db:
        for row_id, quantity in expected.items():
            row = db.execute(
                "SELECT wms_qty,erp_qty,vision_qty FROM inventory_snapshot WHERE id=?",
                (row_id,),
            ).fetchone()
            assert tuple(row) == (quantity, quantity, quantity)


def test_closure_failure_rolls_back_inventory_and_correction(client, monkeypatch):
    item = mismatch(client)
    before = inventory_state()

    def fail_event(*args, **kwargs):
        raise RuntimeError("injected closure failure")

    monkeypatch.setattr(persona, "_add_event", fail_event)
    with pytest.raises(RuntimeError, match="injected closure failure"):
        close(client, item)
    assert inventory_state() == before
    with fulfillment._read_db() as db:
        assert db.execute(
            "SELECT status FROM persona_interventions WHERE id=?", (item["id"],)
        ).fetchone()["status"] == "open"