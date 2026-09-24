# FDE Operating Model 21 — spine verification (this V2 repo)

**Date:** 2026-09-18  
**Source of truth for phases:** `AI_FDE_Operating_Model.pdf` (21 workflows).  
**Engagement:** synthetic / virtual warehouse control tower. No live robots, PLC, or WMS write.  
**PDF footer:** customer release ≈ Repo 3.0 / 6 months — **not claimed here**.

This pass walked OM 1–21 against the tree, **did not invent agents or OT**, filled only gaps that belong in a virtual deterministic spine, then re-ran tests.

---

## Verdict

| Band | OM | Result |
|---|---|---|
| Discover → select | 1–8 | Already complete from Prompts 01–08 |
| Design → synthetic ready | 9–16 | Complete for **this** engagement after this pass (AI/agent extras remain **not needed**) |
| Customer lifecycle | 17–21 | **Deferred** — documented, not faked |

**Modernization complete (live estate):** still **no**.  
**FDE spine complete for a virtual Repo 2 proof:** **yes**, with FAIL/NOT PROVEN still visible.

---

## What was missed (before this pass)

PDF “essential artifacts” that were **implied** in other files but not named as OM spine deliverables:

| Miss | OM | Why it mattered |
|---|---|---|
| Standalone **DDD Context Map** | 5 | Bounded contexts lived in `01_domain_model.md` §2; map of *relationships* was the SoR matrix without DDD names (ACL, Separate Ways) |
| **Information architecture** that explicitly refuses KG/vector/RAG | 9 | Data contracts existed; PDF still lists semantic layer — we had not written “not required, here is why” |
| **Agent-suitability assessment** as its own artifact | 11 | Buried in 04 GO/NO-GO; PDF wants a named assessment |
| **Component register / SBOM-lite** | 12 | Threat model existed; no package inventory |
| **Delivery specification** (NFRs, rollback, backlog) | 13 | DoR/DoD + TRACEABILITY existed; not one delivery spec |
| **As-built C4** | 14 | Target C4 existed; code had moved on (dashboard, UC-1 modules) |
| **CI evidence** | 14 | pytest locally; no workflow file |
| **Operations runbook** | 16 | CLI/dashboard existed; no operator SOP |
| **OM 17–21 explicit deferral** | 17–21 | Easy to look “unfinished”; they are **out of this mandate** |

---

## What was added (this pass)

| File | OM | What it does |
|---|---|---|
| `specs/01_context_map.md` | 5 | DDD context map + relationship types |
| `specs/09_information_architecture.md` | 9 | Target data architecture; KG/RAG **not required** |
| `specs/11_agent_suitability.md` | 11 | Formal NO-GO for agents; HITL = fail-closed gates |
| `docs/COMPONENT_REGISTER.md` | 12 | Runtime components; no LLM supplier |
| `specs/13_delivery_specification.md` | 13 | NFRs, rollback, backlog, telemetry |
| `specs/14_as_built_c4.md` | 14 | As-built vs target C4 |
| `.github/workflows/pytest.yml` | 14 | CI: pytest on 3.12 |
| `discovery/16_OPERATIONS_RUNBOOK.md` | 16 | How to run, demo, inject, eval |
| `discovery/17_21_LIFECYCLE_DEFERRED.md` | 17–21 | Honest N/A for customer lifecycle |
| This file | 1–21 | Coverage map |

**Not added (correct):** OWL ontology, **runtime** Neo4j/RAG, multi-agent orchestration, live deploy, ISO 42001 AIMS, dollar ROI, `physical_control=enabled`.  
**Added later (teaching only):** explanatory domain KG `specs/09_knowledge_graph.md` — not queried by DecisionEngine.

---

## Phase-by-phase (PDF essential artifacts)

Legend: **HAVE** already · **ADDED** this pass · **N/A** not needed here · **DEFER** Repo 3.0 / customer

| OM | PDF workflow | Essential artifacts vs V2 | Status |
|---|---|---|---|
| 1 | Mandate and field immersion | Charter, RACI, evidence register → `discovery/01_*` | **HAVE** |
| 2 | Discover process and architecture | SIPOC, waste, C4 as-is, landscape → `discovery/02_*` | **HAVE** |
| 3 | Frame problem, RCA, value | SCQA, KPI tree → `discovery/03_*` | **HAVE** |
| 4 | Triage regulation, qualify UC | Screen, go/no-go → `discovery/04_*` | **HAVE** (discipline, not EU filing) |
| 5 | Model the domain | Glossary, bounded contexts, events, **context map** | **HAVE** model · **ADDED** context map |
| 6 | Qualify data and knowledge | Inventories, lineage, quality, provenance | **HAVE** `discovery/06_*` |
| 7 | Evals, impacts, risks | Strategy, golden set, harms | **HAVE** specs/03 + evals |
| 8 | Generate and select options | Trade-off, ADRs | **HAVE** 04_options + ADR-001/002 |
| 9 | Information architecture | Data architecture, contracts, **conditional** ontology/graph | **HAVE** contracts · **ADDED** IA · explanatory KG **ADDED** · runtime graph/RAG **N/A** |
| 10 | AI and application architecture | C4, API, failure modes; RAG/routing **if AI** | **HAVE** 05_target_c4 + api + FM · RAG **N/A** |
| 11 | Agentic / multi-agent | Agent topology **if agents** | **ADDED** suitability = **NO-GO** · topology **N/A** |
| 12 | Security, guardrails, suppliers | Threat model; SBOM/AIBOM if models | **HAVE** 07_threat · **ADDED** component register · AIBOM **N/A** |
| 13 | ADRs and delivery spec | Final ADRs, NFRs, contracts, traceability, backlog | **HAVE** ADRs + TRACEABILITY · **ADDED** delivery spec |
| 14 | Engineer | Source, tests, CI, as-built C4 | **HAVE** src/tests · **ADDED** CI + as-built |
| 15 | Evaluate, attack, assure | Harness, golden, injection; independent lab optional | **HAVE** harness + Prompt 15 · third-party lab **N/A** |
| 16 | Ops, recovery, regulatory evidence | RACI, runbooks, dashboards, chaos, legal record | **HAVE** dashboard + injects · **ADDED** runbook · legal AIMS **N/A** |
| 17 | Deploy progressively | Pilot/canary, live service | **DEFER** |
| 18 | Monitor operational resilience | Drift, prod chaos, cost | **DEFER** |
| 19 | Prove value | Benefits, cost-to-value | **HAVE** treatment KPIs · $ ROI **DEFER** (no cost field) |
| 20 | AIMS lifecycle | Audit, CAPA, scale/retire | **DEFER** / **N/A** until a governed live AI system |
| 21 | Retire and reusable IP | Retirement, credential revoke | **DEFER**; ADRs/C4/evals already reusable IP |

---

## Re-verify (2026-09-18)

- `pytest -q`: **46 passed, 3 xfailed** (`test_om21_spine.py` included).
- `/health` `physical_control: disabled` asserted in `test_om21_spine.py`.
- No new POST `/missions`, no agent package, no `data/` cleaning.

---

## Confidence statement

We are confident that **for a virtual Repo 2 FDE engagement** the 21-step spine is either **done**, **explicitly not needed**, or **explicitly deferred**. We are **not** confident that this is a customer production system — and the PDF does not ask V2 to be that.
