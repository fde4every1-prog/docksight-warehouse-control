# Definition of Ready — Repo 2 increment

**Prompt 05.** An implementation task (Prompt 12+) is **Ready** only if all boxes hold.  
No Spec → No Code. No Acceptance Criterion → No Implementation.

## Always required

- [ ] `discovery/04_USE_CASE_AND_AI_SUITABILITY.md` GO still accepted (deterministic spine; LLM off write path)
- [ ] `specs/01_domain_model.md` names the entities and invariants the change will touch
- [ ] Invariants listed as IDs (I1–I12 or subset) with at least one fixture ID from Phase 1
- [ ] `TRACEABILITY_MATRIX.md` row exists: brief outcome and/or golden scenario and/or EVAL-00N
- [ ] Test or eval case written **first** (may xfail until implementation)
- [ ] Safety/operational impact one paragraph: what Eligibility/Uncertainty/Conflict does; what it must not do
- [ ] No requirement to enable `physical_control` or call real OT
- [ ] No requirement to clean or rewrite `data/` contradictions
- [ ] If UC-2/LLM mentioned: output is ActionProposal text only; DecisionEngine/Eligibility remain deterministic

## Data / knowledge (after Prompt 06)

- [ ] Grain, keys, and “retain vs drop” rules cited from `specs/02_data_contracts.md` when touching CSV/SQLite

## Evals (after Prompt 07)

- [ ] Golden case or EVAL-00N mapped; `must_not` copied into the test name or assertion

## Hard gates / authority (after Prompt 10)

- [ ] Gate IDs G1–G8 cited; DecisionEngine (not LLM) is the gate
- [ ] `tests/test_hard_gates_spec.py` exists (may xfail until Prompt 12)
- [ ] A miss-cutoff recommendation is in scope; a safety-bypass recommendation is DENY

## Security (after Prompt 11)

- [ ] Untrusted sources listed in `specs/07_threat_model.md` (emails, FINAL_v7, telemetry, chat)
- [ ] `tests/test_untrusted_content.py` exists: injection note must not change Eligibility
- [ ] CopilotService must not import ActionExecutor (ABSENT copilot is compliant)
- [ ] `/health` remains `physical_control: disabled`

## Ready examples (UC-1)

| Change | Ready when |
|---|---|
| Eligibility function | I1, I2, I5 named; fixtures `RBT-0001`, expired-cert robot; EVAL-002 |
| InventoryObservation API | I3; `SKU-01146`; EVAL-001/006 |
| Task completion guard | I4; `ORD-000968` / `TSK-000968-1` |
| Allocator new path | I1, I5, I6, I12; keep `legacy_score` as named baseline |

## Not Ready

- “Add an agent to assign robots”
- “Make wms_qty = vision_qty”
- “Parse email into safety waiver”
- Implementation with no invariant ID
