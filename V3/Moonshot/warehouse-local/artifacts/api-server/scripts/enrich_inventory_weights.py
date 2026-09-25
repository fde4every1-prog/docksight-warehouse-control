"""One-time, user-authorized synthetic weight enrichment of the inventory CSV."""

import csv
import io
import json
import random
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT / "brownfield"
    / "AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2"
    / "data/raw/inventory_snapshot.csv"
)
SEED = 20260918
RANGES = [(1, 25), (26, 100), (101, 250), (251, 500), (501, 1000), (1001, 1500)]


def main():
    original = SNAPSHOT.read_bytes()
    reader = csv.DictReader(io.StringIO(original.decode("utf-8"), newline=""))
    fields = reader.fieldnames
    rows = list(reader)
    if not fields or "sku" not in fields or not rows:
        raise ValueError("Expected a nonempty inventory CSV with a sku column")
    if "weight_kg" in fields:
        raise ValueError("Weights already exist; refusing to overwrite them")
    if any(not row["sku"].strip() for row in rows):
        raise ValueError("Every inventory row must have a SKU")

    rng = random.Random(SEED)
    weights = {sku: rng.randint(1, 1500) for sku in sorted({row["sku"] for row in rows})}
    enriched = [dict(row, weight_kg=str(weights[row["sku"]])) for row in rows]
    line_ending = "\r\n" if b"\r\n" in original else "\n"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=[*fields, "weight_kg"], lineterminator=line_ending)
    writer.writeheader()
    writer.writerows(enriched)
    result = buffer.getvalue()

    # Round-trip validation ensures the original data and row order are retained.
    decoded = list(csv.DictReader(io.StringIO(result, newline="")))
    assert len(decoded) == len(rows)
    assert [{key: row[key] for key in fields} for row in decoded] == rows
    assert all(1 <= int(row["weight_kg"]) <= 1500 for row in decoded)
    assert all(int(row["weight_kg"]) == weights[row["sku"]] for row in decoded)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=SNAPSHOT.parent,
            suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(result)
        if SNAPSHOT.read_bytes() != original:
            raise RuntimeError("Inventory changed during enrichment; refusing to replace it")
        temp_path.replace(SNAPSHOT)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()

    counts = [
        {"range_kg": f"{low}–{high}", "unique_skus": sum(low <= w <= high for w in weights.values())}
        for low, high in RANGES
    ]
    assert sum(item["unique_skus"] for item in counts) == len(weights)
    print(json.dumps({
        "column": "weight_kg", "inventory_rows": len(rows), "unique_skus": len(weights),
        "seed": SEED, "minimum_kg": min(weights.values()), "maximum_kg": max(weights.values()),
        "ranges": counts,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()