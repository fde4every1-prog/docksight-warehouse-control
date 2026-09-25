# ADR-003: Logistic regression for robotic preventive-maintenance alerts

**Case:** Autonomous Warehouse Robotic Control Tower  
**Stage:** 10 — AI & Application Architecture  
**Status:** Accepted  
**Date:** 2026-09-24  
**Decision owner:** Control Tower architecture / fleet engineering  
**Participant status:** `COMPLETE`  
**Deliverable form:** ADR / decision record

## Context / decision drivers

The control tower needs a preventive-maintenance review signal for robots in each
warehouse. The signal should prioritize robots whose observed data indicates elevated
risk of a failure event in the next seven calendar days, while remaining separate from
live health status, readiness certification, maintenance holds, and physical control.

The alerting design must preserve warehouse and robot attribution, expose the model
snapshot and observation freshness, validate the JSON score bundle, and make the
threshold and evaluation status visible. It must remain useful when a model snapshot
is unavailable or stale. A score must never clear a maintenance hold, change robot
fitness, assign work, reserve inventory, or issue a physical command.

The decision is constrained by the following authority and safety boundaries:

- AI cannot issue or execute navigational commands or replace the Master's command
authority.
- Critical maintenance holds remain hard feasibility constraints until authorized
technical release.
- Maintenance alerts are human-review prioritization, not safety interlocks,
diagnoses, or authorization to operate a robot.
- Deterministic readiness and assignment policy remains authoritative even when a
maintenance score is missing, stale, or favorable.

## Options considered

| Option | Evidence | Advantages | Disadvantages / risks |
|---|---|---|---|
| **A. Logistic regression statistical machine-learning model** | `artifacts/api-server/models/predictive-maintenance/model_card.md`; `predictive_api.py`; R3-24 | Interpretable and bounded binary-risk scoring; reproducible features, holdout evaluation, and threshold; straightforward warehouse filtering and review prioritization; no runtime LLM dependency; can be versioned and replaced through model governance | Current validation precision is modest and most alerts are false positives; probabilities are not externally calibrated; retrospective snapshot is not live telemetry; feature and label quality constrain results; requires monitoring, retraining, and explicit stale-data handling | 
| **B. AI LLM-based maintenance alerts** | `01_AS_BUILT_ARCHITECTURE.md` advisory LLM boundary; `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I15 | Can summarize maintenance context and produce natural-language explanations; flexible for exploratory review | Poor fit for calibrated numeric risk ranking; non-deterministic and difficult to reproduce; prompt/model drift can change alerts; provider availability, cost, privacy, and latency risks; cannot be trusted to detect safety conditions or alter readiness; invalid output requires rejection | 
| **C. LLM-generated alert with deterministic post-processing** | Existing validator-gated advisory patterns in `TRANSFER_CONTRACT.md` and `BATCHING_CONTRACT.md` | Could provide a narrative layer around structured maintenance data | Adds opaque dependency without proving better detection; deterministic post-processing cannot validate the underlying risk estimate; increases audit, rollback, and data-governance complexity |

## Architecture decision

**Choose Option A: use a logistic regression statistical machine-learning model for
robotic preventive-maintenance alerts in each warehouse.**

The model shall produce a versioned, read-only risk snapshot for each observed robot,
including `warehouse_id`, robot identity, risk probability, review priority, model
identity, data end date, threshold, and evaluation metadata. The initial selected
model is `logistic_regression`, trained and evaluated using the documented leakage
controls and robot-ID holdout. The initial alert horizon is the next seven calendar
days. The alert threshold is the validation-selected `0.050909` threshold and must be
changed only through a versioned evaluation and approval process.

The API shall serve checksummed JSON model output and reject missing, malformed,
duplicate, out-of-range, or unreadable snapshots. It shall expose freshness and
warehouse filtering so reviewers can distinguish current operational evidence from a
retrospective snapshot. If the snapshot is unavailable or stale, the system shall
show that state and require human review; it shall not infer that the robot is healthy
or automatically create a maintenance action.

The model is an advisory statistical machine-learning component. It cannot modify
`health_status`, readiness evidence, maintenance records, assignment eligibility,
resource claims, tasks, inventory, or external systems. Deterministic readiness rules
and authorized fleet workflows remain the only path for maintenance holds, repairs,
recovery, and assignment decisions.

An AI LLM-based solution is rejected as the authoritative alerting method. An LLM may
be used only for separately labelled explanation or investigation assistance, with no
write access and no authority to replace the logistic-regression score, deterministic
readiness policy, or human review decision.

## Consequences and trade-offs

Positive consequences:

- Each warehouse can filter and review robot risk using a consistent, versioned score.
- Logistic regression provides a bounded and reproducible statistical model that can be
  evaluated against holdout data and replaced through explicit model governance.
- The read-only JSON contract separates predictive review from operational state and
  avoids loading executable model artifacts at request time.
- Missing, stale, or invalid snapshots fail visibly instead of becoming false claims of
  robot health or silently changing scheduling behavior.
- The model remains independent of LLM provider availability and prompt behavior.

Trade-offs and limitations:

- The measured validation precision at the selected threshold is `0.0639`, so most
  alerts are false positives and fleet reviewers need a triage workflow.
- The model card reports validation AP/PR-AUC `0.0484`, ROC-AUC `0.6914`, and Brier
  `0.0228`; these are retrospective metrics, not operational safety evidence.
- Probabilities are not externally calibrated, and overlapping prediction windows are
  not independent observations.
- Warehouse and charger context are not model inputs, so the score cannot explain all
  warehouse-specific risk or replace local maintenance knowledge.
- The current artifact is a frozen snapshot, not a live telemetry, CMMS, or AIMS
  lifecycle. Staleness and source provenance must remain visible.
- A better statistical model may require new data pipelines, drift monitoring,
  calibration, retraining controls, and model retirement procedures.

## Evidence and traceability

| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Logistic regression is the selected model | `artifacts/api-server/models/predictive-maintenance/model_card.md`, “Selected model: logistic_regression” | Stage 09 maintenance review artifact | High for the inspected frozen model card; not production model approval |
| Alert horizon and threshold are defined | `model_card.md`, next-7-day intended use and threshold `0.050909` | Stage 09 model evaluation evidence | High for the snapshot; threshold is not proven optimal for live operations |
| Model performance is modest and retrospective | `model_card.md`, validation AP `0.0484`, ROC-AUC `0.6914`, Brier `0.0228`, precision/recall `0.0639/0.2719` | Stage 09 evaluation evidence | High for reported metrics; no external calibration or operational validation |
| Input leakage controls are documented | `model_card.md`, permitted features, holdout split, t+1 through t+7 labels, excluded fields | Stage 09 model artifact | High for documented training design; source provenance remains unverified |
| API serves read-only, checksummed JSON and does not unpickle the model | `artifacts/api-server/predictive_api.py`; R3-24; SAFE-05 | Stage 09 architecture and requirements artifacts | High for code inspection; runtime suite was not rerun on this Windows host |
| Scores cannot create work or change fitness/readiness | `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I15; `PRD.md`, I9 and I12; `04_REQUIREMENTS_TRACEABILITY.md`, R3-24 | Stage 09 safety and authority requirements | High for documented/code-inspected boundary; production authorization is not implemented |
| Warehouse-level review is supported | `predictive_api.py`, `/api/predictive-maintenance/predictions` warehouse filter and model response warehouse list | Stage 09 API contract | High for local API behavior; does not establish warehouse-specific model performance |

## Reversal trigger

Reconsider this decision only if a replacement approach demonstrates, against the
logistic-regression baseline and on representative data from each intended warehouse:

1. Material and repeatable improvement in agreed event-level and row-level metrics,
   reported by warehouse, robot cohort, forecast horizon, and alert burden.
2. Acceptable precision for the available fleet-review capacity, with explicit handling
   of false positives, false negatives, missing data, stale data, and new robots.
3. Calibrated or otherwise well-characterized risk outputs with reproducible,
   versioned features, labels, thresholds, snapshots, and evaluation splits.
4. No leakage from future maintenance outcomes, health decisions, target fields, or
   operational state that would be unavailable when an alert is issued.
5. A bounded degraded mode that makes unavailable or stale predictions visible and
   never converts uncertainty into a healthy or safe assertion.
6. Independent approval confirming that the replacement remains advisory and cannot
   alter maintenance holds, readiness, task assignment, physical commands, or external
   system state.

An LLM may be reconsidered for separately governed explanation or investigation support,
but better narrative fluency alone is not a reversal trigger for the numeric alerting
model.

## Open issues / assumptions

| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| The model is retrospective, not live preventive maintenance | The packaged source and prediction bundle are frozen snapshots with no operational telemetry or AIMS lifecycle | Fleet/data engineering | Alerts cannot be treated as current robot health or a maintenance guarantee | Live telemetry/CMMS integration, freshness SLO, and model lifecycle controls |
| Most alerts are false positives | Precision at the selected threshold is `0.0639` | Fleet operations | Review capacity and escalation policy must be defined before operational use | Approved triage workflow and measured alert-burden evaluation |
| Warehouse-specific performance is not established | The API filters by warehouse, but the model card does not establish adequate metrics for each warehouse | Data science and fleet engineering | A global model may underperform in an individual warehouse | Per-warehouse backtest, calibration, and acceptance report |
| Existing maintenance holds remain authoritative | Predictive scores are not safety evidence or technical release | Fleet engineering and safety owner | A favorable score cannot clear a hold; an alert cannot itself impose a certified hold | Approved deterministic hold/release policy and audit evidence |
| Model artifact deserialization is sensitive | The model card warns that joblib/pickle loading can execute code | Platform/security engineering | Only trusted, checksummed local outputs may be used | Artifact supply-chain controls and security review |

## Completion check

- [x] Minimum ADR content is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic, and AI decision rights are distinguishable.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] The selected model is explicitly logistic regression.
- [x] LLM use is explicitly limited to advisory explanation or investigation support.

## Handoff

**Stage exit contribution:** Complete base AI/application architecture

Do not advance to Stage 11 until the Stage 10 exit gate is defensible.
