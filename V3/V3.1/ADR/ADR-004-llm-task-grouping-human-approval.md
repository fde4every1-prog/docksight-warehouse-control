# ADR-004: LLM task grouping with human approval

**Case:** Autonomous Warehouse Robotic Control Tower  
**Stage:** 10 -- AI & Application Architecture  
**Status:** Accepted  
**Date:** 2026-09-24  
**Decision owner:** Control Tower architecture / fulfillment operations  
**Participant status:** `COMPLETE`  
**Deliverable form:** ADR / decision record

## Context / decision drivers

The control tower needs to evaluate grouping proposals for queued robotic tasks in
each warehouse. Grouping compatible work may reduce pick and move service time while
preserving deadlines and downstream resource constraints. A proposal must be based on
the existing task queue, current warehouse context, eligible resources, payloads,
locations, inventory assumptions, and cutoff times. It must not invent orders,
identifiers, resources, or feasibility evidence.

Task grouping is operationally consequential: an approved proposal could influence
which work is performed together and how resources are consumed. The application must
therefore separate proposal generation from authorization and execution. Human review
must be able to inspect the source queue, selected groups, exclusions, assumptions,
validation result, and baseline comparison before approval.

The decision is constrained by the following authority and safety boundaries:

- An LLM cannot issue or execute navigational commands or replace the Master's command
authority.
- Critical maintenance holds remain hard feasibility constraints until authorized
technical release.
- LLM output cannot directly create tasks, reservations, resource claims, or physical
commands.
- Deterministic validation remains authoritative for candidate membership, overlap,
warehouse scope, payload, deadlines, readiness, and downstream contention.
- Human approval is explicit, attributable, revision-aware, and required before a
proposal can be considered for operational application.

## Options considered

| Option | Evidence | Advantages | Disadvantages / risks |
|---|---|---|---|
| **A. LLM proposes task groups and a human approves after deterministic validation** | `artifacts/api-server/BATCHING_CONTRACT.md`; `batching_api.py`, `/suggest`, `validate_llm`, and `resolve_batches` | Uses LLM flexibility for queue interpretation and explanations; preserves human accountability; deterministic validator rejects invalid plans; proposal can be compared with a deterministic singleton baseline; provider failure leaves no substituted plan | Adds review time and approval workflow complexity; human may approve a poor but valid proposal; requires current queue snapshot, revision/fingerprint, audit, and stale-approval handling; current package is detached/synthetic and has no operational approval write path | 
| **B. Automatic LLM task grouping and execution** | Existing advisory-only boundary; `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I15/V3-I16; `05_PRODUCTION_READINESS.md` | Lowest operator effort and potentially fast adaptation to queue patterns | Unsafe authority transfer; prompt/model drift can change grouping; no accountable pre-execution decision; provider outage or malformed output can interrupt work; cannot establish complete constraint coverage; unacceptable for physical or operational dispatch | 
| **C. Fully deterministic grouping policy** | `BATCHING_CONTRACT.md`, deterministic candidate enumeration and baseline scheduler rules | Reproducible, testable, and independent of provider behavior; clear safety and replay properties | Less flexible for context-rich grouping suggestions; may require frequent policy changes; does not use LLM reasoning to prioritize useful candidate combinations; human still needs to review operational impact |

## Architecture decision

**Choose Option A: use an AI LLM to propose task groups from the existing queue, with
human-in-the-loop approval required after deterministic validation and before any
operational application.**

For each warehouse, the system shall create a versioned proposal from a bounded queue
snapshot. The proposal shall identify only existing queued tasks/orders and candidate
groups supported by the supplied warehouse context. It shall include the scenario or
queue snapshot identity, model/provider metadata, selected candidate IDs, reasons,
exclusions, assumptions, and generated-at time.

Before a human can approve the proposal, deterministic validation shall verify at
least:

- queue snapshot identity and warehouse scope;
- known, unique, non-overlapping candidate membership;
- candidate feasibility and combined-plan feasibility;
- robot and asset readiness, capacity, and exclusive-use constraints;
- inventory, stage, path, service-time, and downstream contention rules;
- cutoff/deadline feasibility for every affected order; and
- unchanged revisions or fingerprints since proposal generation.

Validation failures are rejected and are not silently repaired. An LLM timeout,
provider error, incomplete response, or unknown identifier produces no proposal for
approval. The human approver must review the validated plan and baseline comparison,
then explicitly approve or reject it. Approval must record the approver identity,
approval time, queue snapshot/revision, proposal/model IDs, validation result, and any
comment. A stale approval is invalid and must be regenerated.

Approval authorizes only the bounded grouping decision within the approved scope. It
does not authorize physical actuation, bypass deterministic readiness or maintenance
holds, change inventory accounting, or grant the LLM execution authority. Any future
operational application must still pass the deterministic scheduler and existing
resource-claim/state-transition controls.

The current implementation remains a detached synthetic sandbox: `/api/batching/suggest`
generates a validated proposal and `/api/batching/compare` compares it with a
baseline, but the package does not persist human approvals or import the result into
fulfillment. Those capabilities are prerequisites for adopting this decision on a
live operational queue.

An automatic LLM-based solution is rejected because it would remove the explicit human
authorization gate and place operationally consequential grouping decisions on a
non-deterministic provider response.

## Consequences and trade-offs

Positive consequences:

- Operators retain accountable approval authority over grouping proposals.
- LLM flexibility is used for suggestion and explanation without allowing unvalidated
  output to alter operational state.
- Deterministic validation protects queue membership, overlap, feasibility, deadlines,
  payloads, and downstream bottlenecks.
- Proposal, validation, approval, and execution can be audited and replayed against a
  known queue snapshot.
- Provider outage, malformed output, or prompt manipulation results in no proposal,
  rather than an automatic fallback or unsafe dispatch.

Trade-offs and limitations:

- Human review adds latency and operational workload, especially for high-volume
  warehouses.
- A valid proposal is not necessarily globally optimal; the sandbox's synthetic timing,
  geometry, and payload assumptions are not measured site conditions.
- The approval workflow requires secure identity, role authorization, revision checks,
  audit retention, and a clear reject/expire/regenerate path.
- Deterministic validation must remain complete and independent of the LLM; treating
  the validator as a convenience layer would invalidate this decision.
- Current evidence proves an isolated proposal/comparison flow, not production value,
  live queue integration, or physical safety.

## Evidence and traceability

| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| LLM proposals select groups from supplied candidate IDs | `artifacts/api-server/batching_api.py`, `request_llm` and `validate_llm`; `BATCHING_CONTRACT.md` | Stage 09 AI/application boundary | High for inspected detached sandbox; no live queue integration |
| Invalid proposals are rejected, not silently repaired | `batching_api.py`, `resolve_batches` and `validate_llm`; `BATCHING_CONTRACT.md`, validation contract | Stage 09 safety/control artifact | High for code inspection and packaged contract |
| Candidate groups must be revalidated together | `BATCHING_CONTRACT.md`, `enumerate_candidates` and combined-plan rule | Stage 09 batching contract | High for documented sandbox behavior; synthetic constraints only |
| Baseline comparison is available | `BATCHING_CONTRACT.md`, `compare`; `batching_api.py`, `/compare` | Stage 09 workflow/evaluation evidence | High for isolated simulation; no approved business value baseline |
| Proposal cannot currently mutate operational fulfillment state | `04_REQUIREMENTS_TRACEABILITY.md`, R3-22; `PRD.md`, batching boundary; `05_PRODUCTION_READINESS.md`, LLM residual | Stage 09 requirements and production readiness | High for current package; this ADR defines prerequisites for a future approval path |
| LLM and maintenance outputs cannot create work without controls | `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I15/V3-I16; `01_AS_BUILT_ARCHITECTURE.md`, advisory LLM boundary | Stage 09 domain controls | High for documented/code-inspected boundary |
| Human approval is an explicit architecture requirement of this ADR | This ADR: approval identity, revision, validation, comment, and expiry requirements | Stage 10 decision | Design decision; implementation and security evidence remain open |

## Reversal trigger

Reconsider this decision if controlled evaluation shows that human approval does not
provide sufficient safety or operational value, including any of the following:

1. Repeated approval of invalid, stale, unsafe, or materially infeasible plans despite
   deterministic validation and reviewer controls.
2. Review latency or volume makes the workflow impractical without a measured,
   approved change to the authority model.
3. A deterministic grouping policy demonstrates equal or better outcomes with lower
   operational risk and acceptable flexibility.
4. A replacement approach can provide stronger accountability, reproducibility,
   deadline protection, and complete constraint coverage than the approved LLM-plus-
   human workflow.
5. The intended deployment boundary changes to physical or external actuation without
   an independently approved safety case, authenticated authorization, shadow mode,
   rollback, and manual fallback.

Automatic LLM grouping must not be enabled merely because proposal quality improves.
Removing human approval requires a new ADR and independent evidence that the replacement
authority model is safe, authorized, auditable, and reversible.

## Open issues / assumptions

| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| Current batching is detached and synthetic | The package does not import proposals into live fulfillment or persist approvals | Fulfillment/platform engineering | Decision is architectural; operational adoption is not yet enabled | Queue adapter, approval store, import contract, and end-to-end tests |
| Human approval identity is not production-secure | Demo persona headers are caller-controlled and do not establish IAM | Security/platform engineering | Approval cannot be trusted on a shared or production deployment | Authenticated identity, RBAC, audit, and approval threat model |
| Queue freshness and concurrency policy is undefined | A queue can change after proposal generation or during review | Fulfillment engineering | Stale plans could group work that is no longer eligible | Revision/fingerprint contract and stale-approval tests |
| Synthetic geometry and timing are not warehouse truth | Sandbox uses fixed assumptions and does not model all labor, congestion, or failures | Operations/fleet engineering | Savings and feasibility cannot be generalized to live warehouses | Site-validated constraints and representative replay evaluation |
| Human reviewer role and SLA are not defined | Review workload, escalation, and reject/expire behavior need operational ownership | Warehouse operations | Approval delays can negate expected grouping benefit | Approved RACI, review policy, and measured pilot results |

## Completion check

- [x] Minimum content above is complete.
- [x] Material claims cite exact evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic, and AI decision rights are distinguishable.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] Human approval is required before any future operational application.
- [x] Automatic LLM grouping is explicitly evaluated and rejected.

## Handoff

**Stage exit contribution:** Complete base AI/application architecture

Do not advance to Stage 11 until the Stage 10 exit gate is defensible.
