# 06 — Hard gates and execution authority

**FDE Operating Model phase:** 11–12 — Bounded autonomy, hard gates  
**Prompt:** `AI_Native_Warehouse_Robotics_PROMPT_LIBRARY_15_new.md` Prompt 10  
**Date:** 2026-09-17  
**Mode:** Specs + xfail tests. No UC-1 implementation in `src/` this prompt. Do not greenwash by deleting `tests/test_known_legacy_defects.py` xfails.

**The DecisionEngine — not an LLM — is the gate.** (ADR-002, I10)

**Companions:** `specs/06_autonomy_tiers.md`, `tests/test_hard_gates_spec.py`  
**Implements (later):** EligibilityPolicy + DecisionEngine in `specs/05_target_c4.md`

---

## File naming (why this is `06_` not `10_`)

| File | Prompt |
|---|---|
| `specs/05_target_c4.md` | 09 |
| **`specs/06_hard_gates_and_authority.md`** (this) | **10** |
| `specs/06_autonomy_tiers.md` | 10 |
| `specs/07_threat_model.md` | 11 |

---

## Inputs from Prompts 04–09

| Input | How used |
|---|---|
| 04 T0–T5; prohibited uses | Authority: auto-refuse only; T4/T5 never software |
| 04 “supervisor approved tonight” | G2: workaround evidence, not a grant |
| I1–I12 | Each gate cites an invariant |
| ADR-001/002 | Deterministic engine; copilot cannot pass a gate |
| 05 C4 DecisionEngine ABSTAIN | G8 |
| 05 API `/preview/decide` | ALLOW still `execution.applied=false` |
| 05 FM-1–4 | Cutoff miss is legal; safety bypass is not |
| EVAL-002/004/001/019/005 | `must_not` copied into tests |

---

## 1. Rule: gates vs score vs narrative

| Kind | May it block assign / complete / path? | Who computes it |
|---|---|---|
| **Hard gate G1–G8** | Yes. Fail = INELIGIBLE, not completable, refuse path, DENY, or ABSTAIN | Deterministic DecisionEngine / EligibilityPolicy |
| Filter-then-score | Only **after** all applicable gates pass | Allocator |
| `legacy_score` | **Never** as a gate | LEGACY-KEEP baseline only |
| Shadow email / FINAL_v7 reason / future copilot text | **Never** | Untrusted; may add Conflict only |
| Cutoff pressure | **Never** overrides G1–G7 | I7 may surface DELAYED; I6 still holds |

A **recommendation to miss cutoff is legal.**  
A **recommendation to bypass safety is not** — Decision must DENY.

---

## 2. Gate catalogue

Every gate: fail-closed. Missing field that the gate needs is **not** a pass (usually G8 ABSTAIN or the conservative INELIGIBLE listed below).

### G1 — Safety certification

| | |
|---|---|
| When | `safety_cert_status` is `EXPIRED` **or missing/empty** |
| Result | Eligibility **INELIGIBLE**; Decision **DENY** assign |
| Invariant | I1 |
| Fixture | 35 expired-but-connected robots; EVAL-002 |
| `must_not` | Assign because `connectivity=ONLINE` or battery is high |
| Not a grant | Copilot/email “ignore expired cert” |

`EXPIRING` is not G1-fail (Conflict `CERT_EXPIRING`; still eligible unless another gate fails).

### G2 — Open CMMS without recorded safety release

| | |
|---|---|
| When | Maintenance WO `cmms_status` in `{OPEN, IN_PROGRESS}` for that `robot_id`, **and** there is no **recorded** safety release with role `SafetyOfficer` bound to that WO |
| Result | **INELIGIBLE** / **DENY** assign |
| Invariant | I5 |
| Fixture | `WO-000380` / `RBT-0001`; EVAL-014 |
| `must_not` | Treat `fleet_availability=AVAILABLE` as a pass |

**Explicitly not a grant:** shadow text such as “supervisor approved tonight” / “low speed only.” That is evidence of a **workaround** (Conflict), not Approval. Prompt 11 will re-test this as injection.

A valid release (when it exists later) must be: structured record, role, timestamp, **single-use**, WO id. Unstructured notes never qualify.

### G3 — Payload insufficient

| | |
|---|---|
| When | Task payload is **known** and `robot.payload_kg` < task payload |
| Result | **INELIGIBLE** |
| Invariant | I12 |
| Fixture | xfail payload test in `test_known_legacy_defects.py` (keep that xfail on **legacy** `choose_robot`) |
| `must_not` | Prefer the high-battery undersized robot |

If task payload is **ABSENT/UNKNOWN** → **G8 ABSTAIN** (do not assume fit). Do not fail G3 on missing task payload.

### G4 — Target zone blocked or occupancy unknown

| | |
|---|---|
| When | Target zone `robot_access=RESTRICTED`, **or** occupancy UNKNOWN, **or** task `blocked_zone` equals robot zone / target |
| Result | **Refuse path / assign** (INELIGIBLE or DENY) |
| Invariant | I6 |
| Fixture | 43 RESTRICTED zones; xfail congestion test; EVAL-009, EVAL-004 |
| `must_not` | Release the zone to hit Carrier-A cutoff |

Occupancy UNKNOWN is fail-safe refuse, not “assume empty.”

### G5 — Inventory uncertain

| | |
|---|---|
| When | `wms_qty`, `erp_qty`, `vision_qty` are not all equal |
| Result | Observation **UNCERTAIN**; do **not** treat as pickable truth; Decision **ABSTAIN** (or DENY allocate-as-known) |
| Invariant | I3 |
| Fixture | `SKU-01146` 205/205/202; EVAL-001, EVAL-006 |
| `must_not` | Emit a single `available_qty` as truth; pick a source by system name |

`legacy_available_qty` may be returned **labeled legacy** only.

### G6 — WES / fleet terminal-state conflict

| | |
|---|---|
| When | `wes_status` ≠ `fleet_status` on the same `task_id` |
| Result | Conflict `TASK_STATUS`; **do not close** Task or parent Order (`completable=false`) |
| Invariant | I4 |
| Fixture | `TSK-000968-1` / `ORD-000968`; `TSK-000004-1`; EVAL-019 |
| `must_not` | Mark SHIPPED/COMPLETE while PACK_FEED EXECUTING |

After outage, G6+G8: do not blindly replay all fleet rows (I11, EVAL-005, FM-4).

### G7 — Safety-zone / e-stop / speed-limit change

| | |
|---|---|
| When | Proposed action is e-stop bypass, speed-limit change, safety-zone release, safety PLC write, or cert waiver |
| Result | **Never autonomous.** Decision **DENY** unless a **SafetyOfficer** Approval already exists as a structured record (it does **not** in this snapshot). In Repo 2, treat as **always DENY** + `physical_control: disabled` |
| Invariant | I6, I10; tier T4/T5 |
| Fixture | EVAL-004, EVAL-022; `/health` |
| `must_not` | ALLOW execute; parse email into a waiver; enable physical control |

UC-1 may **recommend** that a human miss cutoff instead. That is T1, not G7.

### G8 — Evidence UNKNOWN → abstain

| | |
|---|---|
| When | Required evidence is UNKNOWN: occupancy, unmatched identity (`AMR-044`), unknown mission ack / no command id, task payload missing when payload matters, vision collapsed with no physical count, SITE_MISMATCH meaning UNKNOWN, conflicting terminal states with no resolver |
| Result | Decision **ABSTAIN** (Eligibility may also be `ABSTAIN`) |
| Invariant | Catch-all for I3/I4/I9/I11/I12-absent; 05 FM-1–4 |
| `must_not` | Guess; pick a SoR by name; invent command ids and treat them as acks |

ABSTAIN is a **successful** control-plane outcome (HTTP 200 + `decision=ABSTAIN`), not a 500.

---

## 3. Evaluation order (deterministic)

On assign / preview-allocate:

1. IdentityResolver (collisions retained; unmatched ≠ merge) — not a numbered G but **before** gates
2. **G1** cert  
3. **G2** CMMS  
4. Calibration OVERDUE (I2; same INELIGIBLE family as G1/G2, not a new letter)  
5. Connectivity OFFLINE → INELIGIBLE; INTERMITTENT → Uncertainty / may G8  
6. **G3** payload if known else G8  
7. **G4** zone / occupancy  
8. **G5** if the action is a pick that needs qty  
9. Score **only ELIGIBLE** remainder  
10. **G7** if proposal is safety-shaped → DENY  
11. **G6** if completing an order  
12. **G8** if anything required is still UNKNOWN → ABSTAIN  

First failing hard gate wins. Do not “average” with battery score.

---

## 4. Authority matrix (who may pass a gate)

| Action | Software auto | Supervisor | SafetyOfficer | LLM / Copilot |
|---|---|---|---|---|
| Observe conflicts | Yes (T0) | — | — | No authority |
| Recommend miss cutoff | Yes, T1 text/JSON | May accept | — | Text only if UC-2 later |
| Recommend bypass safety | **No — DENY** | No | Still DENY without OT policy | **No** |
| Assign ELIGIBLE robot (preview) | Preview ALLOW only; **no OT apply** | T3 if material wave change | — | No |
| Close order | Only if G6 pass | T3 | — | No |
| Cert waiver / zone release / speed / e-stop | **Never** | No | Required for T4; still no OT in this repo | **Never** |
| Physical execute | **Never** (G7/I10) | — | — | **Never** |
| Turn G2/G1 pass from email | **Never** | Email ≠ Approval | Structured release only | **Never** |

**Approval** (when introduced): role, expiry, single-use, bound object id. Shadow CSV `manager_override` on `ORD-002442` is **not** Approval.

---

## 5. Python contract (Prompt 12+ must satisfy `test_hard_gates_spec.py`)

Stable imports (create these modules at implementation time; tests **xfail on ImportError** until then):

| Module | Function | Returns |
|---|---|---|
| `warehouse_control.eligibility.policy` | `evaluate_eligibility(robot, task, context=None)` | `{"eligibility": "ELIGIBLE"|"INELIGIBLE"|"ABSTAIN", "gates_failed": ["G1", ...]}` |
| `warehouse_control.inventory.uncertainty` | `observe_inventory(row)` | Triple + `"uncertain": bool`. No unlabeled `available_qty` |
| `warehouse_control.tasks.reconcile` | `reconcile_task(task)` | `{"completable": bool, "conflict": bool}` |
| `warehouse_control.decision.engine` | `decide(action_proposal)` | `{"decision": "ALLOW"|"DENY"|"ABSTAIN", "execution": {"applied": false, "physical_control": "disabled"}}` |

`context` may include `maintenance_rows`, `zone`, `safety_release`, `shadow_note`.  
`action_proposal` includes `intent` (e.g. `assign`, `close_order`, `miss_cutoff`, `release_zone`, `speed_change`, `estop_bypass`) plus evidence.

`legacy.allocator.choose_robot` **must remain** the failing baseline. Do not retarget the three known-defect xfails to pass without a new function.

---

## 6. What Prompt 10 does *not* do

- No EligibilityPolicy implementation (Prompt 12)
- No allocator swap (Prompt 13)
- No threat model (Prompt 11)
- No enabling `physical_control`

**Next:** Prompt 12 — implement identity, eligibility, inventory uncertainty (Prompt 11 threat model exists).
