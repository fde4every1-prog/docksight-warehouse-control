# 04 — Use case qualification: AI vs deterministic (STOP GATE)

**FDE Operating Model phase:** 4 — Triage regulation and qualify use case  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 04  
**Date:** 2026-09-17  
**Mode:** Discovery only. No `src/` changes. No agent/RAG/graph specs except as an **optional, disabled-by-default** assistance card.

This file is the **Discover-phase stop gate**. Prompts 05–15 (Repo 2) must not start until the go/no-go below is accepted.

**Decision in one line:** **GO for Repo 2 on a deterministic control plane. NO-GO for LLM/agent execution. Optional recommend-only copilot is not required to pass the brief.**

**LLM is off the write path.** AI may not assign robots, write WMS/inventory, dispatch missions, change speed, release zones, or call any future ActionExecutor.

---

## Inputs from Prompts 01–03 (what this artifact reused)

Prompt 04 does not re-discover the warehouse. It **qualifies** what 01–03 already evidenced.

| Prompt 04 section | From 01 | From 02 | From 03 |
|---|---|---|---|
| Regulatory / synthetic screen | Responsible AI §7; LICENSE; `physical_control` disabled; ISO 42001 as discipline not certification | C4: no live OT; API read-only | Kill list: no LLM write path, no CSV cleaning |
| Prohibited uses | `docs/06` via 01; RACI Execute disabled; EVAL-004 | Recovery map: safety PLC / cert | CTQ: must not hit cutoff via safety bypass |
| Classification of 10 interventions | Evidence register (which files exist) | SoR matrix (who claims truth); journeys as fixtures | RCA 2.1–2.6 (identity, SoR, shadow, `legacy_score`, gates, clocks) + KPI table |
| Non-AI alternatives | Anti-patterns quoted in 01 (`AGENTS.md`) | Running app already counts some conflicts in `diagnostics.py` | Value hypothesis: false certainty, not missing robots |
| Value–risk–feasibility | Charter outcomes (8 brief items) | Three journeys as eval fixtures | Baselines 28.5% false-available, 78.9% inv, 84.2% task, 16.7% DELAYED |
| Use-case cards (max 2) | Bounded roles: Supervisor, Safety (inferred) | SIPOC stages assign / allocate / ship | Three workflows; success criteria |
| Autonomy tiers | RACI Observe/Recommend/Approve/Execute | ABSENT DecisionEngine/Copilot | Checklist item still OPEN → **closed here as a proposal** |
| Go / no-go / kill | Out of bounds list | Do not invent missing twin/RAG as live | Repo 2 success/failure |

Frozen fixtures still: `ORD-000968`, `ORD-000004`, `RBT-0001` (`BOT-COLLISION-*`), extra `ORD-002442`.

---

## 1. Impact and regulatory screen

| Question | Finding | Tag |
|---|---|---|
| What is this system today? | Synthetic educational brownfield repo. No real warehouse, robot, or PII. | EVIDENCED (LICENSE, README, 01 §7) |
| Is it connected to robots / safety PLC / WMS write? | No. `/health` → `physical_control: disabled`. VERIFICATION: consequential control not configured. | EVIDENCED |
| EU AI Act / high-risk if connected later? | Robot dispatch + safety interaction would likely need high-risk operational treatment **if** connected. It is not connected. Do not classify this baseline as a deployed high-risk system. | INFERRED for the hypothetical; EVIDENCED disconnection |
| ISO/IEC 42001 | Design discipline (eval, oversight, residual risk). **No certification claim.** AIMS artifacts ABSENT. | INFERRED / ABSENT |
| Affected groups if a later live system is wrong | Floor people (ZONE_BREACH, NEAR_MISS, HIGH density zones), delayed customers, mis-maintained robots | INFERRED from 01 map + 03 safety counts |
| Data permissible use | Synthetic; local; `.env.example` has no secrets | EVIDENCED |

**Screen result:** Repo 2 remains a **synthetic, read-only-control** proof. Treat **design** as if eligibility and safety were high-stakes (evals, gates, abstain). Do not treat **deployment** as live OT.

---

## 2. Prohibited-use check

Autonomous performance of any of the following is **prohibited** in this engagement and in any target design [EVIDENCED: `docs/06`, EVAL-004, `AGENTS.md`]:

- Safety-system override, e-stop bypass, safety PLC change
- Robot speed-limit change (shadow “low speed only” is a **human** supervisor grant, not a model grant)
- Release of RESTRICTED / human-density / keep-out equivalent to meet cutoff
- Inventing physical inventory quantity
- Blind replay of fleet tasks after outage (EVAL-005)
- Silent overwrite of robot identity from alias, camera, or LLM (EVAL-006)

**Prompt-injection style content** (emails, FINAL_v7 reasons, future chat) is untrusted. It must not become Policy. [INFERRED from 02 trust boundary; 03 shadow RCA]

---

## 3. Classification of ten candidate interventions

Legend: **DETERMINISTIC REQUIRED** | **AI OPTIONAL** | **AI UNSUITABLE** | **OUT OF SCOPE**

| # | Intervention | Class | One-line why | Non-AI alternative |
|---|---|---|---|---|
| 1 | Robot identity resolution (aliases) | **DETERMINISTIC REQUIRED** | Collisions are joins on `robot_aliases.csv` (`RBT-0001` vs `RBT-0002`). An LLM must not pick the “real” robot. | Alias index + collision report; preserve both ids |
| 2 | Safety-cert and CMMS eligibility gate | **DETERMINISTIC REQUIRED** | 203/712 false-available; EVAL-002 is a boolean. Must be identical every run. | `EXPIRED` or open WO ⇒ ineligible unless structured approval field exists (it mostly does not) |
| 3 | Payload and congestion-aware allocation | **DETERMINISTIC REQUIRED** | `legacy_score` is the RCA; three xfail tests are rules. Scoring can be a heuristic; **filters** are hard gates. | Filter then score (battery, site if trusted, payload when present); abstain if zone UNKNOWN |
| 4 | Inventory uncertainty (do not invent qty) | **DETERMINISTIC REQUIRED** | 78.9% disagree; EVAL-001/006. Guessing qty is fabricating physical truth. | Return `{wms,erp,vision,reserved,uncertain=true}`; never a single invented number |
| 5 | WES vs fleet task state reconciliation | **DETERMINISTIC REQUIRED** | 84.2% split; `ORD-000968` SHIPPED vs EXECUTING. Completion is a state machine, not a paragraph. | Conflict flag; order not COMPLETE while sources disagree |
| 6 | Event-time vs ingest-time ordering | **DETERMINISTIC REQUIRED** | 99.7% skew; EVAL-003. Sort is a comparator. | Order by `event_time`; keep `recorded_time` as ingest evidence |
| 7 | Carrier cutoff using live email / OMS staleness | **DETERMINISTIC REQUIRED** for fields; **AI OPTIONAL** for the email text | `carrier_cutoff`, TMS DELAYED, Carrier-A are structured. The **sentence** “SLA will not refresh until midnight” is unstructured. | Prefer TMS DELAYED + Carrier-A + shadow CSV `reason=carrier_cutoff`; do not trust OMS alone. Parsing `ops_emails.txt` may be copilot |
| 8 | Parsing shadow emails / FINAL_v7 | **DETERMINISTIC REQUIRED** for FINAL_v7; **AI OPTIONAL** for emails | FINAL_v7 is already a 216-row CSV (join on `order_id`). Emails are four short unstructured notes. | Join FINAL_v7 deterministically. Emails: optional NLP to extract entities; **never** auto-grant “supervisor approved” |
| 9 | Explaining a cascade to a supervisor | **AI OPTIONAL** | Cascade reasoning is correlation of **already computed** evidence (`cascade_001.json` + journeys). Narrative is assistance, not control. | Deterministic evidence bundle (IDs, conflicts, gates fired) + a template. LLM may draft the note if evals pass |
| 10 | Execute robot motion, e-stop, speed change, safety-zone release | **OUT OF SCOPE** and **AI UNSUITABLE** | Physical control disabled; `docs/06`; EVAL-004. | Human + real OT systems that are **not in this repo**. Software must refuse |

`docs/04_target_capabilities.md`: rules, services, eventing, optimization are valid; **KG, twin, RAG, agents are not mandatory.** `AGENTS.md`: do not bolt an LLM on a dashboard; do not make KG/twin/agent mandatory unless warranted. **Not warranted for #1–6, #10.**

---

## 4. Value–risk–feasibility matrix

Scale: H / M / L. Feasibility is **in this repo** (local Python, existing CSVs, tests).

| Item | Value if done well | Safety / authority risk if done with AI | Feasibility without AI | Repo 2? |
|---|---|---|---|---|
| 1 Identity | Stops WO/cert attaching to the wrong body | High if LLM invents `R-99` | H — CSV join | **Yes — spine** |
| 2 Eligibility gates | Directly attacks 28.5% false-available | High if prompt can waive EXPIRED | H — booleans | **Yes — spine** |
| 3 Constraint allocator | Turns xfail into passing new path | M if score used to skip filters | H — filter then score | **Yes — spine** |
| 4 Inventory uncertainty | Stops false picks (78.9%) | High if model “picks 205” | H — retain three qtys | **Yes — spine** |
| 5 Task/order conflict | Stops false SHIPPED (`ORD-000968`) | M if model declares COMPLETE | H — state compare | **Yes — spine** |
| 6 Temporal order | Stops false sequence | L | H — sort key | **Yes — spine** |
| 7 Cutoff (structured) | 16.7% DELAYED; `ORD-000004` | M if used to justify unsafe reroute | H — TMS + carrier + FINAL_v7 | **Yes — spine** |
| 8 Email parse | Faster exception reading | H if “supervisor approved” becomes a gate | M — four emails can be **fixtures** without NLP | Optional |
| 9 Cascade explain | Less time for exception_handlers | L if recommend-only + citations | M — template may be enough | Optional |
| 10 Execute OT | None in this training repo | **Unacceptable** | N/A — disabled | **No** |
| KG / digital twin as platform | Unproven here | M complexity | L — not in repo, not evidenced as required | **No** |
| Multi-agent dispatcher | Conflicts with brief + evals | **Unacceptable** | — | **Kill** |

---

## 5. Bounded autonomy tiers (closes discovery checklist)

Proposed for target design. **Not implemented.** Aligns to 01 RACI and `docs/06`.

| Tier | Allowed | Who | Examples | LLM? |
|---|---|---|---|---|
| **T0 Observe** | Read files, diagnostics, conflict counts | Software | `/diagnostics`, SoR flags | No |
| **T1 Recommend** | ActionProposal + evidence + uncertainty | Software; optional copilot drafts text | “Do not assign RBT-0020; cert EXPIRED” | Optional text only |
| **T2 Reversible low-risk** | Policy-listed only, never safety, never OT | Deterministic DecisionEngine **ABSENT today** | N/A in Repo 1; still no WMS write | No |
| **T3 Material ops** | Needs Supervisor | Human | Wave pull-forward, using FINAL_v7 | No |
| **T4 Safety-critical** | Needs Safety authority | Human | e-stop, speed, zone release, cert waiver | **Never** |
| **T5 Physical execute** | Out of scope | — | Motion, PLC, WMS write | **Never** |

Shadow email “supervisor approved low-speed tonight” is a **T4-shaped** human act recorded in unofficial text. Repo 2 must **not** parse that into an automatic grant (would skip CMMS). Treat as evidence of a workaround, not as Policy.

---

## 6. Use-case cards (exactly two)

### UC-1 — Deterministic warehouse truth and eligibility spine (REQUIRED for Repo 2)

| Field | Content |
|---|---|
| Name | Conflict-aware eligibility and allocation (observe + refuse + explain in structured fields) |
| Problem | False certainty: wrong id, false available, WMS qty, WES EXECUTING, stale cutoff (`03` hypothesis) |
| Users | FDE / future supervisor viewing CLI or API (synthetic) |
| In scope | Alias collision report; eligibility (cert, CMMS, cal, connectivity); inventory uncertain object; WES/fleet conflict flag; event_time ordering; filter-then-score allocator; diagnostics/API extensions; tests vs xfail + EVAL-001–006; fixtures `RBT-0001`, `ORD-000004`, `ORD-000968` |
| Out of scope | Physical execute; LLM; KG/twin; cleaning CSV; silent identity merge |
| Data | Existing Repo 1 files only |
| Evals before “autonomy” | There is **no** autonomy. Evals still required before any recommend-as-if-assign API |
| Value | Attacks CTQs; three workflows in `03` §5; measurable vs §3 formulas |
| Residual risk | Cross-DC assignment meaning UNKNOWN; as-of cutoff proxy PARTIAL |
| Go | **GO** |

### UC-2 — Exception copilot, recommend-only (OPTIONAL, default OFF)

| Field | Content |
|---|---|
| Name | Evidence-citing exception note |
| Problem | Humans read emails + FINAL_v7 + conflicting screens (`03` waste / `02` shadow SIPOC) |
| Users | Supervisor analogue |
| In scope | Retrieve **already computed** UC-1 bundle + quote shadow files; draft a recommendation; cite row ids |
| Out of scope | Changing Eligibility, Policy, Execution; treating “you are the safety officer” as authority; RAG over SOPs for live occupancy |
| Non-AI alternative | Markdown/JSON evidence pack generated by UC-1 (sufficient for the brief) |
| When allowed | Only after UC-1 evals pass; copilot cannot import an executor; injection tests required |
| Go | **OPTIONAL / not required.** Default **NO-BUILD** for first Repo 2 increment |

No third card. No agent dispatcher. No mandatory graph.

---

## 7. Go / no-go / kill

### GO (Discover → Repo 2)

- Implement **UC-1** only as the first increment (Prompts 05–13 later).
- Keep brownfield CSV contradictions as evidence.
- Use Prompt 03 formulas for before/after.
- Physical control stays disabled.
- Evals before any endpoint that looks like a decision.

### NO-GO

- LLM/agent that assigns robots or writes WMS.
- Mandatory knowledge graph, digital twin, or multi-agent orchestration.
- Using Prompt 03 cutoff-proxy C (84% as-of) as the success KPI.
- “Supervisor approved” parsed from email as a safety waiver.
- Starting Prompt 05 without this gate accepted.

### KILL (stop the use case / increment)

- Any design where the warehouse cannot run if the LLM is down (contradicts Wi-Fi/outage inject intent).
- Any path from Copilot/chat to ActionExecutor / `choose_robot` without a deterministic gate.
- EVAL-002 or EVAL-004 failing on the **new** path.
- Data rewritten so inventory sources agree.

---

## 8. Explicit statements

1. **The LLM never touches a write path.** Recommendations are data; Execution of OT is disabled and out of scope.
2. **Deterministic software owns** identity, eligibility, inventory uncertainty, task/order conflict, and time.
3. **AI is optional assistance** for unstructured shadow text and supervisor narrative, after UC-1.
4. **None of RAG, ontology, KG, digital twin, or agents is required** to satisfy `CHALLENGE_BRIEF.md` (`docs/04`).
5. **Do not fix every inconsistency**; some are legitimate competing perspectives (`AGENTS.md`). Mark them. Do not collapse them.

---

## 9. Discovery-phase completion (FDE OM 1–4)

Yes. **Prompts 01–04 are the Discover phase** for this capstone (Operating Model phases 1–4). They are not Repo 2 and not Repo 3.

| OM | Prompt | Artifact | Status |
|---|---|---|---|
| 1 Mandate / field immersion | 01 | `discovery/01_MANDATE_AND_FIELD_IMMERSION.md` | Done |
| 2 Process and architecture | 02 | `discovery/02_CURRENT_STATE_PROCESS_AND_ARCHITECTURE.md` + `02_SYSTEM_OF_RECORD_MATRIX.md` | Done |
| 3 Problem, RCA, baseline | 03 | `discovery/03_PROBLEM_FRAME_AND_BASELINE.md` | Done |
| 4 Qualify use case | 04 | **this file** | Done |

Library discovery gate:

- [x] 01 mandate
- [x] 02 architecture
- [x] 02 SoR matrix
- [x] 03 problem/baseline
- [x] 04 suitability
- [x] Three named IDs: `ORD-000968`, `ORD-000004`, `RBT-0001`
- [x] Baselines computed or NOT COMPUTABLE
- [x] Written go/no-go: **deterministic spine first**

Checklist item **Propose bounded autonomy tiers**: **CLOSED as a proposal** (this file §5). Implementation of gates is Repo 2 (Prompt 10+). **Reconcile inventory** stays OPEN on purpose (do not wipe sources).

**Stop.** Do not write `specs/` until this GO is accepted. Next is Prompt 05 (domain model) only after you say to proceed — that is **beyond Discover**.
