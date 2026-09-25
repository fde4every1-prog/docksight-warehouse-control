# ADR-002: Statistical demand forecasting for robotic warehouse work

**Case:** Autonomous Warehouse Robotic Control Tower  
**Stage:** 10 — AI & Application Architecture  
**Status:** Accepted  
**Date:** 2026-09-24  
**Decision owner:** Control Tower architecture / fulfillment engineering  
**Participant status:** `COMPLETE`  
**Deliverable form:** ADR / decision record

## Context / decision drivers

The control tower needs a demand forecast for each `warehouse_id` and `sku` so that
supervisors can see near-term demand and the system can produce low-stock signals.
The forecast supports planning and explanation; it does not assign robots, reserve
inventory, certify physical feasibility, or issue commands.

The forecast must preserve warehouse and SKU attribution, use an explicit observation
window and timezone, include zero-demand days, expose short or missing history, and
persist the inputs and method used for each run. It must remain reproducible and
understandable when data is sparse or incomplete. Forecast outputs must not silently
become safety gates or replace deterministic inventory and resource-eligibility policy.

The decision is also constrained by the existing authority boundary:

- AI cannot issue or execute navigational commands or replace the Master's command
authority.
- Critical maintenance holds remain hard feasibility constraints until authorized
technical release.
- Forecasting is advisory information for demand planning; it is not an authorization
to create robotic tasks or change protected inventory accounting.

## Options considered

| Option | Evidence | Advantages | Disadvantages / risks |
|---|---|---|---|
| **A. Statistical machine-learning forecasting models** | `artifacts/api-server/demand_forecast.py`; R3-15; `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, Journey E | Deterministic, inspectable features and aggregation; supports repeatable per-warehouse/SKU forecasts; can evolve from a transparent baseline to validated regression, exponential-smoothing, intermittent-demand, or other statistical models; bounded runtime and no provider dependency | Quality depends on history, coverage, seasonality, and feature quality; sparse/new SKUs require explicit fallback states; model updates require validation, versioning, and monitoring; current implementation is a mean-demand baseline rather than a trained model | 
| **B. AI LLM-based demand forecasting** | `01_AS_BUILT_ARCHITECTURE.md` advisory LLM boundary; transfer and batching contracts as examples of isolated LLM suggestions | Can accept narrative context and produce explanations; flexible for exploratory what-if analysis | Weak fit for numeric time-series estimation; non-deterministic outputs and prompt/model drift; difficult to reproduce and calibrate per warehouse/SKU; provider outage, cost, privacy, and latency risks; cannot be allowed to alter operational state; invalid output requires rejection | 
| **C. LLM-generated forecast with statistical post-processing** | Existing advisory-only LLM boundary and deterministic application controls | Could combine narrative context with numeric processing | Adds an unnecessary opaque dependency to the forecast path; post-processing cannot prove the LLM estimate is valid; makes attribution, evaluation, rollback, and audit harder without establishing a material benefit |

## Architecture decision

**Choose Option A: use statistical machine-learning models for robotic demand
forecasting at warehouse/SKU granularity.**

The authoritative forecast pipeline shall be a versioned, persisted statistical
calculation over attributable order demand. Every run shall record its forecast date,
observation window, timezone, method version, warehouse, SKU, history units, history
days, history status, and forecast outputs. Zero-demand days shall be represented in
the observation window. Missing, unassigned, cancelled, or out-of-window data shall
follow explicit inclusion/exclusion rules and be visible in run metadata.

The current implementation is the initial transparent model: a mean of ordered units
per observed IST calendar day over the configured lookback window, with ceiling-rounded
7-day and 30-day values. It is intentionally labelled a statistical baseline, not a
trained AI model. Future statistical machine-learning candidates may replace or
augment it only through versioned evaluation against this baseline, with an explicit
fallback for no-history and short-history warehouse/SKU pairs.

An AI LLM-based solution is rejected as the authoritative forecasting method. LLMs may
be used only for separately labelled explanation or isolated exploratory analysis. An
LLM result must not create tasks, reserve stock, change inventory, alter assignment
eligibility, or overwrite a persisted forecast without an approved deterministic
validation and model-governance process.

## Consequences and trade-offs

Positive consequences:

- Forecasts remain reproducible, attributable to a warehouse and SKU, and explainable
  to supervisors.
- Persisted run and daily-input evidence allows a forecast to be inspected and replayed
  without relying on an LLM provider or changing prompt behavior.
- The approach degrades explicitly for no-history and short-history pairs instead of
  inventing confidence.
- Forecasting remains separated from deterministic allocation, task assignment,
  maintenance holds, and protected inventory movements.
- Statistical models can be evaluated with standard time-series backtesting and rolled
  back by method version.

Trade-offs and limitations:

- A transparent mean baseline may miss seasonality, promotions, intermittent demand,
  stockouts, substitutions, and changing warehouse behavior.
- Forecast quality is limited by the synthetic/local data and by the absence of a
  production telemetry and outcome-monitoring service.
- A model with better average error may still be unsuitable for a particular SKU or
  warehouse; coverage and error must remain visible.
- Forecasts are planning signals only. They do not prove inventory availability,
  physical robot capacity, or delivery performance.
- Introducing a more advanced statistical model adds feature, training, drift,
  calibration, and approval obligations.

## Evidence and traceability

| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Forecast is generated per warehouse and SKU with persisted runs and outputs | `artifacts/api-server/demand_forecast.py`, `demand_forecast_runs`, `demand_forecasts`, and `demand_forecast_daily_inputs` | Stage 09 domain model and architecture | High for inspected local implementation; not production telemetry |
| Current method is an explainable statistical baseline | `demand_forecast.py`, `METHOD = mean_daily_ordered_units_completed_ist_days_60d_v2`; `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I13 and Journey E | Stage 09 workflow/control artifact | High; explicitly not evidence of a trained model |
| Zero-demand days and coverage states are represented | `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, Journey E; `demand_forecast.py`, `history_status` values `no_history`, `short_history`, `observed` | Stage 09 forecasting workflow | High for implementation intent and code inspection |
| Forecast is transparent and traceable | `04_REQUIREMENTS_TRACEABILITY.md`, R3-15; `01_AS_BUILT_ARCHITECTURE.md`, Forecasting component | Stage 09 requirements and as-built architecture | Packaged test evidence; backend tests were not rerun on this Windows host |
| Forecast does not authorize operations or physical action | `PRD.md`, I9/I12; `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I13 and V3-I15; `04_REQUIREMENTS_TRACEABILITY.md`, R3-19/R3-20 | Stage 09 product invariants and safety requirements | High for documented/code-inspected boundary; production authorization is not implemented |
| LLM use is advisory and isolated from operational writes | `01_AS_BUILT_ARCHITECTURE.md`, advisory LLM boundary; `TRANSFER_CONTRACT.md` and `BATCHING_CONTRACT.md` | Stage 09 AI/application architecture | High for inspected package; provider governance remains a future concern |

## Reversal trigger

Reconsider this decision only if a replacement forecasting approach demonstrates, on
representative warehouse/SKU time-series data and against the current baseline:

1. A material and repeatable improvement in agreed forecast metrics, reported by
   warehouse, SKU cohort, horizon, and history-coverage class.
2. No unacceptable degradation for sparse, intermittent, new, cancelled, or
   out-of-window demand, with explicit fallback behavior.
3. Versioned inputs, features, model parameters, forecasts, confidence/coverage
   information, and reproducible historical evaluation.
4. Drift, data-quality, calibration, rollback, and human-review controls suitable for
   the intended deployment boundary.
5. Bounded runtime and a deterministic degraded mode that continues to provide safe,
   clearly labelled outputs when the model is unavailable.
6. Evidence that the replacement cannot create tasks, reservations, claims, physical
   commands, or protected inventory changes without separate deterministic policy.

An LLM may be reconsidered for a separately governed explanatory or exploratory surface,
but provider fluency or narrative quality alone is not a reversal trigger for the
numeric forecasting decision.

## Open issues / assumptions

| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| Current baseline is not a trained machine-learning model | The implementation uses mean daily demand and local/synthetic evidence | Forecasting engineering | Do not represent current output as trained AI/ML | Approved model card and backtest report for a replacement statistical model |
| Source data may not represent live demand | Packaged order and inventory sources are snapshots; operational telemetry is not established | Data/platform engineering | Accuracy and drift claims cannot be generalized to production | Production data-quality, coverage, and monitoring report |
| Forecasts are not allocation eligibility | Forecast availability and allocatable stock intentionally use different definitions | Fulfillment engineering | A forecast must not bypass inventory, readiness, or reservation controls | Contract tests covering forecast and allocation boundaries |
| Warehouse/SKU cold-start behavior needs business policy | No-history and short-history pairs need review thresholds and fallback ownership | Operations and product | Low-confidence forecasts may affect planning interpretation | Approved cold-start policy and UI evidence |

## Completion check

- [x] Minimum ADR content is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic, and AI decision rights are distinguishable.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] The current mean baseline is not relabelled as trained AI/ML.
- [x] LLM use is explicitly limited to advisory or isolated exploratory scenarios.

## Handoff

**Stage exit contribution:** Complete base AI/application architecture

Do not advance to Stage 11 until the Stage 10 exit gate is defensible.
