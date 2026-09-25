# ADR-002 — LLM off the write path

**Status:** Accepted  
**Date:** 2026-09-17  
**Prompt:** 08  
**Supersedes:** none  
**Complements:** ADR-001

---

## Context

Canonical loop: Observe → Reason → Propose → Decide → Approve → Execute → Observe outcome.  
Invariant from the prompt library and 04 GO: **the LLM never touches a write path.**

Repo 1 `/health` returns `physical_control: disabled`. EVAL-004/020/022 and I10 forbid motion, e-stop, speed, zone release, WMS write, and Policy changes from untrusted text. Inject intent: floor Wi-Fi / cloud AI outage must not disable hard gates.

A future copilot (Option B) is the main risk of accidental write-path coupling.

---

## Decision

1. **Eligibility, Conflict, Uncertainty, Decision (ALLOW/DENY/ABSTAIN), and any allocator** are deterministic code. They must not call an LLM.
2. **Execution** of OT/WMS/robot commands is **disabled** in this repo. An ActionExecutor module, if introduced, is a stub that refuses OT writes.
3. **Copilot / LLM** (if present) may only produce **ActionProposal** text citing evidence already computed by (1). It must **not** import or invoke ActionExecutor, `choose_robot` (UC-1 or legacy), repository writes, or Policy mutation.
4. Tests must **fail** if Copilot (or equivalent) can import ActionExecutor (Prompt 10/11).
5. If the LLM is unavailable, UC-1 (1)–(2) still run.

“Write path” here includes: robot assign as a side effect, WMS/inventory mutation, CSV mutation, safety override, and setting Eligibility=ELIGIBLE from a prompt.

---

## Consequences

**Good:** EVAL-002/004/022 are testable; Option A survives cloud-down; injection cannot grant cert waiver.

**Trade-off:** No “agent demo” that clicks dispatch. Stakeholder demo is refuse/uncertain/conflict.

**Enforcement (later code):** package boundary + test; not a prompt instruction alone.

---

## Evidence

- `docs/06_security_safety_assurance.md`
- `discovery/04_USE_CASE_AND_AI_SUITABILITY.md` §8
- `specs/01_domain_model.md` I10; LLM not a mutating entity
- `evals/golden_cases_repo2.jsonl` EVAL-004, EVAL-020, EVAL-022
