"""Read-only transformation register. Baseline package version stays 2.0.0."""

from __future__ import annotations

import json
from pathlib import Path

from warehouse_control.overlay import BASELINE_VERSION, OVERLAY_VERSION

ROOT = Path(__file__).resolve().parents[3]
REGISTER_PATH = ROOT / "participant" / "transformation_register.json"


def load_register() -> dict:
    with REGISTER_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def summary() -> dict:
    reg = load_register()
    transforms = reg["transformations"]
    committed = [t for t in transforms if t["scope"] == "10-day"]
    deferred = [t for t in transforms if t["scope"] == "deferred"]
    return {
        "baseline_version": BASELINE_VERSION,
        "baseline_frozen": True,
        "overlay_version": OVERLAY_VERSION,
        "leverage_assets": len(reg["leverage"]),
        "transformations_total": len(transforms),
        "committed_10_day": [t["id"] for t in committed],
        "deferred": [t["id"] for t in deferred],
        "register_counts": reg["counts"],
    }
