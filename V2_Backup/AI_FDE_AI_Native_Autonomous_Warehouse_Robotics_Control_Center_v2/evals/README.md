Evaluate evidence grounding, identity, temporal correctness, safety/authority compliance, tool trajectory, side effects, uncertainty, resilience, latency and cost.

- Seed cases (EVAL-001–006): `evals/golden_cases.jsonl`
- Repo 2 pack (EVAL-001–022, GS-1–15): `evals/golden_cases_repo2.jsonl`
- Strategy and harms: `specs/03_evaluation_strategy.md`, `specs/03_risk_and_harms.md`
- **Harness (Prompt 14):** `python -m warehouse_control.cli evals` → `evals/scorecard.md`, `evals/traces/`, `evals/observability.md`
- **Readiness (Prompt 15):** `python -m warehouse_control.cli readiness` → simultaneous pressure + Prompt 03 before/after; trace `evals/traces/PROMPT-15-SIMULTANEOUS.json`

Success is operational (false availability / unsafe assign = 0), not HTTP 200. Repo 2 is not live OT.
