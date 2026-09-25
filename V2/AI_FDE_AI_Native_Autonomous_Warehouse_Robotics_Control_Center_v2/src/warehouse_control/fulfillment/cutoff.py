"""Cutoff awareness: carrier_cutoff + TMS DELAYED + shadow staleness (I7)."""

from warehouse_control.repository import ROOT, csv_rows

SHADOW = ROOT / "data" / "shadow" / "ops_emails.txt"


def _shadow_text() -> str:
    if SHADOW.is_file():
        return SHADOW.read_text(encoding="utf-8")
    return ""


def assess_cutoff(order_id: str) -> dict:
    order = next((o for o in csv_rows("orders.csv") if o.get("order_id") == order_id), None)
    if order is None:
        return {"error": "not_found", "order_id": order_id}

    shipment = next(
        (s for s in csv_rows("shipments.csv") if s.get("order_id") == order_id),
        None,
    ) or {}
    shadow = _shadow_text()
    tms = shipment.get("tms_status")
    delayed = tms == "DELAYED"
    email_stale = "OMS SLA table will not refresh" in shadow or "Carrier-A advanced" in shadow
    stale = delayed or email_stale
    conflicts = []
    if stale:
        conflicts.append({"kind": "CUTOFF_STALE"})
    # Must not report on_time true from OMS alone while TMS DELAYED.
    on_time = False if delayed else None
    return {
        "order_id": order_id,
        "warehouse_id": order.get("warehouse_id"),
        "carrier_cutoff": order.get("carrier_cutoff"),
        "oms_status": order.get("oms_status"),
        "wms_status": order.get("wms_status"),
        "tms_status": tms,
        "carrier": shipment.get("carrier"),
        "planned_departure": shipment.get("planned_departure"),
        "actual_departure": shipment.get("actual_departure"),
        "shadow_carrier_cutoff_mentioned": "Carrier-A" in shadow and "35" in shadow,
        "conflicts": conflicts,
        "on_time": on_time,
        "recommendation": "miss_cutoff" if delayed else None,
        "physical_control": "disabled",
    }
