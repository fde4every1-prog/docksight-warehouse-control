"""Observe-only dashboard. No OT. No fleet POST."""

from pathlib import Path

from warehouse_control.api import UI_FILE, app, dashboard, dashboard_snapshot
from warehouse_control.api import health

SRC = Path(__file__).resolve().parents[1] / "src" / "warehouse_control"


def test_dashboard_routes_are_get_only():
    paths = {getattr(r, "path", "") for r in app.routes}
    methods = []
    for r in app.routes:
        methods.extend(getattr(r, "methods", set()) or [])
    assert "/" in paths
    assert "/ui" in paths
    assert "/dashboard/snapshot" in paths
    assert "POST" not in methods
    assert "/missions" not in paths


def test_dashboard_html_is_observe_only():
    html = UI_FILE.read_text(encoding="utf-8")
    assert "RBT-0020" in html
    assert "SKU-01146" in html
    assert "physical_control" in html
    assert "method: 'POST'" not in html
    assert 'method: "POST"' not in html
    assert "/missions" not in html
    page = dashboard()
    assert page.path == UI_FILE


def test_dashboard_snapshot_observe_only():
    body = dashboard_snapshot()
    assert body["physical_control"] == "disabled"
    assert body["assign_supported"] is False
    assert body["health"]["physical_control"] == "disabled"
    assert health()["physical_control"] == "disabled"
    assert body["safety_preview"]["decision"] == "DENY"
    assert body["order_968"]["completable"] is False
    api_src = (SRC / "api.py").read_text(encoding="utf-8")
    assert "/missions" not in api_src
    assert "robotId" not in api_src
