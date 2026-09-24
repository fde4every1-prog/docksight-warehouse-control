"""Separately labelled deterministic demo; never substituted for live evidence."""
from datetime import datetime, timedelta, timezone


def synthetic_snapshot():
    now = datetime.now(timezone.utc)
    zones = [{"id": f"DC-01-Z{i:02d}", "label": f"DC-01-Z{i:02d}", "x": 60 + ((i-1)%4)*245,
              "y": 70 + ((i-1)//4)*185, "width": 190, "height": 125,
              "mapping": "synthetic_demo"} for i in range(1, 13)]
    nodes = [{"id": z["id"], "x": z["x"]+95, "y": z["y"]+62, "zone_id": z["id"]} for z in zones]
    nodes.append({"id": "CONVEYOR", "x": 1160, "y": 350, "zone_id": None})
    edges = [{"from": zones[i]["id"], "to": zones[i+1]["id"]} for i in range(11)]
    edges.append({"from": zones[-1]["id"], "to": "CONVEYOR"})
    robots = [{"id": f"DEMO-R{i}", "source_id": f"DEMO-R{i}", "type": "AMR", "capacity_kg": 100,
               "battery_percent": 90, "state": "idle", "available": True,
               "capabilities": ["pick", "transfer"], "eligible": True, "exclusion_reasons": [],
               "start_node": zones[i-1]["id"], "provenance": {"source": "synthetic_demo"}}
              for i in range(1, 7)]
    inventory = [{"id": i, "source_id": f"DEMO-BIN-{i}", "source_row_index": i, "sku": f"DEMO-SKU-{i}",
                  "location": f"DC-01-Z{i:02d}-B001", "zone": f"DC-01-Z{i:02d}",
                  "weight_kg": float(i), "available_unreserved_qty": 20,
                  "quantity_semantics": "synthetic_demo"} for i in range(1, 7)]
    return {"warehouse_id": "DC-01", "mode": "synthetic_demo",
            "map": {"width": 1220, "height": 700, "zones": zones, "nodes": nodes, "edges": edges,
                    "conveyor": {"id": "CONVEYOR-01", "node_id": "CONVEYOR", "label": "Conveyor receipt"},
                    "geometry_provenance": "Synthetic demo geometry"},
            "robots": robots, "selected_robot_ids": [r["id"] for r in robots], "inventory": inventory,
            "blockers": [], "clock": {"at": now.isoformat().replace("+00:00", "Z"), "timezone": "UTC",
                                     "source": "synthetic_demo_clock"},
            "assumptions": ["Separately labelled synthetic demo; not live operational evidence.",
                            "All eligible demo robots are server-selected; selection is not capped at five."]}