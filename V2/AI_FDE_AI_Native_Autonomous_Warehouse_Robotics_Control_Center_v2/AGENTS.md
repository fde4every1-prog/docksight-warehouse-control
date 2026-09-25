# AGENTS.md

## Mission
Treat this repository as a production brownfield discovery and modernization engagement, not as a clean greenfield rewrite.

## Ground rules
- Preserve the ability to reproduce existing behavior before replacing it.
- Never assume a source is authoritative because its name sounds authoritative.
- Distinguish **digital state**, **physical evidence**, **operational interpretation**, and **decision authority**.
- Prefer evidence-backed conclusions. Record unresolved uncertainty.
- Do not connect to real robot controllers or execute physical control actions.
- Safety-critical actions require explicit human authority in any target-state design.
- Treat `restricted_answer_key/` as out of bounds for participants unless explicitly authorized.

## Suggested workflow
1. Inventory code, data, contracts, schemas and shadow processes.
2. Build a system-of-systems map and identify competing systems of record.
3. Reconstruct robot, inventory, task, order and shipment identities.
4. Quantify data quality, temporal, unit and state inconsistencies.
5. Trace at least three end-to-end order journeys.
6. Identify hidden cross-system dependencies and resilience gaps.
7. Define a canonical domain model and bounded contexts.
8. Propose interventions only after root causes are evidenced.
9. Build evals before adding autonomous behavior.
10. Measure business, safety, reliability and cost outcomes.

## Anti-patterns
- Do not bolt an LLM onto dashboards and call it modernization.
- Do not make a knowledge graph, digital twin or agent mandatory unless the problem warrants it.
- Do not let an agent bypass safety or business authority.
- Do not "fix" every inconsistency; some represent legitimate perspectives and require reconciliation.
