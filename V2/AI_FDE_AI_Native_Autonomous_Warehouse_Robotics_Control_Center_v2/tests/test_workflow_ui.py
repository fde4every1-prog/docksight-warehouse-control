"""Supervisor workflow UI. Observe-only. Two scenarios. JSON hidden by default."""

from warehouse_control.api import WORKFLOW_UI_FILE, app, workflow_snapshot_route, workflow_ui
from warehouse_control.workflow import workflow_snapshot


def test_workflow_routes_get_only():
    paths = {getattr(r, "path", "") for r in app.routes}
    methods = []
    for r in app.routes:
        methods.extend(getattr(r, "methods", set()) or [])
    assert "/workflow" in paths
    assert "/workflow/snapshot" in paths
    assert "POST" not in methods


def test_workflow_html_hides_json_and_blocks_assign():
    html = WORKFLOW_UI_FILE.read_text(encoding="utf-8")
    assert "Hide raw data" in html or "Show raw data" in html
    assert "raw-wrap" in html
    assert "Assign (blocked)" in html
    assert "method: 'POST'" not in html
    assert "/missions" not in html
    assert workflow_ui().path == WORKFLOW_UI_FILE


def test_workflow_snapshot_two_scenarios():
    snap = workflow_snapshot_route()
    assert snap["physical_control"] == "disabled"
    assert snap["persona"] == "Warehouse supervisor"
    assert snap["assign_supported"] is False
    green = snap["scenarios"]["green"]
    broken = snap["scenarios"]["broken"]
    assert green["order_id"] == "ORD-009999"
    assert green["complete"] is True
    assert green["decision_kind"] == "done"
    assert [s["id"] for s in green["stages"]] == ["order", "stock", "work", "robot", "zone", "truck"]
    assert green["stages"][0]["status"] == "ok"
    assert green["stages"][5]["status"] == "ok"
    assert broken["order_id"] == "ORD-000004"
    assert broken["complete"] is False
    assert broken["decision_kind"] == "stop"
    assert broken["stages"][2]["status"] == "stop"
    assert broken["stages"][3]["status"] == "stop"
    assert broken["stages"][5]["status"] == "stop"
