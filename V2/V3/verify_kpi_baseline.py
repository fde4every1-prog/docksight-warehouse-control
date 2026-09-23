"""Verify baseline KPI denominators from the V2 raw archive."""

import csv
from datetime import datetime
from pathlib import Path

RAW = Path(
    r"C:\Users\Administrator\AppData\Local\Temp\warehouse-repo3-inspect\warehouse-local"
    r"\artifacts\api-server\brownfield"
    r"\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2\data\raw"
)


def parse(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except ValueError:
        return None


def rows(name):
    with (RAW / name).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


orders = rows("orders.csv")
shipments = rows("shipments.csv")
print("orders.csv rows:", len(orders), "| cols:", list(orders[0])[:8])
print("shipments.csv rows:", len(shipments), "| cols:", list(shipments[0])[:8])

created = {}
for o in orders:
    oid = o.get("order_id") or o.get("id")
    created[oid] = parse(o.get("created_at"))

deltas = []
with_actual = 0
ontime = 0
for s in shipments:
    actual = parse(s.get("actual_departure"))
    planned = parse(s.get("planned_departure"))
    if actual is None:
        continue
    with_actual += 1
    if planned is not None and actual <= planned:
        ontime += 1
    oid = s.get("order_id")
    c = created.get(oid)
    if c is not None:
        deltas.append((actual - c).total_seconds() / 3600.0)

print("shipments with actual_departure:", with_actual)
print("shipments missing actual_departure:", len(shipments) - with_actual)
print("matched order+shipment pairs:", len(deltas))
if deltas:
    print("mean cycle time (h): %.2f" % (sum(deltas) / len(deltas)))
print("on-time count:", ontime, "-> %.2f%%" % (100.0 * ontime / with_actual))
