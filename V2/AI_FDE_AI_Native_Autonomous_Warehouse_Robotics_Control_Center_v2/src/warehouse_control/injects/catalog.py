"""In-memory inject overlays. Do not rewrite data/ CSVs."""

INJECTS = {
    "inject_01": {
        "id": "inject_01",
        "title": "AS/RS unavailable",
        "file": "scenarios/inject_01.md",
        "force_asset_type_down": "ASRS",
    },
    "inject_02": {
        "id": "inject_02",
        "title": "charging subsystem failure",
        "file": "scenarios/inject_02.md",
        "force_asset_type_down": "CHARGER",
    },
    "inject_03": {
        "id": "inject_03",
        "title": "dock closure",
        "file": "scenarios/inject_03.md",
        "force_asset_type_down": "DOCK_DOOR",
    },
}


def load_inject(inject_id: str) -> dict:
    spec = INJECTS.get(inject_id)
    if spec is None:
        raise KeyError(inject_id)
    return dict(spec)


def apply_asset_overlay(assets: list[dict], inject: dict | None, warehouse_id: str | None):
    rows = [dict(a) for a in assets]
    if not inject:
        return rows
    kind = inject.get("force_asset_type_down")
    for row in rows:
        if kind and row.get("asset_type") == kind:
            if warehouse_id and row.get("warehouse_id") != warehouse_id:
                continue
            row["state"] = "DOWN"
            row["inject_id"] = inject.get("id")
    return rows
