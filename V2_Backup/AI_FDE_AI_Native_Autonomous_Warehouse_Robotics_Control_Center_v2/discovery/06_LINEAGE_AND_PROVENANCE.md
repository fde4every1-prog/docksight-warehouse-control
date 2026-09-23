# 06 — Lineage and provenance

**Prompt 06.** Where each byte came from, what it may be used for, and how copies drift.

---

## 1. Generation lineage

```text
[Synthetic generator — not in repo as a full writer]
        seed 20260910, generated_at 2026-09-10
        |
        v
[CSV / JSONL / TXT under data/]
        |                    |
        | copy (8 tables)    | not copied
        v                    v
warehouse_legacy.db      aliases, telemetry, vision,
                         events, zones, charging,
                         labor, reference, shadow
        |
        v
repository.query / GET /robots/{id}
```

`scripts/generate_data.py` **checks** manifest paths; it does not recreate files. Provenance for analytics is **this snapshot**, not a live WMS.

Hashes: `data/manifest.json` per-file SHA-256 + `checksums.sha256`. VERIFICATION.md: not digitally signed, not a certification.

---

## 2. CSV vs SQLite

| Table in DB | CSV source | Counts match? | Value match sampled? |
|---|---|---|---|
| robots | `data/raw/robots.csv` | 712 = 712 | **0** field mismatches all rows |
| inventory | `inventory_snapshot.csv` | 9360 = 9360 | Conflict row SKU-01146 **205/205/202 in both** |
| orders | orders.csv | 3500 | count match |
| tasks | tasks.csv | 8732 | count match |
| shipments | shipments.csv | 3500 | count match |
| maintenance | maintenance.csv | 520 | count match |
| safety_events | safety_events.csv | 1170 | count match |
| control_assets | control_assets.csv | 918 | count match |

**Not in SQLite (CSV-only):** robot_aliases, robot_telemetry, vision_observations, events.jsonl, zones, charging_state, labor_capacity, skus, vendors, warehouses, shadow/*.

**Provenance rule:** SQLite is a **convenience extract**, not a higher-authority SoR. If CSV and DB ever diverge, **CSV + manifest hash win** for this repo. They do not diverge on robots today.

`/robots/{id}` therefore cannot disclose I9 collisions or I5 WOs unless UC-1 reads CSV (or DB is extended later **without** dropping conflict columns).

---

## 3. Contract / schema drift (not live APIs)

These files are **stubs**. No client in `src/` calls them.

| Contract | Identity / fields | Drift vs Repo 1 CSV |
|---|---|---|
| `contracts/fleet_api_v1.yaml` | path `/robots/{robotId}/task`; **no idempotency key** | CSV uses `robot_id` not `robotId`; tasks assigned without command id |
| `contracts/fleet_api_v2.yaml` | POST `/missions`; **`vehicle_id`** instead of robotId | No `vehicle_id` column in robots.csv |
| `contracts/order_event_schema.json` v1 | `orderId`, `status` | events.jsonl uses `entity_id`, `event_type`; orders.csv uses `order_id`, oms_status/wms_status |
| v2 | `order_id`, `state`, `occurred_at` | Closest to `event_time` but events still have `recorded_time` too |

**Lineage implication:** v1 vs v2 is **L9 integration drift**. UC-1 canonical names are domain spec (`robot_id`, `order_id`, `event_time`). Do not rename CSV to match OpenAPI. Map at the boundary if a later adapter exists.

Idempotency: v1 explicitly lacks it. EVAL-005 / I11 (no blind replay) must not assume command ids exist in this snapshot — they **ABSENT**. Replay protection is a to-build concern when writes exist; writes are disabled.

---

## 4. Clock lineage

| Clock | Field | Provenance |
|---|---|---|
| Business / source | `event_time` on events and telemetry | Claimed occurrence |
| Ingest / recorded | `recorded_time`, `ingest_time` | Arrival at some digital log |
| Order/task create | `created_at` | Row timestamp |
| Cutoff / plan | `carrier_cutoff`, `planned_departure` | OMS/TMS extract — may be stale vs email |
| Warehouse TZ | `warehouses.timezone` | Not applied to naive timestamps |

I8: lineage of **sequence** is `event_time`. `recorded_time` is lineage of **ingest**, not of business order.

---

## 5. Permissible use / access

| Data | Permissible | Not permissible |
|---|---|---|
| All `data/` | Local training analysis, UC-1 features, evals | Treat as real PII/OT; publish as production warehouse truth |
| Shadow | Cite as unofficial | Merge into WMS qty/status |
| Vision qty / CAM-18 | Observation with confidence | Sole identity or sole qty (EVAL-006) |
| SQLite | Read replica of 8 tables | Pretend it is complete warehouse state |

No production credentials in `.env.example`. Vendor `remote_access` values (vendor_cloud, jump_host) are **labels in a CSV**, not configured tunnels.

---

## 6. Representativeness

Synthetic: 18 DCs, fake Country-N, Synthetic Product SKUs. Quality profile is internally consistent as a **case study**, not statistically representative of a real 18-site network. KPI before/after is vs **this** snapshot only.
