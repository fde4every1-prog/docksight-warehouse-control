# Versioning policy (show this to the PM)

## Two version lines, not a rewrite

| Line | Version | Rule |
|------|---------|------|
| Inherited baseline (the estate) | **2.0.0** | Frozen. Do not bump `pyproject.toml`, FastAPI `app.version`, or `data/manifest.json`. |
| Participant overlay (our work) | **0.1.0** | Increments only when an overlay transformation lands. Lives beside legacy, never instead of it. |

Inherited package metadata also still says `warehouse_control.__version__ = "0.1.0"` while the API says `2.0.0`. That skew is **baseline evidence** (L1 software inconsistency). We do not “fix” it by rewriting the base release.

## How we leverage v2.0.0

We keep and measure the inherited system:

- data + diagnostics as the **before** counts
- legacy allocator and WMS-only inventory as the **control** path
- XFAIL tests as documented defects
- golden eval questions, injects, shadow emails, read-only API (`physical_control: disabled`)

We do **not** clean contradictory CSVs. We do **not** replace `legacy/` until a new path has evals.

## How many transformations

**12 total.** **8 in the 10-day capstone.** **4 deferred.**

Committed (T01–T08): identity, inventory reconciliation, observability, suitability/assignment, exception/cutoff workflow, eval harness, two injects, KPI + authority.

Deferred (T09–T12): global prioritization, congestion/cutoff forecasting, optional RAG, autonomy beyond recommend.

Machine-readable register: `participant/transformation_register.json`

```bash
.\.venv\Scripts\python.exe scripts/overlay_status.py
```
