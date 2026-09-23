# P01-v1 — Warehouse Brownfield Forensics

**Prompt:** 01 — Warehouse Brownfield Forensics  
**Overlay / artifact version:** v1  
**Baseline product version (frozen):** 2.0.0  
**Date:** 2026-09-16  
**Implementation changed:** No

Prompt 01 required three deliverables. They are in this folder:

| File | Purpose |
|------|---------|
| [P01-v1-CURRENT_STATE.md](P01-v1-CURRENT_STATE.md) | What is actually in this repo (systems, data, code, evidence) |
| [P01-v1-CURRENT_ARCHITECTURE.md](P01-v1-CURRENT_ARCHITECTURE.md) | Diagrams expanded from `docs/03` — documented flow, repo control plane, competing records |
| [P01-v1-CURRENT_ARCHITECTURE-SIMPLE.pptx](P01-v1-CURRENT_ARCHITECTURE-SIMPLE.pptx) | Simple 3-slide PowerPoint (use this for trainer walkthrough) |
| [P01-v1-CURRENT_ARCHITECTURE.pptx](P01-v1-CURRENT_ARCHITECTURE.pptx) | Longer 10-slide PowerPoint |
| [P01-v1-SDD_GAP_ANALYSIS.md](P01-v1-SDD_GAP_ANALYSIS.md) | WRCC SDD / 15 golden scenarios vs this estate (PASS / PARTIAL / FAIL / NOT PROVEN) |
| [P01-v1-MODERNIZATION_BACKLOG.md](P01-v1-MODERNIZATION_BACKLOG.md) | Prioritized work after forensics |

**Not found in this repository (not invented):** `specs/`, WRCC SDD contract, `TRACEABILITY_MATRIX.md`, `DEFINITION_OF_READY.md`, `DEFINITION_OF_DONE.md`, Copilot/RAG runtime, DecisionEngine, ActionExecutor, keep-out polygons, tote barcode model, digital-twin service.

Ratings mean: **PASS** = present and behaves as needed; **PARTIAL** = evidence or data exists but no enforcing control; **FAIL** = required capability missing or opposite behavior; **NOT PROVEN** = cannot be shown from files in this tree.
