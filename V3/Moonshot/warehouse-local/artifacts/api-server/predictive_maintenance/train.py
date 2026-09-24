from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

for variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[variable] = "2"

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from .features import (
    CATEGORICAL,
    NUMERIC,
    build_features,
    deterministic_holdout,
    feature_columns,
    load_observations,
)

MODEL_ID = "predictive-maintenance-next7-v1"
TRAIN_END = pd.Timestamp("2026-04-23")
VALIDATION_START = pd.Timestamp("2026-05-01")
VALIDATION_END = pd.Timestamp("2026-06-23")
TEST_START = pd.Timestamp("2026-07-01")
TEST_END = pd.Timestamp("2026-09-14")


def _json(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    raise TypeError(type(value).__name__)


def candidate_rows(featured: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp) -> pd.DataFrame:
    mask = featured["observation_date"].le(end)
    if start is not None:
        mask &= featured["observation_date"].ge(start)
    mask &= featured["history_eligible"] & featured["target_next_7d"].notna()
    mask &= featured["failure_event"].eq(0)
    return featured.loc[mask].copy()


def metrics(y: pd.Series, probability: np.ndarray, threshold: float) -> dict[str, float | int]:
    alert = probability >= threshold
    return {
        "rows": len(y),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "average_precision": float(average_precision_score(y, probability)),
        "pr_auc": float(average_precision_score(y, probability)),
        "roc_auc": float(roc_auc_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
        "threshold": float(threshold),
        "alert_rate": float(alert.mean()),
        "precision_at_threshold": float(precision_score(y, alert, zero_division=0)),
        "recall_at_threshold": float(recall_score(y, alert, zero_division=0)),
    }


def _models() -> dict[str, Pipeline]:
    all_numeric = [column for column in feature_columns() if column not in CATEGORICAL]
    logistic_transform = ColumnTransformer(
        [
            ("category", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("numeric", StandardScaler(), all_numeric),
        ]
    )
    tree_transform = ColumnTransformer(
        [
            (
                "category",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                CATEGORICAL,
            ),
            ("numeric", "passthrough", all_numeric),
        ]
    )
    return {
        "dummy_prevalence": Pipeline(
            [("transform", tree_transform), ("model", DummyClassifier(strategy="prior"))]
        ),
        "logistic_regression": Pipeline(
            [
                ("transform", logistic_transform),
                ("model", LogisticRegression(max_iter=300, C=1.0)),
            ]
        ),
        "hist_gradient_boosting": Pipeline(
            [
                ("transform", tree_transform),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=0.08,
                        max_iter=150,
                        max_leaf_nodes=31,
                        l2_regularization=1.0,
                        random_state=42017,
                    ),
                ),
            ]
        ),
    }


def event_metrics(
    candidates: pd.DataFrame, probabilities: np.ndarray, failures: pd.DataFrame, threshold: float
) -> dict[str, Any]:
    alerted = candidates.loc[probabilities >= threshold, ["robot_id", "observation_date"]]
    leads: list[int] = []
    detected = 0
    for event in failures.itertuples():
        prior = alerted[
            (alerted["robot_id"] == event.robot_id)
            & (alerted["observation_date"] < event.observation_date)
            & (alerted["observation_date"] >= event.observation_date - pd.Timedelta(days=7))
        ]
        if not prior.empty:
            detected += 1
            leads.append(int((event.observation_date - prior["observation_date"].min()).days))
    return {
        "events": len(failures),
        "events_detected": detected,
        "event_recall": detected / len(failures) if len(failures) else None,
        "median_lead_days": float(np.median(leads)) if leads else None,
        "definition": "A failure with a complete seven-day test opportunity is detected when at least one alert occurs 1-7 calendar days before it.",
    }


def _signal_rows(row: pd.Series) -> list[dict[str, Any]]:
    names = ["temperature_c", "vibration_rms", "motor_current_a", "battery_soh_pct",
             "task_count", "fault_count"]
    return [
        {
            "name": name,
            "value": float(row[name]),
            "mean_7d": float(row[f"{name}_mean_7d"]),
            "mean_30d": float(row[f"{name}_mean_30d"]),
        }
        for name in names
    ]


def _history(frame: pd.DataFrame, robot_id: str) -> list[dict[str, Any]]:
    columns = [
        "observation_date", "temperature_c", "vibration_rms", "motor_current_a",
        "battery_soh_pct", "task_count", "fault_count",
    ]
    records = frame.loc[frame["robot_id"].eq(robot_id), columns].tail(30).to_dict("records")
    return [
        {"date" if key == "observation_date" else key: _json(value) if isinstance(value, (np.generic, pd.Timestamp)) else value
         for key, value in record.items()}
        for record in records
    ]


def train(data_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    raw = load_observations(data_path)
    featured = build_features(raw)
    heldout = deterministic_holdout(raw["robot_id"])

    train_rows = candidate_rows(featured, None, TRAIN_END)
    train_rows = train_rows.loc[~train_rows["robot_id"].isin(heldout)]
    validation = candidate_rows(featured, VALIDATION_START, VALIDATION_END)
    validation_seen = validation.loc[~validation["robot_id"].isin(heldout)]
    test = candidate_rows(featured, TEST_START, TEST_END)
    columns = feature_columns()
    y_train = train_rows["target_next_7d"].astype(int)
    y_validation = validation_seen["target_next_7d"].astype(int)

    models = _models()
    validation_comparison: dict[str, Any] = {}
    validation_probabilities: dict[str, np.ndarray] = {}
    for name, model in models.items():
        model.fit(train_rows[columns], y_train)
        probability = model.predict_proba(validation_seen[columns])[:, 1]
        validation_probabilities[name] = probability
        validation_comparison[name] = metrics(y_validation, probability, 0.5)

    selected_name = max(
        models, key=lambda name: validation_comparison[name]["average_precision"]
    )
    selected = models[selected_name]
    validation_probability = validation_probabilities[selected_name]
    threshold = float(np.quantile(validation_probability, 0.90))
    validation_selected = metrics(y_validation, validation_probability, threshold)

    test_probability = selected.predict_proba(test[columns])[:, 1]
    test_seen_mask = ~test["robot_id"].isin(heldout)
    test_metrics = {
        "all": metrics(test["target_next_7d"].astype(int), test_probability, threshold),
        "seen_robots": metrics(
            test.loc[test_seen_mask, "target_next_7d"].astype(int),
            test_probability[test_seen_mask.to_numpy()],
            threshold,
        ),
        "unseen_robots": metrics(
            test.loc[~test_seen_mask, "target_next_7d"].astype(int),
            test_probability[(~test_seen_mask).to_numpy()],
            threshold,
        ),
    }
    # Only events for which all seven preceding candidate dates fall inside the
    # frozen test observation window have equal detection opportunity.
    failures = raw[
        raw["failure_event"].eq(1)
        & raw["observation_date"].between(TEST_START + pd.Timedelta(days=7),
                                           TEST_END + pd.Timedelta(days=1))
    ]
    event_result = event_metrics(test, test_probability, failures, threshold)

    # Bounded, genuinely held-out permutation importance on validation data.
    importance_sample = validation_seen.sample(
        min(12_000, len(validation_seen)), random_state=42017
    )
    permutation = permutation_importance(
        selected,
        importance_sample[columns],
        importance_sample["target_next_7d"].astype(int),
        scoring="average_precision",
        n_repeats=3,
        random_state=42017,
        n_jobs=2,
    )
    importance = sorted(
        [
            {"feature": feature, "importance": float(score)}
            for feature, score in zip(columns, permutation.importances_mean)
        ],
        key=lambda item: item["importance"],
        reverse=True,
    )

    artifact = {
        "model_id": MODEL_ID,
        "model": selected,
        "feature_columns": columns,
        "threshold": threshold,
        "training_end": str(TRAIN_END.date()),
        "horizon_days": 7,
    }
    model_path = output / "model.joblib"
    joblib.dump(artifact, model_path, compress=3)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    (output / "model.joblib.sha256").write_text(f"{digest}  model.joblib\n")

    latest = featured.groupby("robot_id", sort=False).tail(1)
    latest_probability = selected.predict_proba(latest[columns])[:, 1]
    probabilities = dict(zip(latest["robot_id"], latest_probability))
    predictions = []
    for _, row in latest.iterrows():
        eligible = bool(row["history_eligible"] and row["failure_event"] == 0)
        probability = float(probabilities[row["robot_id"]]) if eligible else None
        predictions.append(
            {
                "robot_id": row["robot_id"],
                "warehouse_id": row["warehouse_id"],
                "robot_type": row["robot_type"],
                "vendor": row["vendor"],
                "observation_date": _json(row["observation_date"]),
                "prediction_start": _json(row["observation_date"] + pd.Timedelta(days=1)),
                "prediction_end": _json(row["observation_date"] + pd.Timedelta(days=7)),
                "risk_probability": probability,
                "priority": "unavailable" if not eligible else ("review" if probability >= threshold else "monitor"),
                "eligible": eligible,
                "reason": "failure_event_on_snapshot_date" if row["failure_event"] == 1 else (None if eligible else "insufficient_30_day_history"),
                "signals": _signal_rows(row),
                "history": _history(featured, row["robot_id"]),
            }
        )
    (output / "predictions.json").write_text(json.dumps(predictions, indent=2, default=_json))

    selected_lift = validation_selected["average_precision"] / validation_selected["prevalence"]
    status = (
        "experimental_holdout_lift"
        if selected_lift > 1.05
        else "experimental_no_holdout_lift"
    )
    warnings = [
        "Source provenance is unverified.",
        "This is a retrospective snapshot, not live telemetry.",
        "Associations and descriptive signals are not causal drivers.",
        "Overlapping 7-day labels make row-level confidence intervals non-independent; no interval estimates are reported.",
        "The frozen artifact was trained only through 2026-04-23 and was not refit after evaluation.",
        "Alert precision is modest, so most alerts at the selected threshold are false positives.",
        "Risk probabilities have not been externally calibrated.",
        "Holdout lift is experimental evidence, not operational or external validation.",
    ]
    if status != "experimental_holdout_lift":
        warnings.append("Validation AP did not show useful lift over natural prevalence.")
    model_comparison = []
    for name in models:
        selected_test = test_metrics["all"] if name == selected_name else None
        model_comparison.append(
            {
                "model": name,
                "validation_average_precision": validation_comparison[name]["average_precision"],
                "test_average_precision": (
                    selected_test["average_precision"] if selected_test else None
                ),
                "test_roc_auc": selected_test["roc_auc"] if selected_test else None,
                "test_brier_score": selected_test["brier"] if selected_test else None,
            }
        )
    source_sha = hashlib.sha256(Path(data_path).read_bytes()).hexdigest()
    dependencies = {
        "python": platform.python_version(),
        "pandas": importlib.metadata.version("pandas"),
        "scikit-learn": importlib.metadata.version("scikit-learn"),
        "joblib": importlib.metadata.version("joblib"),
        "numpy": importlib.metadata.version("numpy"),
    }
    results = {
        "validation_comparison": validation_comparison,
        "validation_selected": validation_selected,
        "test": test_metrics,
        "test_event_level": event_result,
        "holdout_robot_count": len(heldout),
        "heldout_robot_ids": sorted(heldout),
    }
    summary = {
        "model_id": MODEL_ID,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_start": _json(raw["observation_date"].min()),
        "data_end": _json(raw["observation_date"].max()),
        "horizon_days": 7,
        "robot_count": raw["robot_id"].nunique(),
        "row_count": len(raw),
        "failure_count": int(raw["failure_event"].sum()),
        "selected_model": selected_name,
        "validation_status": status,
        "threshold": threshold,
        "metrics": results,
        "split": {
            "train_observations_end": "2026-04-23",
            "train_labels_end": "2026-04-30",
            "validation_observations": ["2026-05-01", "2026-06-23"],
            "validation_labels_end": "2026-06-30",
            "test_observations": ["2026-07-01", "2026-09-14"],
            "test_outcomes_end": "2026-09-21",
            "robot_holdout_fraction": 0.15,
        },
        "features": columns,
        "warnings": warnings,
        "feature_importance": importance,
        "model_sha256": digest,
        "predictions_sha256": hashlib.sha256((output / "predictions.json").read_bytes()).hexdigest(),
        "source_zip_sha256": source_sha,
        "dependency_versions": dependencies,
        "model_comparison": model_comparison,
    }
    (output / "metrics.json").write_text(json.dumps(results, indent=2, default=_json))
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=_json))
    _write_model_card(output / "model_card.md", summary)
    return summary


def _write_model_card(path: Path, summary: dict[str, Any]) -> None:
    selected = summary["metrics"]["validation_selected"]
    test = summary["metrics"]["test"]
    text = f"""# Predictive maintenance next-7-day model

## Intended use
Prioritize human review of robots with elevated estimated failure risk in the next
7 calendar days. This retrospective model is not a safety control, diagnosis, or
live telemetry feed. Source data provenance is unverified.

## Frozen evaluation design
The model was trained on eligible, non-failure-day observations through
2026-04-23 (labels end 2026-04-30), excluding a deterministic 15% robot-ID
holdout. Model selection used AP on seen robots from 2026-05-01 through
2026-06-23. The artifact was not refit. Final test observations span 2026-07-01
through 2026-09-14, with outcomes through 2026-09-21.

Selected model: **{summary['selected_model']}**. Validation status:
**{summary['validation_status']}**. The alert threshold ({summary['threshold']:.6f})
was selected exclusively from validation scores to target approximately 10% of
candidate daily rows.

## Measured performance
Validation AP/PR-AUC: {selected['average_precision']:.4f}; ROC-AUC:
{selected['roc_auc']:.4f}; Brier: {selected['brier']:.4f}; precision/recall at
threshold: {selected['precision_at_threshold']:.4f}/{selected['recall_at_threshold']:.4f}.
This modest precision implies that most alerts are false positives. Probabilities
have not been externally calibrated, and holdout lift is not operational
validation.

Test seen-robot AP: {test['seen_robots']['average_precision']:.4f}. Test unseen-
robot AP: {test['unseen_robots']['average_precision']:.4f}. See `metrics.json`
for prevalence, all model comparisons, row-level metrics, and event-level recall.

## Features and leakage controls
Inputs are robot type, vendor, and the 14 permitted numeric daily measurements,
plus trailing 7/30-day means and 7-day endpoint trends. Robot ID and date are
used only for grouping/splitting; warehouse and charger context are not model
inputs. Firmware, health, charger state, maintenance counters, target fields,
and derivatives of those fields are excluded. Input is sorted, duplicate checked,
and validated for daily date continuity. Labels use strictly t+1 through t+7.
Failure-day and final seven censored rows are excluded from training/evaluation.

## Limitations
The daily prediction rows have overlapping outcome intervals and are therefore
not independent; confidence intervals are not reported. Event-level detection
can count repeated warnings for one eventual event; only events with all seven
preceding prediction dates inside the test window are included. Permutation importance is
computed on a bounded held-out validation sample and describes predictive
association, not causality. Signed values are retained, including negative
importance caused by sampling variation. The latest output is a retrospective snapshot and
must not be represented as current operational status.

Artifact integrity: SHA-256 `{summary['model_sha256']}`. Joblib/pickle must only
be loaded from this trusted local output because deserialization can execute code.
Source ZIP SHA-256: `{summary['source_zip_sha256']}`.
"""
    path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train frozen next-7-day maintenance model")
    parser.add_argument("--data", required=True, help="CSV or ZIP source")
    parser.add_argument("--output", required=True, help="Artifact output directory")
    args = parser.parse_args()
    summary = train(args.data, args.output)
    print(json.dumps(summary, indent=2, default=_json))


if __name__ == "__main__":
    main()