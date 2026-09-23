"""Guardrail: inherited baseline version stays 2.0.0. Overlay versions separately."""

from pathlib import Path

import warehouse_control.api as api
from warehouse_control.overlay import BASELINE_VERSION, OVERLAY_VERSION
from warehouse_control.overlay.register import load_register, summary

ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_baseline_not_bumped():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "2.0.0"' in text


def test_api_surface_still_baseline():
    assert api.app.version == "2.0.0"


def test_overlay_does_not_replace_baseline_version():
    assert BASELINE_VERSION == "2.0.0"
    assert OVERLAY_VERSION == "0.1.0"
    assert OVERLAY_VERSION != BASELINE_VERSION


def test_register_counts_are_the_pm_contract():
    counts = load_register()["counts"]
    assert counts["leverage_assets"] == 9
    assert counts["transformations_total"] == 12
    assert counts["committed_10_day"] == 8
    assert counts["deferred_after_capstone"] == 4
    s = summary()
    assert s["baseline_frozen"] is True
    assert len(s["committed_10_day"]) == 8
    assert len(s["deferred"]) == 4
