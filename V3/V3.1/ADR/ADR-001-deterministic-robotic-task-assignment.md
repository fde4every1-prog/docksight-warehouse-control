# ADR-001: Deterministic robotic task assignment

**Case:** Autonomous Warehouse Robotic Control Tower  
**Stage:** 10 — AI & Application Architecture  
**Status:** Accepted  
**Date:** 2026-09-24  
**Decision owner:** Control Tower architecture / fulfillment engineering  
**Participant status:** `COMPLETE`  
**Deliverable form:** ADR / decision record

## Context / decision drivers

Robotic task assignment must select eligible resources for the staged fulfillment flow
`Pick → Move → Pack_feed → Stage`. Assignment changes operational state by creating or
advancing tasks, claiming resources, starting persisted task clocks, and coordinating
inventory effects. The assignment path therefore needs to be reproducible, auditable,
restart-safe, and fail closed when readiness or safety evidence is missing.

The decision is constrained by the following authority and safety boundaries:

- The system may assign simulated work but may not issue or execute navigational,
  physical, or external WMS/FMS/PLC/robot commands.
- Eligibility, authorization, inventory accounting, readiness holds, exclusive claims,
  and task-state transitions remain deterministic policy decisions.
- Critical maintenance holds remain hard feasibility constraints until authorized
  technical release.
- Any advisory AI output must not create tasks, reservations, claims, or fitness changes.

The main decision drivers are deterministic behavior, safety, explainability, stable
replay and recovery, operational auditability, bounded latency, and independence from
LLM provider availability or output shape.

## Options considered

| Option | Evidence | Advantages | Disadvantages / risks |
|---|---|---|---|
| **A. Deterministic scheduler and eligibility policy** | `artifacts/api-server/fulfillment_v2.py`, `fleet_readiness.py`, `CONTROL_TOWER.md`; requirements R3-08/R3-09 and SAFE-01–04 | Reproducible selections and tie-breaks; fail-closed readiness; explicit payload, stage, warehouse and claim checks; restart-safe persisted clocks/tokens; straightforward audit and testing; no provider dependency | May be less adaptive to unmodelled operational patterns; requires policy/configuration updates when constraints or objectives change; deterministic tie-breaks do not claim optimal real-world travel performance | 
| **B. LLM-based task assignment** | `01_AS_BUILT_ARCHITECTURE.md` advisory LLM boundary; `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md` V3-I15/V3-I16 and LLM transfer/batching contracts | Could summarize context, suggest sequencing, and potentially identify useful non-obvious patterns; flexible natural-language interaction | Non-deterministic output and provider/latency failure; difficult to prove complete constraint coverage; prompt/model drift can change assignments; unsafe to grant write authority; invalid plans require rejection rather than hidden repair; adds governance, cost and observability burden | 
| **C. LLM proposes, deterministic validator/scheduler executes** | `TRANSFER_CONTRACT.md`, `BATCHING_CONTRACT.md`; V3-I15/V3-I16 | Retains a future advisory path while keeping write-path controls deterministic; can compare proposals in isolated scenarios | Does not improve the authoritative assignment path today; validator must remain complete and authoritative; proposal rejection and snapshot isolation add complexity; an accepted proposal still cannot dispatch without deterministic execution rules |

## Architecture decision

**Choose Option A: robotic task assignment is deterministic.**

The scheduler shall assign only work that passes the deterministic eligibility and
readiness policy. It shall use explicit stage, warehouse, robot/control-asset type,
payload, availability, maintenance, safety, resource-block, and exclusive-claim
checks. Ready work shall use the configured deterministic priority/cutoff ordering
and stable tie-breaks. Claims, assignment tokens, due times, task progress, and
movement identities shall be persisted so retries and restarts cannot duplicate
resource claims or inventory effects.

LLM-based assignment is rejected as an authoritative alternative. LLM capabilities
may be used only for isolated, advisory or review scenarios where their output is
validated, attributable to a frozen/synthetic snapshot, and prevented from creating
or changing operational tasks, reservations, claims, or fitness. A malformed,
uncertain, unavailable, or constraint-violating LLM result is rejected; it is not
silently repaired and it does not trigger a fallback that changes the authoritative
assignment decision.

The deterministic scheduler remains the sole authority for simulated task assignment.
It is not authority to operate physical equipment or write external operational systems.

## Consequences and trade-offs

Positive consequences:

- Equal inputs and policy versions produce explainable, repeatable assignment results.
- Missing or blocking readiness evidence fails closed, and exclusive claims prevent
  concurrent assignment of the same resource.
- Persisted clocks, revisions, assignment tokens, and movement identities support
  restart recovery and idempotent effects.
- The fulfillment write path remains available when an LLM provider is unavailable,
  slow, misconfigured, or returns invalid output.
- Tests can exercise boundary conditions directly without depending on probabilistic
  model behavior.

Trade-offs and limitations:

- The policy optimizes for explicit safety and determinism, not guaranteed shortest
  routes, global optimality, or measured physical throughput.
- New warehouse constraints and scheduling objectives require deliberate policy and
  test changes.
- LLM suggestions can still be useful for detached analysis, but they require clear
  separation from operational state and cannot be treated as assignment authority.
- Current evidence covers simulated/local execution only. The package has no physical
  robot adapter, production identity/access control, multi-instance coordination, or
  proof of real-world feasibility.

## Evidence and traceability

| Claim / decision | Evidence file + record / policy version / scenario | Upstream artifact | Confidence / limitation |
|---|---|---|---|
| Deterministic eligibility is the assignment policy | `artifacts/api-server/CONTROL_TOWER.md`, “Fleet task assignment”; `artifacts/fde-artefacts/04_REQUIREMENTS_TRACEABILITY.md`, R3-08 | Stage 09 domain/workflow and requirements artifacts | High for inspected simulator policy; not proof of physical feasibility |
| Missing/blocking readiness evidence prevents assignment | `artifacts/fde-artefacts/02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I8 and SAFE-01; `fleet_readiness.py` | Stage 09 controls | High for local implementation and packaged tests |
| Claims and recovery are restart-safe and idempotent | `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I9/V3-I10; `04_REQUIREMENTS_TRACEABILITY.md`, R3-09 and SAFE-03 | Stage 09 workflow and requirements artifacts | Packaged evidence; backend suite was not rerun on this Windows host |
| LLM output cannot create operational work | `02_DOMAIN_WORKFLOWS_AND_CONTROLS.md`, V3-I15/V3-I16; `TRANSFER_CONTRACT.md` and `BATCHING_CONTRACT.md` | Stage 09 AI boundary and safety controls | High for documented/code-inspected boundary; LLM provider behavior itself is not operational evidence |
| No physical or external actuation exists | `01_AS_BUILT_ARCHITECTURE.md`, security/authority boundary; `04_REQUIREMENTS_TRACEABILITY.md`, R3-20 and SAFE-05 | Stage 09 as-built architecture | High for inspected package; absence is not a certification of a future deployment |

## Reversal trigger

Reconsider this decision only when a replacement can demonstrate, in a controlled,
versioned evaluation, all of the following:

1. Equal or better safety performance against the deterministic policy, including no
   unsafe assignment under missing, conflicting, stale, or blocking readiness data.
2. Complete constraint satisfaction for stage, warehouse, payload, availability,
   maintenance, safety, claim exclusivity, inventory accounting, and authority rules.
3. Bounded latency and a defined degraded mode that preserves deterministic fail-closed
   behavior when the model or provider is unavailable.
4. Reproducible, versioned outputs with sufficient audit data to explain and replay each
   assignment, including model, prompt, context snapshot, and policy versions.
5. Independent evaluation showing a material operational benefit at representative
   workload scale, without granting the model physical or external write authority.
6. Approved security, privacy, identity, monitoring, rollback, and human-override
   controls for the intended deployment boundary.

Until those conditions are evidenced and approved, an LLM remains advisory only and the
deterministic scheduler remains authoritative.

## Open issues / assumptions

| Issue / assumption | Why unresolved | Owner | Downstream impact | Closure evidence |
|---|---|---|---|---|
| Simulator policy is not physical certification | Source weights, durations, topology, and feasibility are synthetic/configured | Fleet and operations engineering | Cannot infer safe real-robot deployment from this ADR | Validated site-specific safety and operational qualification |
| Shared/network authorization is not implemented | The local package relies on loopback and caller-controlled demo persona headers | Platform/security engineering | Additional controls are required before shared or production use | Authenticated deployment threat model and security verification |
| Global scheduling optimality is not claimed | Current policy uses explicit priority/cutoff ordering and stable tie-breaks | Fulfillment engineering | Throughput/travel improvements need separate measured evaluation | Representative benchmark and approved policy revision |

## Completion check

- [x] Minimum ADR content is complete.
- [x] Material claims cite evidence or are labelled assumptions.
- [x] Conflicting/stale evidence is preserved rather than silently resolved.
- [x] Human, deterministic, and AI decision rights are distinguishable.
- [x] The artifact does not contradict approved upstream artifacts.
- [x] LLM use is explicitly limited to advisory or isolated validated scenarios.

## Handoff

**Stage exit contribution:** Complete base AI/application architecture

Do not advance to Stage 11 until the Stage 10 exit gate is defensible.
