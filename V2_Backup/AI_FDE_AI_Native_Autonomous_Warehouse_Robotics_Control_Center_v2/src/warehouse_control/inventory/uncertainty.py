"""Inventory observation: retain wms/erp/vision. Never invent pickable truth (I3)."""

from warehouse_control.legacy.inventory import legacy_available_qty


def observe_inventory(row: dict) -> dict:
    wms = row.get("wms_qty")
    erp = row.get("erp_qty")
    vision = row.get("vision_qty")
    reserved = row.get("reserved_qty", 0)
    uncertain = len({str(wms), str(erp), str(vision)}) > 1
    out = {
        "warehouse_id": row.get("warehouse_id"),
        "sku": row.get("sku"),
        "location": row.get("location"),
        "wms_qty": wms,
        "erp_qty": erp,
        "vision_qty": vision,
        "reserved_qty": reserved,
        "uncertain": uncertain,
        "conflicts": [{"kind": "INVENTORY_QTY"}] if uncertain else [],
        "legacy_available_qty": legacy_available_qty(
            {"wms_qty": wms, "reserved_qty": reserved}
        ),
    }
    return out
