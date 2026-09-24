#!/usr/bin/env python3
"""Isolated deterministic policy-v2 demonstration; prints one JSON object."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import fulfillment_v2 as v2


NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("must include timezone")
    return parsed.astimezone(timezone.utc)


def payload(sku: str, quantity: int, request_id: str | None = None):
    return SimpleNamespace(
        priority="high",
        lines=[SimpleNamespace(sku=sku, quantity=quantity)],
        request_id=request_id or str(uuid.uuid4()),
        source_order_id=f"FBZ-{uuid.uuid4()}",
        order_service="Same_Day",
        order_source="fde_bazaar",
        order_created_at="2030-01-01T00:00:00Z",
        ship_by=None,
    )


def main() -> dict:
    with tempfile.TemporaryDirectory(prefix="fulfillment-v2-demo-") as folder:
        db = sqlite3.connect(Path(folder) / "demo.sqlite")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE orders (
              id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL, priority TEXT NOT NULL,
              ship_by TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              plan_json TEXT NOT NULL, issues_json TEXT NOT NULL,
              request_id TEXT NOT NULL UNIQUE, source_order_id TEXT,
              order_service TEXT, order_source TEXT, request_fingerprint TEXT
            );
            CREATE TABLE order_lines (
              order_id TEXT NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL,
              PRIMARY KEY(order_id,sku)
            );
            CREATE TABLE tasks (
              id TEXT PRIMARY KEY, order_id TEXT NOT NULL, stage TEXT NOT NULL,
              status TEXT NOT NULL, resource_id TEXT, resource_type TEXT,
              started_at TEXT, due_at TEXT, completed_at TEXT
            );
            CREATE TABLE events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
              at TEXT NOT NULL, message TEXT NOT NULL
            );
            """
        )
        opening = tuple(
            {
                "warehouse_id": "DEMO-W1", "sku": sku,
                "location": f"DEMO-W1-Z1-{sku}", "wms_qty": str(quantity),
                "erp_qty": str(quantity), "vision_qty": str(quantity),
                "reserved_qty": "0", "inventory_status": "AVAILABLE",
                "weight_kg": "1",
            }
            for sku, quantity in (("HAPPY", 100), ("BOUNDARY", 100), ("SHORT", 5))
        )
        robots = (
            {
                "robot_id": "DEMO-R1", "warehouse_id": "DEMO-W1",
                "robot_type": "AMR", "battery_soc": "90", "health_status": "HEALTHY",
                "payload_kg": "500", "safety_cert_status": "VALID",
                "calibration_status": "VALID", "connectivity": "ONLINE",
            },
        )
        sources = {
            "robots": robots,
            "maintenance": (
                {
                    "robot_id": "DEMO-R1", "warehouse_id": "DEMO-W1",
                    "cmms_status": "CLOSED", "fleet_availability": "AVAILABLE",
                },
            ),
            "control_assets": tuple(
                {
                    "asset_id": f"DEMO-{kind}", "warehouse_id": "DEMO-W1",
                    "asset_type": kind, "state": "AVAILABLE",
                    "maintenance_state": "CLEAR",
                }
                for kind in ("CONVEYOR", "DOCK_DOOR", "PACK_STATION")
            ),
        }
        v2.ensure_schema(db, opening, NOW)

        def append_event(connection, order_id, message, at=None):
            connection.execute(
                "INSERT INTO events(order_id,at,message) VALUES (?,?,?)",
                (order_id, v2._iso(at or NOW), message),
            )

        def order_json(connection, order_id):
            row = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            result = dict(row)
            result["lines"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT sku,quantity FROM order_lines WHERE order_id=?", (order_id,)
                )
            ]
            result["plan"] = json.loads(result.pop("plan_json"))
            result["issues"] = json.loads(result.pop("issues_json"))
            return v2.enrich_order(connection, result, clock)

        def create(item):
            return v2.create_order(
                db, item, parse_utc=parse_utc, now=clock,
                known_skus={"HAPPY", "BOUNDARY", "SHORT"},
                order_json=order_json, append_event=append_event,
            )

        def source_rows(dataset):
            return sources.get(dataset, ())

        def stock(sku, status):
            row = v2.inventory_rows(db, sku=sku)[0]
            return {
                "wms_qty": row["wms_qty"], "erp_qty": row["erp_qty"],
                "vision_qty": row["vision_qty"], "reserved_qty": row["reserved_qty"],
                "picked_qty": row["picked_qty"], "status": status,
            }

        steps = []
        checks = []
        clock = NOW
        happy = create(payload("HAPPY", 10))
        steps.append({"label": "accepted_10", **stock("HAPPY", happy["status"])})
        checks.append({
            "name": "acceptance_debits_each_source_and_credits_reserved",
            "passed": steps[-1]["wms_qty"] == 90 and steps[-1]["reserved_qty"] == 10,
        })
        v2.executor_once(db, clock, source_rows, append_event)
        steps.append({"label": "pick_started", **stock("HAPPY", order_json(db, happy["id"])["status"])})
        checks.append({
            "name": "assignment_and_pick_start_do_not_change_inventory",
            "passed": steps[-1]["wms_qty"] == 90 and steps[-1]["reserved_qty"] == 10,
        })
        clock += timedelta(seconds=45)
        v2.executor_once(db, clock, source_rows, append_event)
        steps.append({"label": "pick_completed_45s", **stock("HAPPY", order_json(db, happy["id"])["status"])})
        checks.append({
            "name": "pick_moves_reserved_to_picked_once",
            "passed": steps[-1]["reserved_qty"] == 0 and steps[-1]["picked_qty"] == 10,
        })
        for label in ("move_completed_90s", "pack_feed_completed_135s", "stage_completed_180s"):
            clock += timedelta(seconds=45)
            v2.executor_once(db, clock, source_rows, append_event)
            steps.append({"label": label, **stock("HAPPY", order_json(db, happy["id"])["status"])})
        checks.append({
            "name": "later_stages_never_debit_free_stock_again",
            "passed": all(step["wms_qty"] == 90 for step in steps[2:]),
        })
        checks.append({
            "name": "final_stage_completes_parent_and_wip",
            "passed": steps[-1]["status"] == "completed" and steps[-1]["picked_qty"] == 0,
        })

        first = create(payload("BOUNDARY", 60))
        steps.append({"label": "boundary_reserved_60", **stock("BOUNDARY", first["status"])})
        second = create(payload("BOUNDARY", 30))
        steps.append({"label": "boundary_reserved_additional_30", **stock("BOUNDARY", second["status"])})
        checks.append({
            "name": "free_stock_boundary_60_then_30",
            "passed": steps[-1]["wms_qty"] == 10 and steps[-1]["reserved_qty"] == 90,
        })

        shortage = create(payload("SHORT", 10))
        steps.append({"label": "shortage_held", **stock("SHORT", shortage["status"])})
        short_row = v2.inventory_rows(db, sku="SHORT")[0]
        v2.correct_inventory(
            db, short_row["inventory_row_id"],
            {"wms_qty": 20, "erp_qty": 20, "vision_qty": 20},
            "free", short_row["revision"], "Isolated demo replenishment", "demo", clock,
        )
        recovered = order_json(db, shortage["id"])
        steps.append({"label": "shortage_corrected_and_recovered", **stock("SHORT", recovered["status"])})
        checks.append({
            "name": "correction_reevaluates_and_reserves_held_line",
            "passed": steps[-1]["wms_qty"] == 10 and steps[-1]["reserved_qty"] == 10,
        })
        db.commit()
        return {
            "success": all(check["passed"] for check in checks),
            "steps": steps,
            "checks": checks,
            "assumptions": [
                "Simulation only; no live WMS, robot, asset, or physical action.",
                "Each persisted stage duration is exactly 45 seconds.",
                "The temporary SQLite database and process-local fixtures are deleted on exit.",
            ],
        }


if __name__ == "__main__":
    print(json.dumps(main(), separators=(",", ":")))