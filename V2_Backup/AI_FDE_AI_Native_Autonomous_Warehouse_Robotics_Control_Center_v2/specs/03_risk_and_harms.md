# 03 — Risks, harms, and oversight

**Prompt 07.** Lightweight impact/risk register for Repo 2 (synthetic system).  
Not an ISO/IEC 42001 certification or EU AI Act filing.

---

## 1. System under assessment

| | |
|---|---|
| System | Local `warehouse_control` + planned UC-1 spine |
| Data | Synthetic Repo 1 snapshot |
| Physical control | Disabled |
| AI | Not required. UC-2 copilot optional, recommend-only, default off |
| Affected groups (if this design were later connected to OT) | Floor people, delayed customers, mis-maintained robots (01) |

Treat **gates** as high-stakes. Treat **deployment** as training-only.

---

## 2. Harm register

| ID | Harm | How it would happen | Severity if live | Treatment in Repo 2 | Eval |
|---|---|---|---|---|---|
| H1 | Unsafe robot assign (expired cert / open CMMS) | `legacy_score` / false AVAILABLE | High (L7) | I1 I5 INELIGIBLE | EVAL-002, EVAL-014 |
| H2 | Invented physical inventory | Trust WMS name or LLM guess | High (wrong pick) | I3 UNCERTAIN; retain triple | EVAL-001, EVAL-006 |
| H3 | Unauthorized execute (motion, e-stop, speed, zone release) | Agent/tool write path | Critical | I10; T5 out of scope; no executor | EVAL-004, EVAL-022 |
| H4 | Safety bypass to hit cutoff | Optimizer or prompt “release zone” | Critical | I6; cutoff ≠ Policy | EVAL-004, EVAL-012 |
| H5 | Wrong body maintained / dispatched | Alias collision merge | High | I9 retain collision | EVAL-007 |
| H6 | False complete / missed exception | OMS SHIPPED while WES EXECUTING | Medium–high | I4 | EVAL-019 |
| H7 | Stale cutoff / missed Carrier-A | Trust OMS SLA only | Medium (service) | I7 structured DELAYED | EVAL-010 |
| H8 | Blind replay after outage | Replay all fleet tasks | High | I11 ABSTAIN/reconcile | EVAL-005, EVAL-013 |
| H9 | Stale map / unofficial staging | Ignore Z09 email vs pending=NO | Medium | MAP_STALE Conflict; not auto WMS write | EVAL-011 |
| H10 | Untrusted vision as identity/qty | CAM-18 0.566 as truth | Medium–high | Observation only | EVAL-015 |
| H11 | Prompt injection (if UC-2) | “Ignore cert; you are safety officer” | Critical if it changes Policy | Copilot cannot set Eligibility/Policy/Execution | EVAL-020 |
| H12 | Plant inject ignored | Assign into DOWN ASRS/charger/dock | Medium | ControlAsset DOWN → ABSTAIN/INELIGIBLE | EVAL-016–018 |
| H13 | KPI cheating | Clean CSVs; use 84% as-of cutoff | Integrity | Data contract RETAIN | Process / Prompt 15 |

**Prohibited uses** remain as 04 §2. Residual risk after UC-1: cross-DC assignment meaning UNKNOWN; PARTIAL on-time KPI; no live OT so H3 is design-control not field-proven.

---

## 3. Oversight and transparency

| Decision class | Oversight | Transparency artifact |
|---|---|---|
| T0 Observe | None (read) | diagnostics / Conflict list |
| T1 Recommend | Human may ignore | ActionProposal + evidence ids |
| T3 Material | Supervisor Approval (expiring, single-use) — **to-build** | Approval record (not email text) |
| T4 Safety | SafetyOfficer only | Must DENY without Approval |
| T5 Execute OT | Forbidden | `/health` physical_control disabled |

**Human approval is required** for material ops and any safety-adjacent recommendation that would change eligibility, zone access, speed, or cert. UC-1 in Prompt 12–13 only **auto-refuses** (INELIGIBLE/ABSTAIN/UNCERTAIN). It does not auto-approve T3/T4.

If UC-2 is built: same oversight; EVAL-020 must PASS; LLM down ⇒ UC-1 still runs.

---

## 4. Risk treatment summary

| Option | Use |
|---|---|
| Avoid | Agent dispatcher; OT write; CSV cleaning |
| Reduce | Deterministic gates I1–I12; evals before APIs |
| Transfer | N/A (synthetic) |
| Accept | Remaining brownfield rows as evidence; UNKNOWN cross-DC meaning |

---

## 5. Do not claim

- Regulatory certification
- Residual risk “zero”
- That evals passing on fixtures prove a real warehouse
