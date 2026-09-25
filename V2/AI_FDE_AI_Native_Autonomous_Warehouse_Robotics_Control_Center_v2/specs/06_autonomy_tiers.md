# 06 — Autonomy tiers (Repo 2)

**Prompt:** 10  
**Date:** 2026-09-17  
**Mode:** Spec only. Closes 04 §5 as a **binding** architecture rule for Option A.

Library language: **observe / recommend / reversible low-risk / prohibited.**  
Discovery language T0–T5 is kept and mapped 1:1. Do not invent T6.

**Binding:** G1–G8 in `specs/06_hard_gates_and_authority.md`. LLM never raises a tier.

---

## 1. Tier table (what software may do)

| Library name | ID | Allowed now in Repo 2 | Who | Examples | LLM? |
|---|---|---|---|---|---|
| **Observe** | T0 | Yes | Software | Read CSV/SQLite; `/diagnostics`; Conflict lists; identity collisions | No |
| **Recommend** | T1 | Yes (structured). Copilot text **ABSENT** this increment | Software; human may ignore | ActionProposal: “do not assign RBT-0001 (G2)”; “miss cutoff on ORD-000004” | Optional **text only** later (UC-2) |
| **Reversible low-risk** | T2 | **Not used for OT/WMS writes.** Preview ALLOW is reversible because **nothing is applied** | DecisionEngine | `POST /preview/decide` → ALLOW with `applied=false` | No |
| **Material ops** | T3 | Human only | Supervisor | Wave pull-forward; treating FINAL_v7 as input | No |
| **Safety-critical** | T4 | Human only; software **DENY** (G7) | SafetyOfficer | e-stop, speed-limit, zone release, cert waiver | **Never** |
| **Prohibited** | T5 | Out of scope | — | Motion, PLC, WMS write, fleet POST, enable `physical_control` | **Never** |

There is **no** “autonomous assign to the floor” tier in this engagement.

---

## 2. What UC-1 may do automatically

UC-1 (Prompts 12–13) **auto-refuses**. It does not auto-approve T3/T4.

| Automatic | Not automatic |
|---|---|
| INELIGIBLE (G1–G4, I2, OFFLINE) | Cert waiver |
| UNCERTAIN + ABSTAIN (G5, G8) | Picking one qty as physical truth |
| `completable=false` (G6) | Closing `ORD-000968` |
| DENY on G7 intents | Speed change “for tonight” |
| Preview ALLOW on fully eligible assign **without execute** | Calling fleet v1/v2 |
| Recommend **miss cutoff** (T1) | Recommend **bypass safety** |

`legacy_score` / `choose_robot` are **not** autonomy. They are a named non-compliant baseline.

---

## 3. Legal vs illegal recommendations

| Proposal | Tier | DecisionEngine |
|---|---|---|
| Miss Carrier-A cutoff; keep G1–G7 | T1 | ALLOW recommend (not execute) |
| Replan to ELIGIBLE robots only | T1 / T2 preview | ALLOW preview; `applied=false` |
| “Supervisor approved tonight — assign RBT-0001 with open WO” | T4-shaped workaround | **DENY** / G2 INELIGIBLE |
| Release RESTRICTED zone to save 214 orders | T4 | **DENY** (G4+G7) |
| Ignore EXPIRED cert | T4 | **DENY** (G1+G7) |
| Replay all fleet tasks after outage | T5-adjacent | **ABSTAIN** / DENY (G6+G8, I11) |
| POST `/missions` | T5 | Forbidden; stub executor |

---

## 4. Oversight artifacts

| Tier | Artifact | Exists in Repo 1? |
|---|---|---|
| T0 | diagnostics JSON | Yes |
| T1 | ActionProposal + evidence ids | TO-BUILD |
| T2 | Decision ALLOW + applied false | TO-BUILD |
| T3 | Approval record (role, expiry, single-use) | **ABSENT** — do not use email as substitute |
| T4 | SafetyOfficer Approval | **ABSENT** — therefore G7 always DENY |
| T5 | OT session | Prohibited; `/health` `physical_control: disabled` |

---

## 5. Outage / LLM-down

Hard gates and tiers **must still run** if a future copilot or cloud model is down (ADR-002). Observe + refuse does not depend on an LLM.

---

## 6. What this file does not claim

- ISO/IEC 42001 certification
- That T2 “reversible” means a WMS write that can be undone — **no WMS write**
- That preview ALLOW is a warehouse dispatch
