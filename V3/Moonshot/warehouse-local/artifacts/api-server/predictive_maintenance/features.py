from __future__ import annotations

from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

IDENTITY = ["observation_date", "robot_id", "warehouse_id"]
CATEGORICAL = ["robot_type", "vendor"]
NUMERIC = [
    "operating_hours",
    "task_count",
    "distance_km",
    "payload_hours",
    "battery_soc_pct",
    "battery_soh_pct",
    "charge_cycles",
    "charging_minutes",
    "fault_count",
    "safety_event_count",
    "connectivity_loss_minutes",
    "temperature_c",
    "vibration_rms",
    "motor_current_a",
]
TARGETS = ["failure_event", "failure_type", "downtime_hours"]
ALLOWED_INPUTS = CATEGORICAL + NUMERIC
REQUIRED = IDENTITY + ALLOWED_INPUTS + TARGETS


def load_observations(path: str | Path) -> pd.DataFrame:
    """Load CSV or a ZIP containing exactly one CSV, then validate its panel."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            csvs = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csvs) != 1:
                raise ValueError(f"Expected exactly one CSV in archive, found {len(csvs)}")
            with archive.open(csvs[0]) as source:
                frame = pd.read_csv(source, usecols=lambda c: c in REQUIRED)
    else:
        frame = pd.read_csv(path, usecols=lambda c: c in REQUIRED)
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="raise")
    for column in NUMERIC + ["failure_event", "downtime_hours"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame[REQUIRED].isna().any().drop(TARGETS[1], errors="ignore").any():
        cols = frame.columns[frame.isna().any()].tolist()
        required_nulls = sorted(set(cols) - {"failure_type"})
        if required_nulls:
            raise ValueError(f"Nulls in required fields: {required_nulls}")
    if not np.isfinite(frame[NUMERIC + ["failure_event", "downtime_hours"]].to_numpy()).all():
        raise ValueError("Non-finite value in numeric fields")
    if frame.duplicated(["robot_id", "observation_date"]).any():
        raise ValueError("Duplicate robot/date rows")
    frame = frame.sort_values(["robot_id", "observation_date"], kind="stable").reset_index(drop=True)
    day_step = frame.groupby("robot_id", sort=False)["observation_date"].diff().dropna().dt.days
    if not day_step.eq(1).all():
        raise ValueError("Date gap or non-daily observation found within a robot history")
    if not frame["failure_event"].isin([0, 1]).all():
        raise ValueError("failure_event must be binary")
    return frame


def feature_columns() -> list[str]:
    numeric = NUMERIC + [f"{c}_mean_7d" for c in NUMERIC]
    numeric += [f"{c}_mean_30d" for c in NUMERIC]
    numeric += [f"{c}_trend_7d" for c in NUMERIC]
    return CATEGORICAL + numeric


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Create same-day and trailing features and the strictly future 7-day label."""
    out = frame.copy()
    grouped = out.groupby("robot_id", sort=False)
    for column in NUMERIC:
        group = grouped[column]
        out[f"{column}_mean_7d"] = group.transform(
            lambda s: s.rolling(7, min_periods=7).mean()
        )
        out[f"{column}_mean_30d"] = group.transform(
            lambda s: s.rolling(30, min_periods=30).mean()
        )
        out[f"{column}_trend_7d"] = (out[column] - group.shift(6)) / 6.0

    # Reverse rolling includes the current row; shift by one makes this t+1..t+7.
    future = (
        out.iloc[::-1]
        .groupby("robot_id", sort=False)["failure_event"]
        .transform(lambda s: s.rolling(7, min_periods=7).max())
        .iloc[::-1]
    )
    out["target_next_7d"] = future.groupby(out["robot_id"], sort=False).shift(-1)
    out["history_eligible"] = out[f"{NUMERIC[0]}_mean_30d"].notna()
    return out


def deterministic_holdout(robot_ids: pd.Series, fraction: float = 0.15) -> set[str]:
    """Stable robot holdout independent of Python's randomized hash seed."""
    import hashlib

    unique = sorted(robot_ids.astype(str).unique())
    ranked = sorted(unique, key=lambda value: hashlib.sha256(value.encode()).hexdigest())
    return set(ranked[: round(len(ranked) * fraction)])