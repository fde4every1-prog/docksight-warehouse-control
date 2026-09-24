# 05 — Failure modes (Repo 2 control plane)

**Prompt:** 09  
**Date:** 2026-09-17  
**Mode:** Spec only. No simulator implementation in this prompt.

Library-required modes: **stale OMS cutoff**, **vision collapse**, **charger fail**, **unknown ack**.  
Related injects (AS/RS, dock, cascade) are listed so Prompt 13 can replay two of them without inventing new floor stories.

DecisionEngine **ABSTAIN** / Eligibility **INELIGIBLE** / Inventory **UNCERTAIN** are the legal control-plane answers. Inventing truth or dispatching through failure is not.

---

## How to read a mode

| Field | Meaning |
|---|---|
| Trigger | What is wrong |
| Evidence in this repo | File + id — do not invent a new DC |
| Symptom if we did nothing (Repo 1) | Legacy path |
| Option A required | Identity / eligibility / inventory / reconcile / decide |
| `must_not` | Eval hard gate |
| Recovery | Observe/reason only; OT still disabled |

---

## FM-1 Stale OMS cutoff

**Trigger:** OMS SLA / on-time table is treated as live while Carrier-A has already moved or TMS is DELAYED.

**Evidence:**

| Item | Where |
|---|---|
| Same-day critical, DELAYED | `ORD-000004` |
| Shadow: Carrier-A −35 min; OMS SLA stale until midnight | `data/shadow/ops_emails.txt` |
| Cascade inject | `scenarios/cascade_001.json` “Carrier-A advances cutoff by 35 minutes”; 214 priority orders at risk |
| Standing DELAYED population | 03: 586 / 3500 shipments (16.7%) |
| Invariant | I7 |

**Repo 1 symptom:** no cutoff-aware allocator; `legacy_score` still picks battery+ONLINE; 02 recovery map: OMS looks fine while Carrier-A already moved.

**Option A required:**

- CutoffAwareness reads `orders.carrier_cutoff` **and** shipment DELAYED / planned_departure.
- Shadow email may create Conflict `CUTOFF_STALE`; it is **not** Policy and not an auto re-wave.
- Decision may ALLOW a **recommendation** to miss cutoff (legal). Decision must DENY safety bypass to hit cutoff (I6).
- If OMS and TMS/shadow disagree and structured DELAYED is present → do not report on-time from OMS alone.
- If the only extra signal is unstructured email and TMS is not DELAYED → Conflict + Uncertainty; **ABSTAIN** on “will we make cutoff?” — do not invent a new SLA clock.

**`must_not`:** treat OMS SLA as live; release RESTRICTED zone or expired-cert robot to save cutoff (EVAL-010, EVAL-004, EVAL-012).

**Recovery:** surface DELAYED + Conflict on `GET /orders/ORD-000004/cutoff`. No WMS write. No AMR redirect storm (cascade “38 AMRs toward C/D”).

**Eval / GS:** GS-11, EVAL-010; cascade GS-12, EVAL-012.

---

## FM-2 Vision collapse

**Trigger:** vision qty or camera class becomes unusable (low confidence, inject, or untrusted camera).

**Evidence:**

| Item | Where |
|---|---|
| Triple disagree | `SKU-01146` DC-01 loc `DC-01-Z03-B017` wms 205 / erp 205 / vision 202 |
| Untrusted camera | `DC-01-CAM-18`; shadow “do not trust camera 18”; confidence 0.566 in 02 |
| Injects | `scenarios/inject_04.md`, `inject_05.md` (vision confidence collapse) |
| Population | 03: 7382 / 9360 inventory disagree (78.9%) |
| Invariant | I3, I9 |

**Repo 1 symptom:** `legacy_available_qty` = WMS − reserved; EVAL-001 fails if that is used as truth.

**Option A required:**

- InventoryUncertainty **retains** wms, erp, vision. `uncertain=true` when they disagree.
- Vision observation is physical evidence, not identity authority (camera `observed_entity` ≠ `robot_id`).
- On collapse/inject: mark vision untrusted; **do not** fill the hole with an LLM guess or by copying WMS into vision.
- Pick/allocate path: UNCERTAIN → do not treat as pickable truth; Decision **ABSTAIN** (or DENY allocate-as-known). Human/cycle count remains the physical path (not implemented OT).

**`must_not`:** invent physical qty; pick one source because it is named WMS/Vision; treat CAM-18 as registry identity (EVAL-001, EVAL-006, EVAL-015).

**Recovery:** return the triple; Conflict `INVENTORY_QTY`; optional note that vision is untrusted. Do not PATCH inventory CSV.

**Eval / GS:** GS-4, GS-10; EVAL-001, EVAL-006, EVAL-015.

---

## FM-3 Charger fail

**Trigger:** preferred charger (or charging subsystem) is DOWN; low-SOC robots cannot recover; cascade queue grows.

**Evidence:**

| Item | Where |
|---|---|
| Inject | `scenarios/inject_02.md` charging subsystem failure |
| Assets | `DC-16-CHARGER-08` DOWN; `DC-02-CHARGER-07` DOWN (02 recovery map) |
| Cascade | `cascade_001.json` “charger 3 fails”; remaining charger queue grows; `AMR-044` low battery (**unmatched** name) |
| Robot example | `RBT-0644` low SOC cited in 02 (do not assume it is AMR-044) |
| ControlAsset | `data/raw/control_assets.csv` CHARGER DOWN |
| ChargingState | `data/raw/charging_state.csv` `preferred_charger` |
| Invariant | I12 adjacent; ControlAsset DOWN; I9 for AMR-044 |

**Repo 1 symptom:** allocator ignores charger state; may still “choose” an ONLINE robot that cannot charge; no inject replay in code.

**Option A required:**

- If `preferred_charger` asset is DOWN → Uncertainty on charging recovery; do **not** assume the robot will be eligible later by magic SOC.
- Eligibility: OFFLINE still INELIGIBLE; low battery is a score penalty among ELIGIBLE, not a reason to skip cert/CMMS gates.
- Unmatched `AMR-044` in the cascade stays unmatched (IdentityResolver). Do not fail charger recovery onto `RBT-0044` without evidence.
- Decision: **ABSTAIN** or DENY assign that depends on the dead charger; do not locally optimal-reroute 38 AMRs into congestion (cascade expected_reasoning).
- FilterThenScore must not treat DOWN charger as AVAILABLE capacity.

**`must_not`:** assign into a recovery plan that requires the failed charger; merge AMR-044; override safety to keep waves moving (EVAL-017, EVAL-012, I6).

**Recovery:** expose ControlAsset DOWN on preview-allocate evidence list. OT charge-command remains disabled.

**Eval / GS:** GS-14, EVAL-017; cascade GS-12, EVAL-012.

---

## FM-4 Unknown ack (stale fleet queue / no command id)

**Trigger:** fleet manager recovers after outage (or we imagine a v1/v2 POST) and the control plane does not know whether a task was acknowledged. Snapshot has **no command ids**. Fleet v1 YAML: assign task, **no idempotency key**.

**Evidence:**

| Item | Where |
|---|---|
| EVAL-005 | “ABSTAIN where status conflicts (I4) or UNKNOWN ack”; `must_not` blindly replay all tasks |
| Task splits already | 7351 / 8732 WES ≠ fleet (I4) |
| Contracts | `contracts/fleet_api_v1.yaml` no idempotency; v2 `vehicle_id` / `/missions` unused |
| Lineage | command ids **ABSENT** (`discovery/06_LINEAGE_AND_PROVENANCE.md`) |
| Invariant | I11, I4, I10 |

**Repo 1 symptom:** no executor; if someone later POSTed v1 blindly, duplicate missions / wrong robot (`robotId` vs `robot_id`).

**Option A required:**

- TaskReconciler: per-task compare WES vs fleet. Conflict → `completable=false`.
- DecisionEngine: **ABSTAIN** on replay when ack is UNKNOWN or statuses conflict. Do not emit a batch “replay all fleet rows.”
- ActionExecutor STUB: never POST v1/v2; return `applied=false`.
- Do **not** invent command ids in preview JSON and then treat them as proof of ack.
- Identity: v1 `robotId` / v2 `vehicle_id` adapters if ever used at an edge must not overwrite `robot_id` (I9).

**`must_not`:** blindly replay all tasks; treat HTTP 200 from a future client as ack; enable physical_control because “we need to drain the queue” (EVAL-005, EVAL-013, EVAL-022).

**Recovery:** list conflicting tasks; human Supervisor may decide T3 later (Prompt 10). Repo 2 first increment only auto-refuses.

**Eval / GS:** EVAL-005, EVAL-013; GS-12 (outage + congestion); I11.

---

## Related modes (not extra floor fiction)

Prompt 13 must demonstrate **at least two** injects. These are already in `scenarios/`. Option A treats them the same way: ControlAsset DOWN → do not allocate as if the asset worked.

| ID | Inject | Required Option A behavior | Eval |
|---|---|---|---|
| FM-5 | AS/RS unavailable `inject_01.md` | STORAGE/PICK replenishment starved; do not assume PACK_FEED can complete; ABSTAIN close of `ORD-000968` pattern | GS-13, EVAL-016 |
| FM-6 | Dock closure `inject_03.md` / `inject_06.md` | DELAYED / no `actual_departure`; SAME_DAY CRITICAL cannot digitally “depart” | GS-15, EVAL-018 |
| FM-7 | Sorter / conveyor / Z09 map stale | Conflict `MAP_STALE`; unofficial staging is not a WMS write | GS-9, EVAL-011 |
| FM-8 | Identity collision during any of the above | Keep both robots; do not recover onto the wrong body | GS-1, EVAL-007 |

---

## Cross-cutting fail-safe

| If this is UNKNOWN | Decision |
|---|---|
| Physical qty | UNCERTAIN / ABSTAIN allocate-as-known |
| Occupancy / RESTRICTED | refuse path (I6) |
| Which robot an alias is | Conflict; do not assign by alias alone |
| Mission ack / command id | ABSTAIN replay |
| SafetyOfficer release | INELIGIBLE (email is not Approval) |
| LLM / copilot down | UC-1 still runs (ADR-002) |

Cutoff pressure, cascade “predicted on-time departure collapses,” and supervisor shadow text **never** flip EXPIRED cert or OPEN CMMS to ELIGIBLE.

---

## What Prompt 09 does *not* do

- No inject replay engine (Prompt 13)
- No eval harness (Prompt 14)
- No G1–G8 numbered gate spec (Prompt 10 uses these modes as examples)
