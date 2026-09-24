"""Detached synthetic fixtures. No clock, database, or operational imports."""


def scenario():
    nodes = [
        {"id": "HOME", "x": 70, "y": 280, "zone": "A"},
        {"id": "A1", "x": 180, "y": 280, "zone": "A"},
        {"id": "A2", "x": 240, "y": 280, "zone": "A"},
        {"id": "A3", "x": 300, "y": 280, "zone": "A"},
        {"id": "TRANSFER", "x": 420, "y": 280, "zone": "TRANSFER"},
        {"id": "PACK", "x": 540, "y": 280, "zone": "PACK"},
        {"id": "DOCK", "x": 660, "y": 280, "zone": "STAGE"},
    ]
    specs = [
        ("URGENT", "A1", 1, 180),
        ("NEAR-1", "A1", 2, 900),
        ("NEAR-2", "A2", 2, 900),
        ("NEAR-3", "A3", 2, 900),
        ("HEAVY", "A3", 20, 1200),
    ]
    return {
        "scenario_id": "dc01-synthetic-v1-seed60",
        "warehouse_id": "DC-01", "seed": 60,
        "clock_start": "2026-06-01T09:00:00Z",
        "source": "detached_synthetic",
        "assumptions": [
            "Synthetic map, stock, readiness and capacities; not a surveyed floor plan.",
            "Sandbox only: no live reads, writes, reservations or physical equipment control.",
            "Independent fixed replay clock; playback speed never changes results.",
            "Pick and move each cost 45 + 22.5*(n-1) seconds; pack_feed and stage cost 45 per order.",
            "50% reduction on each additional order, not on the whole batch; not observed savings.",
            "Graph routes visualize service time; travel time is not added.",
            "Baseline adapts fulfillment_v2 executor_once/_choose: cutoff, sub-order, stage, task ordering.",
            "One line/sub-order per order; fixed readiness; no failures, charging, labor pool or executor cadence.",
            "Exclusive pack and stage assets model the common downstream bottleneck.",
        ],
        "map": {
            "width": 740, "height": 440,
            "boundary": [{"x": 20, "y": 20}, {"x": 720, "y": 20},
                         {"x": 720, "y": 420}, {"x": 20, "y": 420}],
            "zones": [
                {"id": "A", "label": "Nearby picking / racks", "x": 40, "y": 60, "width": 310, "height": 320},
                {"id": "TRANSFER", "label": "Transfer", "x": 370, "y": 60, "width": 100, "height": 320},
                {"id": "PACK", "label": "Pack", "x": 490, "y": 60, "width": 100, "height": 320},
                {"id": "STAGE", "label": "Outbound staging", "x": 610, "y": 60, "width": 100, "height": 320},
            ],
            "nodes": nodes,
            "edges": [{"from": a["id"], "to": b["id"]} for a, b in zip(nodes, nodes[1:])],
            "bins": [{"id": "BIN-" + oid, "node_id": node, "zone": "A",
                      "sku": "SKU-" + oid, "stock": 4} for oid, node, _, _ in specs],
            "destinations": {"pick": "HOME", "transfer": "TRANSFER",
                             "pack_feed": "PACK", "stage": "DOCK"},
        },
        "skus": [{"id": "SKU-" + oid, "unit_weight_kg": weight} for oid, _, weight, _ in specs],
        "orders": [
            {"id": oid, "sub_order_id": "SUB-" + oid, "tote_id": "TOTE-" + oid,
             "status": "queued", "cutoff_seconds": cutoff,
             "lines": [{"id": "LINE-" + oid, "sku": "SKU-" + oid,
                        "quantity": 1, "bin_id": "BIN-" + oid}]}
            for oid, _, _, cutoff in specs
        ],
        "robots": [
            {"id": rid, "warehouse_id": "DC-01", "type": "AMR",
             "start_node": "HOME", "available": ready, "battery_percent": 85,
             "capacity_kg": 20, "capabilities": ["pick", "move"],
             "blocked_reason": "" if ready else "Synthetic maintenance hold"}
            for rid, ready in [("R-01", True), ("R-02", True), ("R-03", False)]
        ],
        "assets": [
            {"id": "PACK-01", "warehouse_id": "DC-01", "stage": "pack_feed", "node_id": "PACK", "available": True},
            {"id": "DOCK-01", "warehouse_id": "DC-01", "stage": "stage", "node_id": "DOCK", "available": True},
        ],
        "constraints": {"base_duration_seconds": 45, "max_batch_size": 3, "max_proximity": 180},
    }