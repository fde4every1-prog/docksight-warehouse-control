"""FDE Bazaar order intake with an independently owned durable outbox."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, validator

from fulfillment_status import migrate_bazaar


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("BAZAAR_DB_PATH", ROOT / ".local" / "bazaar.sqlite"))
HTTP_TIMEOUT_SECONDS = 4.0
CATALOG_TTL_SECONDS = 30.0
MAX_AUTO_ATTEMPTS = 8
STALE_SENDING_SECONDS = 30

SERVICES = {
    "Same_Day": {
        "label": "Same day",
        "description": "Ships within 6 hours of the original order creation time.",
        "priority": "urgent",
        "hours": 6,
    },
    "Next_Day": {
        "label": "Next day",
        "description": "Ships within 12 hours of the original order creation time.",
        "priority": "high",
        "hours": 12,
    },
    "Standard": {
        "label": "Standard",
        "description": "Ships within 24 hours of the original order creation time.",
        "priority": "standard",
        "hours": 24,
    },
}
ASSUMPTIONS = [
    "Service deadlines are exact UTC offsets from the original persisted creation time.",
    "Every new order selects one warehouse; Control Tower assigns eligible zones and locations within it.",
    "Catalog entries are normalized from the complete current Control Tower catalog.",
    "Delivery is asynchronous and idempotent; a Bazaar acceptance does not imply fulfillment acceptance.",
]

router = APIRouter(prefix="/api/bazaar", tags=["fde-bazaar"])
_db_lock = threading.RLock()
_delivery_lock = threading.Lock()
_worker_stop = threading.Event()
_worker_thread: threading.Thread | None = None
_catalog_lock = threading.Lock()
_catalog_cache: tuple[float, dict[str, Any]] | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def control_tower_base_url() -> str:
    configured = os.environ.get("CONTROL_TOWER_API_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/fulfillment"


class RemoteError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Bounded real HTTP seam, replaceable by isolated tests."""

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{control_tower_base_url()}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail")
        except Exception:
            detail = None
        raise RemoteError(
            f"Control Tower rejected the request ({exc.code})"
            + (f": {detail}" if detail else ""),
            exc.code,
        ) from exc
    except (URLError, socket.timeout, TimeoutError, OSError, ValueError) as exc:
        raise RemoteError(f"Control Tower request failed: {type(exc).__name__}") from exc


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, sqlite3.connect(DB_PATH) as db:
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            CREATE TABLE IF NOT EXISTS retired_order_requests (
                request_digest TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                warehouse_id TEXT NOT NULL,
                service TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL,
                ship_by TEXT NOT NULL,
                priority TEXT NOT NULL,
                delivery_status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                control_tower_order_id TEXT,
                last_error TEXT,
                control_tower_status TEXT,
                control_tower_issues_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_lines (
                order_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                position INTEGER NOT NULL,
                PRIMARY KEY(order_id, sku),
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                order_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                next_attempt_at TEXT,
                claimed_at TEXT,
                permanent INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE INDEX IF NOT EXISTS bazaar_outbox_due
                ON outbox(status, permanent, next_attempt_at);
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(orders)")}
        if "control_tower_sub_orders_json" not in columns:
            db.execute(
                "ALTER TABLE orders ADD COLUMN control_tower_sub_orders_json "
                "TEXT NOT NULL DEFAULT '[]'"
            )
        migrate_bazaar(db)


@contextmanager
def _tx():
    _init_db()
    with _db_lock:
        db = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


@contextmanager
def _read_db():
    _init_db()
    with _db_lock, sqlite3.connect(DB_PATH, timeout=5) as db:
        db.row_factory = sqlite3.Row
        yield db


class BazaarLineInput(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    quantity: int

    @validator("quantity", pre=True)
    def positive_strict_integer(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("quantity must be a positive integer")
        return value


class BazaarOrderInput(BaseModel):
    # Nullable only so a pre-warehouse idempotency request can still replay.
    # create_order rejects it for every genuinely new request.
    warehouse_id: str | None = Field(None, max_length=64)
    service: Literal["Next_Day", "Same_Day", "Standard"]
    lines: list[BazaarLineInput] = Field(..., min_items=1)
    request_id: str

    @validator("request_id")
    def request_uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError) as exc:
            raise ValueError("request_id must be a UUID") from exc


def _normalized_catalog(raw: dict[str, Any]) -> dict[str, Any]:
    warehouses = []
    for item in raw.get("warehouses", []):
        warehouse_id = str(item.get("warehouse_id") or "")
        if warehouse_id:
            location = ", ".join(
                str(value) for value in (item.get("region"), item.get("country")) if value
            )
            warehouses.append(
                {"warehouse_id": warehouse_id, "name": location or warehouse_id}
            )
    skus = []
    for item in raw.get("skus", []):
        sku = str(item.get("sku") or "")
        if sku:
            skus.append({"sku": sku, "name": str(item.get("description") or sku)})
    return {
        "warehouses": warehouses,
        "skus": skus,
        "services": [
            {
                "code": code,
                "label": details["label"],
                "description": details["description"],
                "priority": details["priority"],
            }
            for code, details in SERVICES.items()
        ],
        "timezone": "UTC",
        "assumptions": ASSUMPTIONS,
    }


def catalog(force: bool = False) -> dict[str, Any]:
    global _catalog_cache
    now = time.monotonic()
    with _catalog_lock:
        if not force and _catalog_cache and now - _catalog_cache[0] < CATALOG_TTL_SECONDS:
            return _catalog_cache[1]
        try:
            result = _normalized_catalog(request_json("GET", "/catalog"))
        except RemoteError as exc:
            raise HTTPException(503, str(exc)) from exc
        _catalog_cache = (now, result)
        return result


def _validate_catalog(payload: BazaarOrderInput) -> None:
    current = catalog()
    warehouses = {item["warehouse_id"] for item in current["warehouses"]}
    skus = {item["sku"] for item in current["skus"]}
    if payload.warehouse_id not in warehouses:
        raise HTTPException(422, f"Unknown warehouse_id {payload.warehouse_id}")
    seen: set[str] = set()
    for line in payload.lines:
        if line.sku in seen:
            raise HTTPException(
                422, f"Duplicate SKU {line.sku}; combine quantities before submitting"
            )
        if line.sku not in skus:
            raise HTTPException(422, f"Unknown SKU {line.sku}")
        seen.add(line.sku)


def _deadline(service: str, now: datetime | None = None) -> datetime:
    return (now or utc_now()).astimezone(timezone.utc) + timedelta(
        hours=int(SERVICES[service]["hours"])
    )


def _fingerprint(payload: BazaarOrderInput) -> str:
    canonical = {
        "warehouse_id": payload.warehouse_id,
        "service": payload.service,
        "lines": sorted(
            ({"sku": line.sku, "quantity": line.quantity} for line in payload.lines),
            key=lambda item: item["sku"],
        ),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _lines(db: sqlite3.Connection, order_id: str) -> list[dict[str, Any]]:
    return [
        {"sku": row["sku"], "quantity": row["quantity"]}
        for row in db.execute(
            "SELECT sku,quantity FROM order_lines WHERE order_id=? ORDER BY position",
            (order_id,),
        )
    ]


def _order_json(db: sqlite3.Connection, order_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Unknown Bazaar order: {order_id}")
    return {
        "id": row["id"],
        "warehouse_id": row["warehouse_id"] or None,
        "service": row["service"],
        "lines": _lines(db, order_id),
        "request_id": row["request_id"],
        "created_at": row["created_at"],
        "ship_by": row["ship_by"],
        "priority": row["priority"],
        "delivery_status": row["delivery_status"],
        "attempts": row["attempts"],
        "control_tower_order_id": row["control_tower_order_id"],
        "last_error": row["last_error"],
        "control_tower_status": row["control_tower_status"],
        "control_tower_issues": json.loads(row["control_tower_issues_json"]),
        "sub_orders": json.loads(row["control_tower_sub_orders_json"]),
        "updated_at": row["updated_at"],
    }


def _claim(order_id: str | None = None, manual: bool = False) -> tuple[str, dict[str, Any]] | None:
    now = iso(utc_now())
    with _tx() as db:
        if order_id:
            row = db.execute(
                "SELECT * FROM outbox WHERE order_id=?", (order_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, f"Unknown Bazaar order: {order_id}")
            if row["status"] == "sent":
                return None
            if row["status"] == "sending":
                raise HTTPException(409, "Order delivery is already in progress")
            if row["permanent"] and not manual:
                return None
        else:
            row = db.execute(
                """
                SELECT * FROM outbox
                WHERE status IN ('pending','failed') AND permanent=0
                  AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                ORDER BY next_attempt_at, rowid LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                return None
        db.execute(
            "UPDATE outbox SET status='sending',claimed_at=? WHERE order_id=?",
            (now, row["order_id"]),
        )
        db.execute(
            "UPDATE orders SET delivery_status='sending',updated_at=? WHERE id=?",
            (now, row["order_id"]),
        )
        return row["order_id"], json.loads(row["payload_json"])


def _finish_delivery(
    order_id: str, response: dict[str, Any] | None, error: RemoteError | None
) -> None:
    now = utc_now()
    with _tx() as db:
        current = db.execute(
            "SELECT attempts FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        attempts = int(current["attempts"]) + 1
        if error is None:
            db.execute(
                """
                UPDATE orders SET delivery_status='sent',attempts=?,
                    control_tower_order_id=?,control_tower_status=?,
                    control_tower_issues_json=?,control_tower_sub_orders_json=?,
                    last_error=NULL,updated_at=?
                WHERE id=?
                """,
                (
                    attempts,
                    response.get("id"),
                    response.get("status"),
                    json.dumps(response.get("issues") or []),
                    json.dumps(response.get("sub_orders") or []),
                    iso(now),
                    order_id,
                ),
            )
            db.execute(
                "UPDATE outbox SET status='sent',next_attempt_at=NULL,claimed_at=NULL WHERE order_id=?",
                (order_id,),
            )
            return
        permanent = error.status is not None and 400 <= error.status < 500
        exhausted = attempts >= MAX_AUTO_ATTEMPTS
        delay = min(300, 2 ** min(attempts, 8))
        status = "failed" if permanent or exhausted else "pending"
        next_attempt = None if permanent or exhausted else iso(now + timedelta(seconds=delay))
        db.execute(
            "UPDATE orders SET delivery_status=?,attempts=?,last_error=?,updated_at=? WHERE id=?",
            (status, attempts, str(error), iso(now), order_id),
        )
        db.execute(
            """
            UPDATE outbox SET status=?,next_attempt_at=?,claimed_at=NULL,permanent=?
            WHERE order_id=?
            """,
            (status, next_attempt, int(permanent or exhausted), order_id),
        )


def deliver(order_id: str | None = None, manual: bool = False) -> bool:
    with _delivery_lock:
        claim = _claim(order_id, manual)
        if not claim:
            return False
        claimed_id, payload = claim
        try:
            response = request_json("POST", "/orders", payload)
        except RemoteError as exc:
            _finish_delivery(claimed_id, None, exc)
        else:
            _finish_delivery(claimed_id, response, None)
        return True


def create_order(payload: BazaarOrderInput) -> tuple[dict[str, Any], bool]:
    fingerprint = _fingerprint(payload)
    # Idempotent replay must not depend on current catalog availability or on
    # catalog entries that may have changed since the order was accepted.
    with _read_db() as db:
        _reject_retired_request(db, payload.request_id)
        existing = db.execute(
            "SELECT id,fingerprint FROM orders WHERE request_id=?",
            (payload.request_id,),
        ).fetchone()
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise HTTPException(
                    409, "request_id is already associated with a different payload"
                )
            return _order_json(db, existing["id"]), False

    if payload.warehouse_id is None or not payload.warehouse_id.strip():
        raise HTTPException(422, "warehouse_id is required for new Bazaar orders")
    _validate_catalog(payload)
    with _tx() as db:
        _reject_retired_request(db, payload.request_id)
        # A concurrent creator may have committed while catalog validation was
        # in flight. Recheck under the write transaction before inserting.
        existing = db.execute(
            "SELECT id,fingerprint FROM orders WHERE request_id=?",
            (payload.request_id,),
        ).fetchone()
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise HTTPException(
                    409, "request_id is already associated with a different payload"
                )
            return _order_json(db, existing["id"]), False
        order_id = f"FBZ-{uuid.uuid4()}"
        now = utc_now()
        ship_by = _deadline(payload.service, now)
        priority = str(SERVICES[payload.service]["priority"])
        downstream = {
            "priority": priority,
            "ship_by": iso(ship_by),
            "lines": [line.dict() for line in payload.lines],
            "request_id": payload.request_id,
            "source_order_id": order_id,
            "order_service": payload.service,
            "order_source": "fde_bazaar",
            "order_created_at": iso(now),
        }
        downstream["warehouse_id"] = payload.warehouse_id
        db.execute(
            """
            INSERT INTO orders(id,warehouse_id,service,request_id,fingerprint,ship_by,
                priority,delivery_status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,'pending',?,?)
            """,
            (
                order_id,
                payload.warehouse_id,
                payload.service,
                payload.request_id,
                fingerprint,
                iso(ship_by),
                priority,
                iso(now),
                iso(now),
            ),
        )
        db.executemany(
            "INSERT INTO order_lines(order_id,sku,quantity,position) VALUES (?,?,?,?)",
            [
                (order_id, line.sku, line.quantity, position)
                for position, line in enumerate(payload.lines)
            ],
        )
        db.execute(
            "INSERT INTO outbox(order_id,payload_json,status,next_attempt_at) VALUES (?,?,'pending',?)",
            (order_id, json.dumps(downstream, sort_keys=True), iso(now)),
        )
    deliver(order_id)
    with _read_db() as db:
        return _order_json(db, order_id), True


def _reject_retired_request(db: sqlite3.Connection, request_id: str) -> None:
    digest = hashlib.sha256(request_id.encode()).hexdigest()
    if db.execute(
        "SELECT 1 FROM retired_order_requests WHERE request_digest=?", (digest,)
    ).fetchone():
        raise HTTPException(
            409, "This request was retired by the order reset; create a new order."
        )


def get_order(order_id: str, sync: bool = True) -> dict[str, Any]:
    with _read_db() as db:
        result = _order_json(db, order_id)
    if sync and result["control_tower_order_id"]:
        try:
            remote = request_json(
                "GET", f"/orders/{result['control_tower_order_id']}"
            )
            result["control_tower_status"] = remote.get("status")
            result["control_tower_issues"] = remote.get("issues") or []
            result["sub_orders"] = remote.get("sub_orders") or []
            result["sync_error"] = None
            observed_at = iso(utc_now())
            result["updated_at"] = observed_at
            with _tx() as db:
                db.execute(
                    """
                    UPDATE orders SET control_tower_status=?,
                        control_tower_issues_json=?,
                        control_tower_sub_orders_json=?,updated_at=?
                    WHERE id=?
                    """,
                    (
                        result["control_tower_status"],
                        json.dumps(result["control_tower_issues"]),
                        json.dumps(result["sub_orders"]),
                        observed_at,
                        order_id,
                    ),
                )
        except RemoteError as exc:
            # Preserve the last durable progress snapshot. sync_error makes its
            # freshness explicit without making per-SKU progress disappear.
            result["sync_error"] = str(exc)
    else:
        result["sync_error"] = None
    return result


def list_orders(limit: int = 25, offset: int = 0) -> dict[str, Any]:
    with _read_db() as db:
        total = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        orders = [
            _order_json(db, row["id"])
            for row in db.execute(
                "SELECT id FROM orders ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        ]
        counts = {
            row["delivery_status"]: row["count"]
            for row in db.execute(
                "SELECT delivery_status,COUNT(*) AS count FROM orders GROUP BY delivery_status"
            )
        }
    terminal = {"completed", "fulfilled", "cancelled", "canceled", "failed"}
    for index, order in enumerate(orders):
        downstream_status = str(order["control_tower_status"] or "").lower()
        if (
            order["delivery_status"] == "sent"
            and downstream_status not in terminal
            and order["control_tower_order_id"]
        ):
            # History has the same freshness path as the receipt. Network calls
            # happen outside SQLite transactions and successful snapshots are
            # persisted by get_order.
            orders[index] = get_order(order["id"])
    return {
        "orders": orders,
        "total": total,
        "limit": limit,
        "offset": offset,
        "summary": {
            "total": total,
            "sent": counts.get("sent", 0),
            "pending": counts.get("pending", 0) + counts.get("sending", 0),
            "failed": counts.get("failed", 0),
        },
    }


def _worker_loop() -> None:
    while not _worker_stop.wait(1):
        try:
            while deliver():
                if _worker_stop.is_set():
                    return
        except Exception:
            _worker_stop.wait(2)


def start_worker() -> None:
    global _worker_thread
    _init_db()
    with _tx() as db:
        stale = [
            row["order_id"]
            for row in db.execute(
                "SELECT order_id FROM outbox WHERE status='sending'",
            )
        ]
        for order_id in stale:
            db.execute(
                "UPDATE outbox SET status='pending',claimed_at=NULL,next_attempt_at=? WHERE order_id=?",
                (iso(utc_now()), order_id),
            )
            db.execute(
                "UPDATE orders SET delivery_status='pending',updated_at=? WHERE id=?",
                (iso(utc_now()), order_id),
            )
    if _worker_thread and _worker_thread.is_alive():
        return
    _worker_stop.clear()
    _worker_thread = threading.Thread(
        target=_worker_loop, name="bazaar-outbox", daemon=True
    )
    _worker_thread.start()


def stop_worker() -> None:
    global _worker_thread
    _worker_stop.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=HTTP_TIMEOUT_SECONDS + 1)
    _worker_thread = None


@router.get("/catalog")
def get_catalog():
    return catalog()


@router.get("/orders")
def get_orders(
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)
):
    return list_orders(limit, offset)


@router.post("/orders", status_code=201)
def post_order(payload: BazaarOrderInput):
    result, _ = create_order(payload)
    return result


@router.get("/orders/{order_id}")
def order_detail(order_id: str):
    return get_order(order_id)


@router.post("/orders/{order_id}/retry")
def retry_order(order_id: str):
    with _read_db() as db:
        _order_json(db, order_id)
    deliver(order_id, manual=True)
    return get_order(order_id)