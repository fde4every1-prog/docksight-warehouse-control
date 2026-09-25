"""Supervisor workflow view: order → truck. Two scenarios. Observe-only."""

from warehouse_control.browse import order_browse, robot_on_order
from warehouse_control.inventory.uncertainty import observe_inventory
from warehouse_control.repository import csv_rows

GREEN_ORDER = "ORD-009999"
BROKEN_ORDER = "ORD-000004"
GREEN_SKU = ("DC-01", "SKU-09999", "DC-01-Z02-B099")


def _zone(zone_id: str) -> dict:
    return next((z for z in csv_rows("zones.csv") if z.get("zone_id") == zone_id), {}) or {}


def _inv(warehouse_id: str, sku: str, location: str) -> dict | None:
    for row in csv_rows("inventory_snapshot.csv"):
        if (
            row.get("warehouse_id") == warehouse_id
            and row.get("sku") == sku
            and row.get("location") == location
        ):
            return row
    return None


def _events(order_id: str, task_ids: list[str]) -> list[dict]:
    import json

    from warehouse_control.repository import ROOT

    want = {order_id, *task_ids}
    path = ROOT / "data" / "raw" / "events.jsonl"
    if not path.is_file():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if row.get("entity_id") in want:
            out.append(
                {
                    "event_time": row.get("event_time"),
                    "source": row.get("source"),
                    "event_type": row.get("event_type"),
                    "entity_id": row.get("entity_id"),
                }
            )
    out.sort(key=lambda e: e.get("event_time") or "")
    return out[:12]


def _stage(sid, title, status, headline, facts, you_should):
    return {
        "id": sid,
        "title": title,
        "status": status,
        "headline": headline,
        "facts": facts,
        "you_should": you_should,
    }


def _build_scenario(kind: str) -> dict:
    order_id = GREEN_ORDER if kind == "green" else BROKEN_ORDER
    browse = order_browse(order_id)
    order = browse["order"]
    ship = browse["shipment"]
    cut = browse["cutoff"]
    rec = browse["reconcile"]
    tasks = browse["tasks"]
    first = tasks[0] if tasks else {}
    rid = first.get("assigned_robot") or ""
    probe = robot_on_order(order_id, rid) if rid else {}
    dest = first.get("dest_zone") or ""
    zone = _zone(dest)

    oms = order.get("oms_status")
    wms = order.get("wms_status")
    header_ok = oms == wms
    complete = rec.get("completable") is True
    delayed = cut.get("tms_status") == "DELAYED"
    departed = cut.get("tms_status") == "DEPARTED" and bool(ship.get("actual_departure"))
    robot_ok = probe.get("eligibility") != "INELIGIBLE"
    zone_ok = str(zone.get("robot_access") or "").upper() != "RESTRICTED"
    task_split = any(t.get("wes_status") != t.get("fleet_status") for t in tasks)

    if kind == "green":
        inv_row = _inv(*GREEN_SKU)
        inv = observe_inventory(inv_row) if inv_row else {}
        stock_ok = inv.get("uncertain") is False
        stock_stage = _stage(
            "stock",
            "2 · Stock",
            "ok" if stock_ok else "stop",
            "Bin counts agree. Not an order line — same warehouse only.",
            [
                {"k": "SKU", "v": GREEN_SKU[1]},
                {"k": "Bin", "v": GREEN_SKU[2]},
                {"k": "WMS / ERP / vision", "v": f"{inv.get('wms_qty')} / {inv.get('erp_qty')} / {inv.get('vision_qty')}"},
            ],
            "You may treat qty as consistent. Still do not pick-as-known from this tower.",
        )
        decision = "Treat as finished. Do not dispatch. The truck already left."
        decision_kind = "done"
    else:
        stock_stage = _stage(
            "stock",
            "2 · Stock",
            "skip",
            "No SKU on the order file. Do not invent a pick list.",
            [
                {"k": "Order lines", "v": "None in this dataset"},
                {"k": "Warehouse", "v": order.get("warehouse_id") or ""},
            ],
            "Skip pick. The break is later: job, robot, and truck.",
        )
        inv = {}
        decision = "Stop. Miss the cutoff. Do not assign this robot. Do not open a zone."
        decision_kind = "stop"

    stages = [
        _stage(
            "order",
            "1 · Order in",
            "ok" if header_ok and not delayed else "stop",
            "OMS and WMS " + ("agree" if header_ok else "disagree") + ".",
            [
                {"k": "Order", "v": order_id},
                {"k": "Warehouse", "v": order.get("warehouse_id") or ""},
                {"k": "OMS / WMS", "v": f"{oms} / {wms}"},
                {"k": "Cutoff", "v": order.get("carrier_cutoff") or ""},
                {"k": "Service", "v": order.get("service_level") or ""},
            ],
            "Read both statuses. Do not pick a winner by system name.",
        ),
        stock_stage,
        _stage(
            "work",
            "3 · Warehouse jobs",
            "ok" if complete and not task_split else "stop",
            "Every task must be COMPLETE in both WES and fleet.",
            [
                {
                    "k": t.get("task_id"),
                    "v": f"{t.get('task_type')} · WES {t.get('wes_status')} · fleet {t.get('fleet_status')}",
                }
                for t in tasks
            ],
            "If they split, the order is not finished.",
        ),
        _stage(
            "robot",
            "4 · Robot",
            "ok" if robot_ok else "stop",
            "Available is not suitable.",
            [
                {"k": "Assigned", "v": rid},
                {"k": "Robot lives", "v": (probe.get("robot_warehouse_id") or "")},
                {"k": "Task site", "v": (probe.get("task_warehouse_id") or "")},
                {"k": "Eligibility", "v": probe.get("eligibility") or ""},
                {"k": "Gates", "v": ", ".join(probe.get("gates_failed") or []) or "none"},
            ],
            "Do not assign from this screen. Preview only.",
        ),
        _stage(
            "zone",
            "5 · Path / zone",
            "ok" if zone_ok else "stop",
            "RESTRICTED dest is a refuse, even for a good robot.",
            [
                {"k": "Dest", "v": dest},
                {"k": "Type", "v": zone.get("zone_type") or ""},
                {"k": "Robot access", "v": zone.get("robot_access") or ""},
            ],
            "Cutoff pressure cannot open a keep-out.",
        ),
        _stage(
            "truck",
            "6 · Truck",
            "ok" if departed and not delayed else "stop",
            "On-time is TMS, not OMS alone.",
            [
                {"k": "Shipment", "v": ship.get("shipment_id") or ""},
                {"k": "TMS", "v": ship.get("tms_status") or ""},
                {"k": "Carrier", "v": ship.get("carrier") or ""},
                {"k": "Planned", "v": ship.get("planned_departure") or ""},
                {"k": "Actual", "v": ship.get("actual_departure") or "empty"},
            ],
            cut.get("recommendation") or "Do not invent a departure time.",
        ),
    ]

    return {
        "id": kind,
        "order_id": order_id,
        "title": "Agreed path — order reached the truck" if kind == "green" else "Broken path — do not send work",
        "persona": "Supervisor",
        "decision": decision,
        "decision_kind": decision_kind,
        "complete": complete,
        "on_time": cut.get("on_time"),
        "stages": stages,
        "timeline": _events(order_id, [t.get("task_id") for t in tasks if t.get("task_id")]),
        "assign_supported": False,
        "physical_control": "disabled",
        "raw": {"order": order, "shipment": ship, "tasks": tasks, "probe": probe, "inventory": inv},
    }


def workflow_snapshot() -> dict:
    return {
        "persona": "Warehouse supervisor",
        "question": "Should I treat this as real and act — or stop?",
        "physical_control": "disabled",
        "assign_supported": False,
        "scenarios": {
            "green": _build_scenario("green"),
            "broken": _build_scenario("broken"),
        },
    }
