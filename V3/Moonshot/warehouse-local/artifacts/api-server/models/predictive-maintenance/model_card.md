# Predictive maintenance next-7-day model

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

Selected model: **logistic_regression**. Validation status:
**experimental_holdout_lift**. The alert threshold (0.050909)
was selected exclusively from validation scores to target approximately 10% of
candidate daily rows.

## Measured performance
Validation AP/PR-AUC: 0.0484; ROC-AUC:
0.6914; Brier: 0.0228; precision/recall at
threshold: 0.0639/0.2719.
This modest precision implies that most alerts are false positives. Probabilities
have not been externally calibrated, and holdout lift is not operational
validation.

Test seen-robot AP: 0.0682. Test unseen-
robot AP: 0.0729. See `metrics.json`
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

Artifact integrity: SHA-256 `e4f9dc2d90221799cf34ef81f77cc68888970909037d7b08863385ac4981ab80`. Joblib/pickle must only
be loaded from this trusted local output because deserialization can execute code.
Source ZIP SHA-256: `d62a4a36aa13e43572e9ffa2a76da154e1c7862ef7d00c2f128570cab56ecff8`.
