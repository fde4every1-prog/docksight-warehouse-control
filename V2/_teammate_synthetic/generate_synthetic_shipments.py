#!/usr/bin/env python3
"""Generate synthetic shipment records for the warehouse data set.

This script is deliberately tolerant of being run from any working directory in
this repository. All file paths are resolved relative to the project root and the
script directory so the data generation remains reproducible.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
RAW_SHIPMENTS_PATH = ROOT / "data" / "raw" / "shipments.csv"
ORDERS_PATH = SCRIPTS_DIR / "synthetic_orders_7000.csv"


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    shipments_df = pd.read_csv(RAW_SHIPMENTS_PATH)
    orders_df = pd.read_csv(ORDERS_PATH)
    return shipments_df, orders_df


def same_values(left: pd.Series, right: pd.Series) -> bool:
    if len(left) != len(right):
        return False
    return bool((left.reset_index(drop=True) == right.reset_index(drop=True)).all())


def main() -> None:
    shipments_df, orders_df = load_data()

    print("shipments_df shape:", shipments_df.shape)
    print("shipments_df columns:", shipments_df.columns.tolist())
    print(shipments_df.head(5))

    print("\norders_df shape:", orders_df.shape)
    print("orders_df columns:", orders_df.columns.tolist())
    print(orders_df.head(5))

    print("orders_df order_id min and max:", orders_df["order_id"].min(), orders_df["order_id"].max())
    print("shipments_df order_id min and max:", shipments_df["order_id"].min(), shipments_df["order_id"].max())
    print("Do all order_ids in shipments match orders_df?:", same_values(shipments_df["order_id"], orders_df["order_id"]))
    print("Do warehouse_ids match?:", same_values(shipments_df["warehouse_id"], orders_df["warehouse_id"]))
    print("Do planned_departure match carrier_cutoff?:", same_values(shipments_df["planned_departure"], orders_df["carrier_cutoff"]))

    print("shipments_df tms_status value counts:")
    print(shipments_df["tms_status"].value_counts(dropna=False))
    print("\nCarrier value counts:")
    print(shipments_df["carrier"].value_counts(dropna=False))
    print("\nactual_departure non-null count:", shipments_df["actual_departure"].notna().sum())
    print("Sample of non-null actual_departure:")
    print(shipments_df[shipments_df["actual_departure"].notna()].head(5))

    print("Shipments head 10:")
    print(shipments_df.head(10))

    print("\ntms_status distribution:")
    print(shipments_df["tms_status"].value_counts())

    print("\nCarrier distribution:")
    print(shipments_df["carrier"].value_counts())

    merged = orders_df.merge(shipments_df, on="order_id")
    print("\noms_status vs tms_status:")
    print(pd.crosstab(merged["oms_status"], merged["tms_status"]))

    merged_existing = orders_df.merge(shipments_df, on="order_id")
    non_null_act = merged_existing[merged_existing["actual_departure"].notna()].copy()
    non_null_act["created_dt"] = pd.to_datetime(non_null_act["created_at"])
    non_null_act["actual_dt"] = pd.to_datetime(non_null_act["actual_departure"])
    non_null_act["diff_hours"] = (non_null_act["actual_dt"] - non_null_act["created_dt"]).dt.total_seconds() / 3600

    print("Existing actual_departure diff_hours summary:")
    print(non_null_act["diff_hours"].describe())

    print("Seconds in shipments planned_departure:")
    print(shipments_df["planned_departure"].str[-2:].value_counts())
    print("Seconds in shipments actual_departure:")
    print(shipments_df["actual_departure"].dropna().str[-2:].value_counts())
    print("Seconds in orders created_at:")
    print(orders_df["created_at"].str[-2:].value_counts())

    np.random.seed(42)
    created_dt = pd.to_datetime(orders_df["created_at"])
    delta_minutes = np.random.randint(421, 540, size=len(orders_df))
    actual_dt = created_dt + pd.to_timedelta(delta_minutes, unit="m")
    diff_hours = (actual_dt - created_dt).dt.total_seconds() / 3600

    print("Min diff_hours:", diff_hours.min())
    print("Max diff_hours:", diff_hours.max())
    print("All > 7 hours?:", (diff_hours > 7.0).all())
    print("All < 9 hours?:", (diff_hours < 9.0).all())

    print("orders_df length:", len(orders_df))
    print("shipments_df length:", len(shipments_df))
    print("Is order_id column identical?:", same_values(orders_df["order_id"], shipments_df["order_id"]))
    print("Is warehouse_id column identical?:", same_values(orders_df["warehouse_id"], shipments_df["warehouse_id"]))
    print("Is carrier_cutoff identical to planned_departure?:", same_values(orders_df["carrier_cutoff"], shipments_df["planned_departure"]))

    shipments_3500 = shipments_df.copy()
    created_dt_3500 = pd.to_datetime(orders_df["created_at"])
    np.random.seed(42)
    delta_min_3500 = np.random.randint(421, 540, size=len(orders_df))
    actual_dt_3500 = created_dt_3500 + pd.to_timedelta(delta_min_3500, unit="m")
    shipments_3500["actual_departure"] = actual_dt_3500.dt.strftime("%Y-%m-%dT%H:%M:00")

    diff_3500 = (actual_dt_3500 - created_dt_3500).dt.total_seconds() / 3600
    assert (diff_3500 > 7.0).all() and (diff_3500 < 9.0).all(), "3500 bounds failed"

    shipments_path = SCRIPTS_DIR / "shipments.csv"
    shipments_3500.to_csv(shipments_path, index=False)
    print(f"{shipments_path.name} (3,500 records) generated. Head:")
    print(shipments_3500.head(5))

    synth_orders_df = pd.read_csv(ORDERS_PATH)
    print("\nsynth_orders_df len:", len(synth_orders_df))

    created_dt_7000 = pd.to_datetime(synth_orders_df["created_at"])
    delta_min_7000 = np.random.randint(421, 540, size=len(synth_orders_df))
    actual_dt_7000 = created_dt_7000 + pd.to_timedelta(delta_min_7000, unit="m")

    carrier_dist = shipments_df["carrier"].value_counts(normalize=True)
    tms_dist = shipments_df["tms_status"].value_counts(normalize=True)

    synth_carriers = np.random.choice(carrier_dist.index, size=len(synth_orders_df), p=carrier_dist.values)
    synth_tms = np.random.choice(tms_dist.index, size=len(synth_orders_df), p=tms_dist.values)

    planned_after_actual = np.random.rand(len(synth_orders_df)) < 0.623
    planned_delay_minutes = np.random.randint(5, 91, size=len(synth_orders_df))
    early_offset_minutes = np.random.randint(5, 46, size=len(synth_orders_df))

    planned_dt_7000 = actual_dt_7000.copy()
    planned_dt_7000[planned_after_actual] += pd.to_timedelta(planned_delay_minutes[planned_after_actual], unit="m")
    planned_dt_7000[~planned_after_actual] -= pd.to_timedelta(early_offset_minutes[~planned_after_actual], unit="m")

    shipments_7000 = pd.DataFrame(
        {
            "shipment_id": [f"SHP-{i:06d}" for i in range(100001, 100001 + len(synth_orders_df))],
            "order_id": synth_orders_df["order_id"],
            "warehouse_id": synth_orders_df["warehouse_id"],
            "tms_status": synth_tms,
            "carrier": synth_carriers,
            "planned_departure": planned_dt_7000.dt.strftime("%Y-%m-%dT%H:%M:00"),
            "actual_departure": actual_dt_7000.dt.strftime("%Y-%m-%dT%H:%M:00"),
        }
    )

    diff_7000 = (actual_dt_7000 - created_dt_7000).dt.total_seconds() / 3600
    assert (diff_7000 > 7.0).all() and (diff_7000 < 9.0).all(), "7000 bounds failed"

    planned_gt_actual_ratio = (shipments_7000["planned_departure"] > shipments_7000["actual_departure"]).mean()
    print(f"planned_departure > actual_departure on {planned_gt_actual_ratio:.2%} of records")

    synthetic_shipments_path = SCRIPTS_DIR / "synthetic_shipments_7000.csv"
    shipments_7000.to_csv(synthetic_shipments_path, index=False)
    print(f"{synthetic_shipments_path.name} (7,000 records) generated. Head:")
    print(shipments_7000.head(5))


if __name__ == "__main__":
    main()