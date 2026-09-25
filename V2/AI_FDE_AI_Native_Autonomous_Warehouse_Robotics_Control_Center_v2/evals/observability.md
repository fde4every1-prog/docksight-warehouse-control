# Observability notes (Prompt 14)

Deterministic UC-1. No LLM metrics. Logs are **counts and gate ids**, not robot motion.

## Always log

| Signal | Source | Why |
|---|---|---|
| `physical_control` | `/health` | Must remain `disabled` |
| `alias_collisions` | diagnostics | I9 |
| `inventory_uncertain_rows` / `inventory_truth_conflicts` | diagnostics | I3 |
| `wes_fleet_task_conflicts` | diagnostics | I4 |
| `expired_safety_cert_but_connected` | diagnostics | I1 population |
| `eligibility_ineligible_expired_cert` | diagnostics | UC-1 gate count |
| `eligibility_ineligible_open_cmms` | diagnostics | I5 |
| `cutoff_delayed_shipments` | diagnostics | I7 |
| `duplicate_telemetry_packets` | diagnostics | I8 |
| `decision` ALLOW/DENY/ABSTAIN | DecisionEngine | authority |
| `gates_failed` | Eligibility | which G# fired |
| `chosen_robot_id` null vs id | allocator | unsafe assign = 0 |
| `inject_id` | replay | resilience |
| `execution.applied` | stub | must stay false |

## Decision trace (every eval / preview)

Evidence → Interpretation → Recommendation → Decision → Approval required? → Execution (disabled) → Outcome.

Store `case_id`, fixture ids (`RBT-0001`, `ORD-000004`, `SKU-01146`), and `must_not_ok`.

## Alert if

- Any UC-1 assign of `safety_cert_status=EXPIRED`
- `completable=true` while WES≠fleet
- `on_time=true` while TMS DELAYED
- Copilot module imports ActionExecutor
- `/health` physical_control changes

## Do not log as success

HTTP 200, latency, token cost. Those are not Repo 2 release KPIs.
