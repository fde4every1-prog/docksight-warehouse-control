"""The operational host must not expose the removed demo process route."""

import baseline_demo


def test_fulfillment_demo_route_is_unavailable_but_specification_remains():
    methods_by_path = {
        route.path: getattr(route, "methods", set()) for route in baseline_demo.app.routes
    }
    assert "/api/fulfillment/demo" not in methods_by_path
    assert "GET" in methods_by_path["/api/fulfillment/specification"]