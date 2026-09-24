"""Contention demo UI. Observe-only. No reservation. No OT."""

from pathlib import Path

from warehouse_control.api import CONTENTION_UI_FILE, app, contention_snapshot_route, contention_ui
from warehouse_control.contention import LOCATION_ZONE_ID, snapshot

SRC = Path(__file__).resolve().parents[1] / "src" / "warehouse_control"


def test_contention_routes_are_get_only():
    paths = {getattr(r, "path", "") for r in app.routes}
    methods = []
    for r in app.routes:
        methods.extend(getattr(r, "methods", set()) or [])
    assert "/contention" in paths
    assert "/contention/snapshot" in paths
    assert "POST" not in methods
    assert "/missions" not in paths


def test_contention_html_is_observe_only():
    html = CONTENTION_UI_FILE.read_text(encoding="utf-8")
    assert "TSK-000019-2" in html
    assert "DC-01-Z05" in html
    assert "inject_03" in html
    assert "SKU-01146" in html
    assert "physical_control" in html
    assert "method: 'POST'" not in html
    assert 'method: "POST"' not in html
    assert "/missions" not in html
    page = contention_ui()
    assert page.path == CONTENTION_UI_FILE


def test_contention_snapshot_refuses_without_mutex():
    body = contention_snapshot_route()
    assert body["physical_control"] == "disabled"
    assert body["assign_supported"] is False
    assert body["reservation_supported"] is False
    loc = body["location"]
    assert loc["zone"]["zone_id"] == LOCATION_ZONE_ID
    assert loc["zone"]["robot_access"] == "RESTRICTED"
    assert len(loc["claimants"]) >= 2
    assert all(c["dest_zone"] == LOCATION_ZONE_ID for c in loc["claimants"])
    assert loc["probe"]["eligibility"] == "INELIGIBLE"
    assert "G4" in loc["probe"]["gates_failed"]
    assert loc["allocation"]["chosen_robot_id"] is None
    assert loc["allocation"]["execution_applied"] is False
    dock = body["dock"]
    assert dock["outbound_blocked"] is True
    assert dock["chosen_robot_id"] is None
    assert dock["decision_hint"] == "ABSTAIN"
    assert dock["safety_bypass"] == "DENY"
    assert dock["csv_rewritten"] is False
    inv = body["inventory"]
    assert inv["uncertain"] is True
    assert str(inv["wms_qty"]) == "205"
    assert str(inv["vision_qty"]) == "202"
    assert "available_qty" not in inv
    assert body["blocked"]["release_zone"] == "DENY"
    assert body["blocked"]["pick_as_known"] in {"DENY", "ABSTAIN"}
    api_src = (SRC / "api.py").read_text(encoding="utf-8")
    assert "/missions" not in api_src


def test_snapshot_helper_matches_route():
    raw = snapshot()
    via = contention_snapshot_route()
    assert raw["location"]["probe"] == via["location"]["probe"]
    assert raw["dock"]["outbound_blocked"] == via["dock"]["outbound_blocked"]
