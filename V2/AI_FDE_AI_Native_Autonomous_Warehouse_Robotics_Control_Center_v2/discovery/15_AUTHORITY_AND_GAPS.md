# 15 — Authority boundaries and production-readiness gaps

**Prompt:** 15  
**Date:** 2026-09-17  
**Binding:** `specs/06_hard_gates_and_authority.md`, `specs/06_autonomy_tiers.md`, ADR-001, ADR-002, `docs/06`.

Physical control remains **disabled**. There is **no** “autonomous assign to the floor” tier in this engagement.

---

## 1. Who may do what (T0–T5)

| Tier | Library name | Software may | Human may | LLM |
|---|---|---|---|---|
| T0 | Observe | Read CSV/SQLite; diagnostics; Conflict lists; identity collisions | Read the same | No |
| T1 | Recommend | Structured ActionProposal: miss cutoff; do not assign `RBT-0001` | Ignore the proposal | Optional **text only** later (UC-2 **ABSENT**) |
| T2 | Reversible low-risk | Preview ALLOW with `applied=false` | Treat preview as advice | No |
| T3 | Material ops | **Refuse to auto-apply** (no approval store) | Wave pull-forward, FINAL_v7 as *input* | No |
| T4 | Safety-critical | **DENY** (G7) | SafetyOfficer cert waiver / speed / zone — **not in this repo as a record** | **Never** |
| T5 | Prohibited | Stub executor; no fleet POST; no WMS write | Real OT systems **not in this repo** | **Never** |

UC-1 **auto-refuses**. It does not auto-approve T3/T4.

Shadow email “supervisor approved low-speed tonight” is a **T4-shaped workaround in unofficial text**. It is **not** Approval.

---

## 2. Authority map for this increment

| Decision | Owner | Evidence required | Gap |
|---|---|---|---|
| Mark robot INELIGIBLE (G1–G4, I2, OFFLINE) | EligibilityPolicy | `robots.csv` + `maintenance.csv` + zones | None for refuse |
| Mark inventory UNCERTAIN | InventoryObservation | WMS/ERP/vision triple | Physical count process **OPEN** |
| Refuse order complete | TaskReconciler | WES vs fleet | No write-back to OMS/WMS |
| Recommend miss cutoff | DecisionEngine T1 | TMS DELAYED + shadow mention | Not a TMS update |
| Release RESTRICTED zone | SafetyOfficer | Structured record | **ABSENT** ⇒ always DENY |
| Cert waiver | SafetyOfficer | Structured record | **ABSENT** ⇒ G1 stands |
| Dispatch mission | Out of scope | Fleet v1/v2 | Executor stub; `applied=false` |
| Enable `physical_control` | Out of scope | Separate safety case | Must stay disabled |

---

## 3. Trusted vs untrusted (do not invert)

**Trusted as gate *inputs* (may fail a robot, never overwritten by chat):**

- `safety_cert_status`, `calibration_status`, `connectivity`, `payload_kg`
- CMMS `OPEN` / `IN_PROGRESS` + `work_order_id`
- Zone `RESTRICTED` / occupancy UNKNOWN
- Inventory triple (disagreement → G5)
- WES vs fleet status (split → G6)

**Not trusted as a pass:** `fleet_availability=AVAILABLE`, `health_status=HEALTHY`, SQLite `/robots/{id}`, OMS SLA alone, battery-high `legacy_score`.

**Untrusted (Conflict only):** `ops_emails.txt`, FINAL_v7 reasons, telemetry payloads, cascade informal names (`AMR-044`), future chat, “ignore gates.”

---

## 4. Production-readiness gaps (keep visible)

| ID | Gap | Severity for live | Repo 2 handling |
|---|---|---|---|
| GAP-1 | T3/T4 approval store ABSENT (role, expiry, single-use) | High | Fail closed (G2/G7) |
| GAP-2 | Command ids / fleet acks ABSENT | High (replay) | G8 ABSTAIN on replay-all (EVAL-005/013) |
| GAP-3 | IdentityResolver not on legacy `/robots/{id}` | High (wrong body) | Additive `/identity` routes; SQLite path unchanged |
| GAP-4 | `choose_robot` still callable and still FAIL | High if a caller uses it | Named baseline; xfails kept |
| GAP-5 | CSV tasks often lack `payload_kg` | Medium | G8; allocator may still rank G8-only missing payload |
| GAP-6 | Naive timestamps; 18 warehouse timezones | Medium | event_time sort on fixtures; estate TZ **NOT PROVEN** |
| GAP-7 | Cross-DC assign 94.4% meaning UNKNOWN | Medium | SITE_MISMATCH conflict; injects can force no-cross-DC |
| GAP-8 | Inventory physical reconcile OPEN | High for pick truth | UNCERTAIN retained; no wipe |
| GAP-9 | UC-2 copilot ABSENT | Low for brief | Optional; default off; must not import executor |
| GAP-10 | Injects are in-memory overlays | High vs real plant | Do not rewrite CSVs |
| GAP-11 | No OT, no PLC, no WMS write | Absolute for this repo | `/health` disabled |
| GAP-12 | No ISO 42001 / independent safety case | Absolute for customer | Not claimed |

---

## 5. Residual harms (from Prompt 07, still true)

A future operator who **ignores** UC-1 and calls `choose_robot` can still assign expired-cert or open-CMMS robots. Repo 2 does not physically prevent that; it provides a **different function** and keeps the old one labeled FAIL.

A future copilot that is wired to the stub executor would be a **kill** (ADR-002). Tests forbid the import.

---

## 6. What is in-authority for the stakeholder demo

Show: diagnostics conflicts, identity collision `BOT-COLLISION-*`, eligibility of `RBT-0001` / `RBT-0020`, inventory `SKU-01146`, cutoff `ORD-000004`, inject_02/03 replay, eval scorecard, simultaneous-pressure trace.

Do not show: live robot motion, a single “true qty”, a closed `ORD-000968`, a zone release, or an enabled `physical_control` flag.
