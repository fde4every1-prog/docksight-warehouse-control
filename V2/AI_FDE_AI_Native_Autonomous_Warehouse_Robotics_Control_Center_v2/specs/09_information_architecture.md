# 09 — Information architecture (OM 9)

**FDE OM:** 9 — Design information architecture  
**Date:** 2026-09-18  
**Binding:** `specs/02_data_contracts.md`, ADR-001 (no mandatory KG/twin), Prompt 06 quality/lineage.

PDF lists ontology, knowledge graphs, graph/vector DBs as **conditional**. For this virtual tower they are **not required**.

---

## Target data architecture (as-is extracts stay)

```text
data/raw/*.csv  +  data/telemetry  +  data/shadow  +  SQLite warehouse_legacy.db
        |
        v
repository.csv_rows / query     (read only)
        |
        +--> Identity / Eligibility / InventoryObservation / TaskReconcile / Cutoff
        |
        v
Conflict + Uncertainty  (first-class; no silent merge)
```

No new system of record. No write-back to WMS/OMS/Fleet.

---

## Data contracts

Canonical keys and retain/drop: `specs/02_data_contracts.md`.

Adapters: fleet YAML `robotId` / `vehicle_id` are **evidence of drift**, not stored names.

---

## Semantic model

The semantic model **is** the domain ubiquitous language (`specs/01_domain_model.md`), not an ontology store. The **overall claim graph** (types, not rows) is `specs/09_knowledge_graph.md`.

| Concept | Semantic rule |
|---|---|
| Quantity | Three fields, not one |
| Available | Not a field; derive Eligibility |
| Complete | Both WES and fleet COMPLETE |
| On-time | Not OMS SLA alone when TMS DELAYED |

---

## Metadata / provenance

`discovery/06_LINEAGE_AND_PROVENANCE.md`. Command ids **ABSENT**. `event_time` vs `recorded_time`.

Retrieval architecture: **file + SQL read**. No vector index. No RAG corpus.

---

## Conditional artifacts — decision

| PDF item | Decision | Why |
|---|---|---|
| Ontology / OWL | **Do not build** | Language already in domain spec; OWL would not reconcile 205/205/202 |
| Runtime knowledge graph / Neo4j | **Do not build** | Joins are CSV keys; DecisionEngine must not query a graph for truth |
| Explanatory domain KG | **ADDED** `specs/09_knowledge_graph.md` + `.json` + `.mmd` | Teaching map of claims, frozen IDs, gates. Not on the write path |
| Vector DB / RAG | **Do not build** | No embedding use case on the write path; UC-2 off |
| Graph/vector schemas for retrieval | **N/A** | Follows runtime “do not build” |

**Data ADR:** this file + ADR-001 Option D not required. Explanatory KG does not change ADR-001/002.

---

## Access

Local process. `.env.example` has no secrets. Shadow files untrusted (`specs/07_threat_model.md`).
