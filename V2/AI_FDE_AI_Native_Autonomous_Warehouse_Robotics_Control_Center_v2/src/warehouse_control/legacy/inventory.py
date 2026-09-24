def legacy_available_qty(row: dict) -> int:
    """Legacy truth rule: blindly trusts WMS quantity."""
    return int(row["wms_qty"]) - int(row.get("reserved_qty", 0))
