# Predictive-maintenance training

Run from `artifacts/api-server`:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  uv run --project ../.. python -m predictive_maintenance \
  --data ../../attached_assets/robot_observations_1790058633828.zip \
  --output models/predictive-maintenance
```

The command validates and sorts the daily robot panel, creates leakage-safe
trailing features and t+1..t+7 labels, compares a prevalence baseline, logistic
regression, and histogram gradient boosting, then selects only by validation
average precision. It writes the frozen model, checksum, metrics, model card,
self-contained API summary, and one latest retrospective prediction per robot.

Run focused tests with:

```sh
uv run --project ../.. pytest predictive_maintenance
```