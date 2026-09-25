"""Focused Bazaar tests use isolated SQLite files and fake HTTP only."""

from datetime import datetime, timezone
import json
import sqlite3
import hashlib
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import bazaar_api as bazaar


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(bazaar, "DB_PATH", tmp_path / "bazaar.sqlite")
    monkeypatch.setattr(
        bazaar, "utc_now", lambda: datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(bazaar, "_catalog_cache", None)
    records = {}
    calls = {"catalog": 0, "post": 0}

    def fake_http(method, path, payload=None, timeout=4):
        if path == "/catalog":
            calls["catalog"] += 1
            return {
                "warehouses": [
                    {"warehouse_id": "DC-01", "region": "NA", "country": "One"},
                    {"warehouse_id": "DC-02", "region": "APAC", "country": "Two"},
                ],
                "skus": [
                    {"sku": "SKU-1", "description": "First"},
                    {"sku": "SKU-2", "description": "Second"},
                    {"sku": "SKU-3", "description": "Third"},
                ],
            }
        if method == "POST":
            calls["post"] += 1
            current = records.setdefault(
                payload["request_id"],
                {
                    "id": f"FUL-{uuid.uuid4()}",
                    "status": "planned",
                    "issues": [],
                    "payload": payload,
                },
            )
            return current
        order_id = path.rsplit("/", 1)[-1]
        return next(value for value in records.values() if value["id"] == order_id)

    monkeypatch.setattr(bazaar, "request_json", fake_http)
    bazaar._init_db()
    return records, calls


def payload(service="Same_Day", request_id=None, warehouse_id="DC-01"):
    return bazaar.BazaarOrderInput(
        warehouse_id=warehouse_id,
        service=service,
        lines=[
            bazaar.BazaarLineInput(sku="SKU-1", quantity=2),
            bazaar.BazaarLineInput(sku="SKU-2", quantity=3),
        ],
        request_id=request_id or str(uuid.uuid4()),
    )


def test_complete_catalog_is_normalized_and_cached_once(isolated):
    _, calls = isolated
    first = bazaar.catalog()
    second = bazaar.catalog()
    assert len(first["warehouses"]) == 2
    assert len(first["skus"]) == 3
    assert first == second
    assert calls["catalog"] == 1


@pytest.mark.parametrize(
    "service,priority,ship_by",
    [
        ("Same_Day", "urgent", "2030-01-01T18:00:00Z"),
        ("Next_Day", "high", "2030-01-02T00:00:00Z"),
        ("Standard", "standard", "2030-01-02T12:00:00Z"),
    ],
)
def test_multisku_all_services_ids_and_metadata(isolated, service, priority, ship_by):
    records, _ = isolated
    order, created = bazaar.create_order(payload(service))
    assert created
    assert order["id"].startswith("FBZ-")
    assert order["priority"] == priority
    assert order["ship_by"] == ship_by
    assert order["delivery_status"] == "sent"
    delivered = next(iter(records.values()))["payload"]
    assert delivered["source_order_id"] == order["id"]
    assert delivered["order_service"] == service
    assert delivered["order_source"] == "fde_bazaar"
    assert delivered["order_created_at"] == order["created_at"]
    assert delivered["warehouse_id"] == "DC-01"
    assert len(delivered["lines"]) == 2


def test_selected_warehouse_is_preserved(isolated):
    records, _ = isolated
    legacy = payload()
    legacy.warehouse_id = "DC-02"
    order, created = bazaar.create_order(legacy)
    assert created
    assert order["warehouse_id"] == "DC-02"
    assert next(iter(records.values()))["payload"]["warehouse_id"] == "DC-02"


@pytest.mark.parametrize("warehouse_id", [None, "", "   ", "UNKNOWN"])
def test_new_order_requires_known_nonblank_warehouse(isolated, warehouse_id):
    request = payload(warehouse_id=warehouse_id)
    with pytest.raises(HTTPException) as error:
        bazaar.create_order(request)
    assert error.value.status_code == 422
    with bazaar._read_db() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


def test_legacy_missing_warehouse_request_replays_before_catalog_validation(
    isolated, monkeypatch
):
    request = payload(warehouse_id=None)
    fingerprint = bazaar._fingerprint(request)
    order_id = "FBZ-legacy"
    stamp = "2029-12-01T00:00:00Z"
    with bazaar._tx() as db:
        db.execute(
            """INSERT INTO orders(
                 id,warehouse_id,service,request_id,fingerprint,ship_by,priority,
                 delivery_status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,'sent',?,?)""",
            (
                order_id, "", request.service, request.request_id, fingerprint,
                "2029-12-02T00:00:00Z", "urgent", stamp, stamp,
            ),
        )
        db.executemany(
            "INSERT INTO order_lines(order_id,sku,quantity,position) VALUES (?,?,?,?)",
            [
                (order_id, line.sku, line.quantity, position)
                for position, line in enumerate(request.lines)
            ],
        )
        db.execute(
            """INSERT INTO outbox(order_id,payload_json,status,permanent)
               VALUES (?,'{}','sent',0)""",
            (order_id,),
        )

    monkeypatch.setattr(
        bazaar,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            bazaar.RemoteError("catalog unavailable")
        ),
    )
    monkeypatch.setattr(bazaar, "_catalog_cache", None)
    replay, created = bazaar.create_order(request)
    assert not created
    assert replay["id"] == order_id
    assert replay["warehouse_id"] is None


def test_historical_missing_warehouse_outbox_delivers_after_upgrade(isolated):
    records, calls = isolated
    request = payload(warehouse_id=None)
    order_id = "FBZ-historical-pending"
    stamp = "2029-12-01T00:00:00Z"
    downstream = {
        "priority": "urgent",
        "ship_by": "2029-12-01T06:00:00Z",
        "lines": [line.dict() for line in request.lines],
        "request_id": request.request_id,
        "source_order_id": order_id,
        "order_service": request.service,
        "order_source": "fde_bazaar",
        "order_created_at": stamp,
    }
    with bazaar._tx() as db:
        db.execute(
            """INSERT INTO orders(
                 id,warehouse_id,service,request_id,fingerprint,ship_by,priority,
                 delivery_status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,'pending',?,?)""",
            (
                order_id, "", request.service, request.request_id,
                bazaar._fingerprint(request), downstream["ship_by"], "urgent",
                stamp, stamp,
            ),
        )
        db.executemany(
            "INSERT INTO order_lines(order_id,sku,quantity,position) VALUES (?,?,?,?)",
            [
                (order_id, line.sku, line.quantity, position)
                for position, line in enumerate(request.lines)
            ],
        )
        db.execute(
            """INSERT INTO outbox(order_id,payload_json,status,next_attempt_at)
               VALUES (?,?,'pending',?)""",
            (order_id, json.dumps(downstream), stamp),
        )

    assert bazaar.deliver(order_id)
    current = bazaar.get_order(order_id, sync=False)
    assert current["delivery_status"] == "sent"
    assert current["warehouse_id"] is None
    assert next(iter(records.values()))["payload"] == downstream
    assert "warehouse_id" not in downstream
    assert calls["post"] == 1


def test_poll_persists_flexible_sub_order_progress(isolated):
    records, _ = isolated
    order, _ = bazaar.create_order(payload())
    remote = next(iter(records.values()))
    remote["status"] = "partially_completed"
    remote["sub_orders"] = [
        {
            "id": "SUB-1",
            "sku": "SKU-1",
            "status": "completed",
            "warehouse_id": "DC-02",
            "completed_quantity": 2,
            "future_downstream_field": {"kept": True},
        },
        {
            "id": "SUB-2",
            "sku": "SKU-2",
            "status": "held",
            "hold_reason": "inventory_shortage",
        },
    ]
    refreshed = bazaar.get_order(order["id"])
    assert refreshed["control_tower_status"] == "partially_completed"
    assert refreshed["sub_orders"][0]["future_downstream_field"] == {"kept": True}
    with bazaar._read_db() as db:
        persisted = bazaar._order_json(db, order["id"])
    assert persisted["sub_orders"] == refreshed["sub_orders"]


def test_validation_idempotency_and_changed_payload(isolated):
    request_id = str(uuid.uuid4())
    first, _ = bazaar.create_order(payload(request_id=request_id))
    same, created = bazaar.create_order(payload(request_id=request_id))
    assert not created
    assert same["id"] == first["id"]
    changed = payload(request_id=request_id)
    changed.lines[0].quantity = 9
    with pytest.raises(HTTPException) as conflict:
        bazaar.create_order(changed)
    assert conflict.value.status_code == 409
    with pytest.raises(ValidationError):
        bazaar.BazaarLineInput(sku="SKU-1", quantity=True)
    with pytest.raises(ValidationError):
        bazaar.BazaarLineInput(sku="SKU-1", quantity=1.5)
    duplicate = payload()
    duplicate.lines[1].sku = "SKU-1"
    with pytest.raises(HTTPException):
        bazaar.create_order(duplicate)


def test_identical_replay_bypasses_unavailable_catalog(isolated, monkeypatch):
    request_id = str(uuid.uuid4())
    first, _ = bazaar.create_order(payload(request_id=request_id))

    def unavailable(*args, **kwargs):
        raise bazaar.RemoteError("catalog unavailable")

    monkeypatch.setattr(bazaar, "request_json", unavailable)
    monkeypatch.setattr(bazaar, "_catalog_cache", None)
    replay, created = bazaar.create_order(payload(request_id=request_id))
    assert not created
    assert replay["id"] == first["id"]

    changed = payload(request_id=request_id)
    changed.lines[0].sku = "SKU-3"
    with pytest.raises(HTTPException) as conflict:
        bazaar.create_order(changed)
    assert conflict.value.status_code == 409


def test_reset_request_cannot_be_recreated_or_redelivered(isolated):
    _, calls = isolated
    request = payload()
    with bazaar._tx() as db:
        db.execute(
            "INSERT INTO retired_order_requests(request_digest) VALUES (?)",
            (hashlib.sha256(request.request_id.encode()).hexdigest(),),
        )
    with pytest.raises(HTTPException) as error:
        bazaar.create_order(request)
    assert error.value.status_code == 409
    assert calls == {"catalog": 0, "post": 0}
    with bazaar._read_db() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


def test_timeout_after_accept_retry_creates_one_downstream_record(isolated, monkeypatch):
    records, calls = isolated
    original = bazaar.request_json
    timed_out = {"once": False}

    def ambiguous(method, path, payload=None, timeout=4):
        response = original(method, path, payload, timeout)
        if method == "POST" and not timed_out["once"]:
            timed_out["once"] = True
            raise bazaar.RemoteError("Control Tower request failed: TimeoutError")
        return response

    monkeypatch.setattr(bazaar, "request_json", ambiguous)
    order, _ = bazaar.create_order(payload())
    assert order["delivery_status"] == "pending"
    bazaar.deliver(order["id"], manual=True)
    current = bazaar.get_order(order["id"])
    assert current["delivery_status"] == "sent"
    assert len(records) == 1
    assert calls["post"] == 2


def test_restart_recovers_stale_claim_and_permanent_failure_stays_failed(
    isolated, monkeypatch
):
    rejection = (
        "Control Tower rejected the request (422): "
        "{'warehouse_id': 'DC-01', 'sku': 'SKU-1', "
        "'requested': 2, 'available': 1}"
    )
    monkeypatch.setattr(
        bazaar,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            bazaar.RemoteError(rejection, 422)
        )
        if args[1] != "/catalog"
        else {
            "warehouses": [{"warehouse_id": "DC-01"}],
            "skus": [{"sku": "SKU-1"}, {"sku": "SKU-2"}],
        },
    )
    monkeypatch.setattr(bazaar, "_catalog_cache", None)
    order, _ = bazaar.create_order(payload())
    assert order["delivery_status"] == "failed"
    assert order["control_tower_order_id"] is None
    assert order["last_error"] == rejection
    assert "requested" in order["last_error"]
    assert "available" in order["last_error"]
    assert bazaar.deliver() is False

    with sqlite3.connect(bazaar.DB_PATH) as db:
        db.execute(
            "UPDATE outbox SET status='sending',permanent=0,claimed_at='2000-01-01T00:00:00Z' "
            "WHERE order_id=?",
            (order["id"],),
        )
        db.execute(
            "UPDATE orders SET delivery_status='sending' WHERE id=?", (order["id"],)
        )
    bazaar.start_worker()
    bazaar.stop_worker()
    with sqlite3.connect(bazaar.DB_PATH) as db:
        assert db.execute(
            "SELECT status FROM outbox WHERE order_id=?", (order["id"],)
        ).fetchone()[0] in {"pending", "failed"}