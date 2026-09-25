import pandas as pd
import pytest

from .features import (
    ALLOWED_INPUTS,
    CATEGORICAL,
    NUMERIC,
    REQUIRED,
    build_features,
    deterministic_holdout,
    feature_columns,
    load_observations,
)
from .train import (
    TEST_END,
    TEST_START,
    TRAIN_END,
    VALIDATION_END,
    VALIDATION_START,
    candidate_rows,
)


def _frame(days: int = 40) -> pd.DataFrame:
    rows = []
    for robot in ("A", "B"):
        for day, date in enumerate(pd.date_range("2026-01-01", periods=days)):
            row = {
                "robot_id": robot,
                "observation_date": date,
                "failure_event": int(robot == "A" and day == 35),
            }
            row.update({column: float(day) for column in NUMERIC})
            rows.append(row)
    return pd.DataFrame(rows)


def test_features_use_trailing_data_and_strictly_future_label():
    result = build_features(_frame())
    row = result[(result.robot_id == "A") & (result.observation_date == "2026-01-29")].iloc[0]
    assert not row["history_eligible"]
    row = result[(result.robot_id == "A") & (result.observation_date == "2026-01-30")].iloc[0]
    assert row["history_eligible"]
    assert row["operating_hours_mean_7d"] == pytest.approx(26.0)
    assert row["operating_hours_trend_7d"] == pytest.approx(1.0)
    assert row["target_next_7d"] == 1
    failure_day = result[(result.robot_id == "A") & (result.observation_date == "2026-02-05")].iloc[0]
    assert pd.isna(failure_day["target_next_7d"])
    assert result[result.robot_id == "A"].tail(7)["target_next_7d"].isna().all()


def test_robot_holdout_is_stable_and_sized():
    ids = pd.Series([f"R-{value:03d}" for value in range(100)])
    assert deterministic_holdout(ids) == deterministic_holdout(ids.sample(frac=1, random_state=2))
    assert len(deterministic_holdout(ids)) == 15


def test_day_seven_included_day_eight_excluded_and_robots_isolated():
    frame = _frame(45)
    frame.loc[
        (frame.robot_id == "A") & (frame.observation_date == "2026-02-07"),
        "failure_event",
    ] = 1
    frame.loc[
        (frame.robot_id == "A") & (frame.observation_date == "2026-02-05"),
        "failure_event",
    ] = 0
    result = build_features(frame)
    a = result[result.robot_id == "A"].set_index("observation_date")
    b = result[result.robot_id == "B"].set_index("observation_date")
    assert a.loc["2026-01-31", "target_next_7d"] == 1  # exactly t+7
    assert a.loc["2026-01-30", "target_next_7d"] == 0  # event is t+8
    assert b.loc["2026-01-31", "target_next_7d"] == 0
    assert a.tail(7)["target_next_7d"].isna().all()


def _valid_csv_frame(days=3):
    rows = []
    for day, date in enumerate(pd.date_range("2026-01-01", periods=days)):
        row = {
            "observation_date": date.strftime("%Y-%m-%d"),
            "robot_id": "R1",
            "warehouse_id": "W1",
            "robot_type": "AMR",
            "vendor": "Vendor",
            "failure_event": 0,
            "failure_type": None,
            "downtime_hours": 0.0,
        }
        row.update({column: float(day + 1) for column in NUMERIC})
        rows.append(row)
    return pd.DataFrame(rows, columns=REQUIRED)


@pytest.mark.parametrize("mutation,match", [
    (lambda frame: frame.drop(index=1), "Date gap"),
    (lambda frame: pd.concat([frame, frame.iloc[[0]]]), "Duplicate"),
])
def test_loader_rejects_date_gaps_and_duplicates(tmp_path, mutation, match):
    path = tmp_path / "data.csv"
    mutation(_valid_csv_frame()).to_csv(path, index=False)
    with pytest.raises(ValueError, match=match):
        load_observations(path)


@pytest.mark.parametrize("column,value,match", [
    ("temperature_c", float("inf"), "Non-finite"),
    ("failure_event", 2, "binary"),
])
def test_loader_rejects_invalid_numeric_and_target(tmp_path, column, value, match):
    frame = _valid_csv_frame()
    frame.loc[0, column] = value
    path = tmp_path / "data.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match=match):
        load_observations(path)


def test_feature_contract_excludes_forbidden_fields():
    forbidden = {
        "firmware", "health_status", "charger_state",
        "charger_maintenance_state", "days_since_maintenance",
        "maintenance_due_days", "failure_event", "failure_type", "downtime_hours",
    }
    assert set(feature_columns()).isdisjoint(forbidden)
    assert set(feature_columns()) == set(CATEGORICAL + NUMERIC) | {
        f"{column}_{suffix}"
        for column in NUMERIC
        for suffix in ("mean_7d", "mean_30d", "trend_7d")
    }
    assert set(ALLOWED_INPUTS).isdisjoint(forbidden)


def test_chronological_partitions_are_purged_and_censored():
    frame = _frame(365)
    frame["observation_date"] = pd.date_range("2025-09-22", periods=365).tolist() * 2
    featured = build_features(frame.sort_values(["robot_id", "observation_date"]))
    train = candidate_rows(featured, None, TRAIN_END)
    validation = candidate_rows(featured, VALIDATION_START, VALIDATION_END)
    test = candidate_rows(featured, TEST_START, TEST_END)
    assert train.observation_date.max() == TRAIN_END
    assert validation.observation_date.min() == VALIDATION_START
    assert validation.observation_date.max() == VALIDATION_END
    assert test.observation_date.min() == TEST_START
    assert test.observation_date.max() == TEST_END
    assert train.observation_date.max() < validation.observation_date.min()
    assert validation.observation_date.max() < test.observation_date.min()