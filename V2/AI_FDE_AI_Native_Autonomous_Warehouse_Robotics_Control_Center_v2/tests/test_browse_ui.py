"""Order-first browse UI. Observe-only. Robot joins via tasks; SKU does not."""

from pathlib import Path

from warehouse_control.api import BROWSE_UI_FILE, app, browse_ui
from warehouse_control.browse import featured_catalog, order_browse, robot_on_order

SRC = Path(__file__).resolve().parents[1] / "src" / "warehouse_control"


def test_browse_routes_are_get_only():
    paths = {getattr(r, "path", "") for r in app.routes}
    methods = []
    for r in app.routes:
        methods.extend(getattr(r, "methods", set()) or [])
    assert "/browse" in paths
    assert "/lookup/featured" in paths
    assert "/orders/{order_id}/browse" in paths
    assert "POST" not in methods


def test_browse_html_is_observe_only():
    html = BROWSE_UI_FILE.read_text(encoding="utf-8")
    assert "ORD-009999" in html
    assert "assigned_robot" in html
    assert "method: 'POST'" not in html
    assert "/missions" not in html
    page = browse_ui()
    assert page.path == BROWSE_UI_FILE


def test_featured_lists_robot_next_not_sku_on_order():
    cat = featured_catalog()
    assert cat["list_next"] == "robot_id"
    ids = [o["order_id"] for o in cat["orders"]]
    assert "ORD-009999" in ids
    assert "ORD-000004" in ids
    assert cat["physical_control"] == "disabled"


def test_happy_order_browse_has_robot_not_sku_line():
    body = order_browse("ORD-009999")
    assert body["order"]["oms_status"] == "SHIPPED"
    assert body["reconcile"]["completable"] is True
    assert body["list_next"] == "robot_id"
    assert any(r["robot_id"] == "RBT-0012" for r in body["robots"])
    assert body["sku_options"]
    assert body["sku_options"][0]["sku"] in {"SKU-09999", "SKU-01146"}
    assert body["assign_supported"] is False


def test_delayed_order_browse_robots_from_tasks():
    body = order_browse("ORD-000004")
    assert body["cutoff"]["tms_status"] == "DELAYED"
    assert body["reconcile"]["completable"] is False
    assert any(r["robot_id"] == "RBT-0644" for r in body["robots"])
    assert body["sku_options"] == []


def test_robot_on_order_does_not_assign():
    data = robot_on_order("ORD-000004", "RBT-0644")
    assert data["eligibility"] == "INELIGIBLE"
    assert data["assign_supported"] is False
    assert data["physical_control"] == "disabled"
    api_src = (SRC / "api.py").read_text(encoding="utf-8")
    assert "/missions" not in api_src
