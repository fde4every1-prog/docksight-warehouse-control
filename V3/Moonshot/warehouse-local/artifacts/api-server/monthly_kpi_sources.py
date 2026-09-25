"""Immutable input loading and deterministic isolated September scenario.

Rows exist only in this module's in-memory bundle, never in operational stores.
"""
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import zipfile

from monthly_kpi_metrics import timestamp, unique

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "brownfield/AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2/data/raw"
ARCHIVE = ROOT.parent.parent / "attached_assets/Synthetic_Data_1789961144297.zip"
NAMES = ("orders", "shipments", "tasks", "inventory_snapshot", "robots")
VERSION = "september-scenario-v2"
# Keep deterministic non-duration assignments stable across this recalibration.
SCORE_VERSION = "september-scenario-v1"
TARGET_CYCLE_HOURS = 7.38


def score(identity):
    return int(hashlib.sha256((SCORE_VERSION + identity).encode()).hexdigest()[:12], 16) % 10000


def audit(rows):
    date_fields = ("created_at", "planned_departure", "actual_departure")
    ranges = {}
    for field in date_fields:
        if rows and field in rows[0]:
            dates = [t for row in rows if (t := timestamp(row.get(field))) is not None]
            ranges[field] = {"start": min(dates).isoformat() if dates else None,
                             "end": max(dates).isoformat() if dates else None,
                             "missing_or_invalid": len(rows) - len(dates)}
    return {
        "rows": len(rows),
        "date_ranges": ranges,
        "enums": {field: sorted({row.get(field, "") for row in rows})
                  for field in ("task_type", "wes_status", "fleet_status", "safety_cert_status", "connectivity")
                  if rows and field in rows[0]},
    }


def valid_august_pairs(source):
    """Apply the baseline's unambiguous, same-warehouse, nonnegative join rules."""
    orders, _ = unique(source["orders"], ("order_id",))
    shipments, _ = unique(source["shipments"], ("shipment_id",))
    by_order = defaultdict(list)
    for shipment in shipments:
        by_order[shipment.get("order_id")].append(shipment)
    pairs = []
    for order in orders:
        created = timestamp(order.get("created_at"))
        joined = by_order[order["order_id"]]
        if not created or created.strftime("%Y-%m") != "2026-08" or len(joined) != 1:
            continue
        shipment = joined[0]
        actual = timestamp(shipment.get("actual_departure"))
        if (not actual or actual < created
                or actual > datetime(2026, 9, 22, 23, 59, 59, tzinfo=timezone.utc)
                or shipment.get("warehouse_id") != order.get("warehouse_id")):
            continue
        pairs.append((order, shipment, actual - created))
    return pairs


def duration_multiplier(pairs):
    total_hours = sum(duration.total_seconds() / 3600 for _, _, duration in pairs)
    if not total_hours:
        raise ValueError("September calibration requires positive valid August durations")
    return TARGET_CYCLE_HOURS * len(pairs) / total_hours


def generate(source):
    """New identities and assumed relationships; original rows are never modified."""
    result = {name: [] for name in NAMES}
    pairs = valid_august_pairs(source)
    multiplier = duration_multiplier(pairs)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for order, shipment, duration in pairs:
        key = order["order_id"]
        arrival = start + timedelta(minutes=score(key) / 10000 * (29 * 24 * 60))
        departure = arrival + duration * multiplier
        planned = departure + timedelta(minutes=30 if score(key + "ontime") < 9700 else -30)
        result["orders"].append({**order, "order_id": "SCN-" + key, "created_at": arrival.isoformat(),
                                  "carrier_cutoff": planned.isoformat(), "oms_status": "SHIPPED", "wms_status": "SHIPPED"})
        result["shipments"].append({**shipment, "order_id": "SCN-" + key,
            "shipment_id": "SCN-" + shipment["shipment_id"], "actual_departure": departure.isoformat(),
            "planned_departure": planned.isoformat(), "tms_status": "DEPARTED"})
    for row in source["tasks"]:
        created = timestamp(row.get("created_at"))
        if not created or created.month != 8:
            continue
        key = row["task_id"]
        status = "BLOCKED" if score(key) < 350 else "COMPLETE"
        result["tasks"].append({**row, "task_id": "SCN-" + key, "order_id": "SCN-" + row["order_id"],
            "created_at": (start + timedelta(minutes=score(key + "date") / 10000 * 30 * 24 * 60)).isoformat(),
            "wes_status": status, "fleet_status": "FAILED" if status == "BLOCKED" else "COMPLETE"})
    for row in source["inventory_snapshot"]:
        copy = dict(row)
        if score("|".join(row[k] for k in ("warehouse_id", "sku", "location"))) < 9850:
            copy.update(erp_qty=row["wms_qty"], vision_qty=row["wms_qty"])
        result["inventory_snapshot"].append(copy)
    for row in source["robots"]:
        copy = dict(row)
        if row["safety_cert_status"] == "EXPIRED" and score(row["robot_id"]) < 9000:
            copy["safety_cert_status"] = "VALID"
        result["robots"].append(copy)
    return result


@lru_cache(maxsize=1)
def bundle():
    source, evidence = {}, {}
    for name in NAMES:
        path = RAW / f"{name}.csv"
        raw = path.read_bytes()
        source[name] = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        evidence[name] = {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(),
                          **audit(source[name]), "headers": list(source[name][0])}
    archive_audit = {"used_in_metrics": False, "reason": "Separate generated benchmark population; not blended with original observations"}
    if ARCHIVE.exists():
        archive_audit["sha256"] = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive_ids = []
            for name in ("synthetic_orders_7000.csv", "synthetic_shipments_7000.csv"):
                rows = list(csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8")))
                archive_ids.append({r["order_id"] for r in rows})
                archive_audit[name] = {**audit(rows), "unique_order_ids": len(archive_ids[-1]),
                    "missing_actual_departures": sum(not r.get("actual_departure") for r in rows) if "shipments" in name else None}
            archive_audit["matched_unique_order_ids"] = len(archive_ids[0] & archive_ids[1])
            archive_audit["unmatched_unique_order_ids"] = len(archive_ids[0] ^ archive_ids[1])
    generated = generate(source)
    manifest = {"version": VERSION, "source_records": evidence, "archive_benchmark": archive_audit,
        "assumed_baselines": {"inventory_snapshot": "Undated snapshot assigned to August for illustration only",
                             "robots": "Undated snapshot assigned to August for illustration only"},
        "generated_records": {name: len(rows) for name, rows in generated.items()},
        "generation": {"duration_multiplier": duration_multiplier(valid_august_pairs(source)),
                       "target_cycle_hours": TARGET_CYCLE_HOURS, "score_version": SCORE_VERSION,
                       "on_time_threshold": 9700, "hash_modulus": 10000,
                       "inventory_alignment_threshold": 9850, "task_failure_threshold": 350,
                       "expired_certificate_repair_threshold": 9000}}
    return source, generated, manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Print isolated KPI audit JSON; never writes operational stores.")
    parser.add_argument("--include-records", action="store_true", help="Include immutable source and generated row-level records")
    args = parser.parse_args()
    source, generated, manifest = bundle()
    output = {"manifest": manifest}
    if args.include_records:
        output.update(source_records=source, generated_records=generated,
                      assumed_baseline_records={name: source[name] for name in ("inventory_snapshot", "robots")})
    print(json.dumps(output, sort_keys=True, indent=2))