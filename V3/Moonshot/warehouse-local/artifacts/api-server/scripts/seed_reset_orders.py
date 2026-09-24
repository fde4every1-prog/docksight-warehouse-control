"""Create the two reset-test orders through real development HTTP intake.

Reruns reuse stable request IDs and never reset data. Run only after the
separately authorized offline reset and API restart.
"""

import argparse
import json
import uuid
from urllib.parse import urlparse
from urllib.request import Request, urlopen


TEST_ORDERS = [
    {
        "service": "Standard",
        "lines": [{"sku": "SKU-00911", "quantity": 1}],
        "request_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "warehouse-v2-reset-standard")),
    },
    {
        "service": "Next_Day",
        "lines": [
            {"sku": "SKU-00499", "quantity": 1},
            {"sku": "SKU-01131", "quantity": 1},
        ],
        "request_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "warehouse-v2-reset-next-day")),
    },
]


def request(base_url, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(
        base_url.rstrip("/") + path,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST" if payload is not None else "GET",
    ), timeout=30) as response:
        return json.load(response)


def seed(base_url):
    hostname = urlparse(base_url).hostname or ""
    if hostname not in {"localhost", "127.0.0.1"} and not hostname.endswith(".replit.dev"):
        raise RuntimeError("Test seeding is restricted to a development host")
    expected = {payload["request_id"] for payload in TEST_ORDERS}
    existing = request(base_url, "/api/bazaar/orders?limit=100")
    state = request(base_url, "/api/fulfillment/state")
    allowed_sources = {row["id"] for row in existing["orders"]}
    if existing["total"] > 2 or any(
        row["request_id"] not in expected
        for row in existing["orders"]
    ) or any(row["source_order_id"] not in allowed_sources for row in state["orders"]):
        raise RuntimeError("Unrelated orders exist; refusing to add reset-test orders")
    for payload in TEST_ORDERS:
        # A lost HTTP response is safe: rerunning submits the identical identity.
        created = request(base_url, "/api/bazaar/orders", payload)
        if created["delivery_status"] != "sent":
            raise RuntimeError(
                f"Order {created['id']} is {created['delivery_status']}; "
                "resolve handoff before rerunning"
            )
        receipt = request(base_url, f"/api/bazaar/orders/{created['id']}")
        print(json.dumps({
            "service": payload["service"],
            "bazaar_id": receipt["id"],
            "control_tower_id": receipt["control_tower_order_id"],
            "status": receipt["control_tower_status"],
            "lines": receipt["lines"],
        }))
    result = request(base_url, "/api/bazaar/orders?limit=100")
    state = request(base_url, "/api/fulfillment/state")
    if result["total"] != 2 or len(state["orders"]) != 2:
        raise RuntimeError("Expected exactly two orders in each app after seeding")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Development API origin")
    seed(parser.parse_args().base_url)