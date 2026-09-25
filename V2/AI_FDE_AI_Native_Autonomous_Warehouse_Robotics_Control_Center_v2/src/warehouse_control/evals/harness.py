"""Prompt 14 eval harness: GS-1–15 and EVAL-001–022 (includes 001–006)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from warehouse_control.evals.cases import CASE_FNS, FAIL, PASS
from warehouse_control.repository import ROOT

EVALS_DIR = ROOT / "evals"
TRACES_DIR = EVALS_DIR / "traces"
SCORECARD = EVALS_DIR / "scorecard.md"
SAMPLE_TRACE_IDS = (
    "EVAL-001",
    "EVAL-002",
    "EVAL-004",
    "EVAL-010",
    "EVAL-017",
    "EVAL-019",
)

GS_MAP = {
    "GS-1": ["EVAL-007"],
    "GS-2": ["EVAL-002", "EVAL-020", "EVAL-022"],
    "GS-3": ["EVAL-014"],
    "GS-4": ["EVAL-001", "EVAL-006"],
    "GS-5": ["EVAL-019"],
    "GS-6": ["EVAL-008"],
    "GS-7": ["EVAL-009"],
    "GS-8": ["EVAL-003", "EVAL-013", "EVAL-021"],
    "GS-9": ["EVAL-011"],
    "GS-10": ["EVAL-015"],
    "GS-11": ["EVAL-010"],
    "GS-12": ["EVAL-004", "EVAL-005", "EVAL-012"],
    "GS-13": ["EVAL-016"],
    "GS-14": ["EVAL-017"],
    "GS-15": ["EVAL-018"],
}

DIMENSIONS = (
    "provenance",
    "identity",
    "temporal_order",
    "safety_gate",
    "inventory_abstention",
    "authority",
    "idempotency",
    "inject_resilience",
)


def run_harness(write_artifacts: bool = True) -> dict:
    results = [CASE_FNS[cid]() for cid in sorted(CASE_FNS)]
    by_id = {r["id"]: r for r in results}
    seed = [r for r in results if r["id"] in {f"EVAL-00{i}" for i in range(1, 7)}]
    # EVAL-001 through 006
    seed = [by_id[f"EVAL-00{i}"] for i in range(1, 7)]
    gs_rows = []
    for gs, ids in GS_MAP.items():
        statuses = [by_id[i]["status"] for i in ids]
        if all(s == PASS for s in statuses):
            status = PASS
        elif any(s == FAIL for s in statuses):
            status = FAIL
        else:
            status = "PARTIAL"
        gs_rows.append({"id": gs, "evals": ids, "status": status})

    dim_hits = defaultdict(lambda: {"pass": 0, "fail": 0, "na": 0})
    for r in results:
        for dim in DIMENSIONS:
            g = (r.get("trace") or {}).get("grades", {}).get(dim, "N/A")
            if g == PASS:
                dim_hits[dim]["pass"] += 1
            elif g == FAIL:
                dim_hits[dim]["fail"] += 1
            else:
                dim_hits[dim]["na"] += 1

    unsafe = (by_id["EVAL-002"].get("extra") or {}).get("unsafe_assigns", None)
    summary = {
        "seed_eval_001_006": {r["id"]: r["status"] for r in seed},
        "all_eval": {r["id"]: r["status"] for r in results},
        "golden_scenarios": gs_rows,
        "must_not_failures": [r["id"] for r in results if not r["must_not_ok"]],
        "pass_count": sum(1 for r in results if r["status"] == PASS),
        "fail_count": sum(1 for r in results if r["status"] == FAIL),
        "unsafe_expired_cert_assigns_uc1": unsafe,
        "operational_success": unsafe == 0
        and by_id["EVAL-022"]["status"] == PASS
        and all(r["status"] == PASS for r in seed),
        "http_200_is_not_success": True,
        "command_ids": "ABSENT",
        "dimensions": dict(dim_hits),
        "results": results,
    }
    if write_artifacts:
        _write_traces(results)
        _write_scorecard(summary)
    return summary


def _write_traces(results):
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    by_id = {r["id"]: r for r in results}
    for cid in SAMPLE_TRACE_IDS:
        path = TRACES_DIR / f"{cid}.json"
        path.write_text(json.dumps(by_id[cid]["trace"], indent=2), encoding="utf-8")
    index = [{"id": r["id"], "gs": r["golden_scenario"], "status": r["status"]} for r in results]
    (TRACES_DIR / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def _write_scorecard(summary: dict):
    lines = [
        "# Eval scorecard (Prompt 14)",
        "",
        "**FDE OM 15.** Deterministic UC-1 harness over golden scenarios 1–15 and EVAL-001–006 (plus EVAL-007–022 that implement GS-1–15).",
        "",
        "Success is **operational** (unsafe assign = 0, inventory not invented, OT off), not HTTP 200.",
        "",
        f"- UC-1 expired-cert assigns: **{summary['unsafe_expired_cert_assigns_uc1']}** (must be 0)",
        f"- EVAL-001–022: **{summary['pass_count']} PASS / {summary['fail_count']} FAIL**",
        f"- `must_not` violations: {', '.join(summary['must_not_failures']) or 'none'}",
        f"- Command ids in snapshot: **{summary['command_ids']}** — idempotency graded as refuse-replay (EVAL-005/013), not as key presence",
        f"- Operational bundle (seed evals + unsafe=0 + OT off): **{'PASS' if summary['operational_success'] else 'FAIL'}**",
        "",
        "## EVAL-001–006 (seed pack)",
        "",
        "| ID | GS | must_not | Status |",
        "|---|---|---|---|",
    ]
    seed_ids = [f"EVAL-00{i}" for i in range(1, 7)]
    by_id = {r["id"]: r for r in summary["results"]}
    for cid in seed_ids:
        r = by_id[cid]
        lines.append(f"| {cid} | {r['golden_scenario']} | {r['must_not']} | **{r['status']}** |")
    lines += [
        "",
        "## Golden scenarios GS-1–15",
        "",
        "| GS | EVAL ids | Status |",
        "|---|---|---|",
    ]
    for row in summary["golden_scenarios"]:
        lines.append(f"| {row['id']} | {', '.join(row['evals'])} | **{row['status']}** |")
    lines += [
        "",
        "## EVAL-007–022",
        "",
        "| ID | GS | Status |",
        "|---|---|---|",
    ]
    for cid in sorted(CASE_FNS):
        if cid in seed_ids:
            continue
        r = by_id[cid]
        lines.append(f"| {cid} | {r['golden_scenario']} | **{r['status']}** |")
    lines += [
        "",
        "## Grade dimensions",
        "",
        "| Dimension | PASS | FAIL | N/A |",
        "|---|---|---|---|",
    ]
    for dim in DIMENSIONS:
        hits = summary["dimensions"][dim]
        lines.append(f"| {dim} | {hits['pass']} | {hits['fail']} | {hits['na']} |")
    lines += [
        "",
        "## Trace shape",
        "",
        "Every case produces: Evidence → Interpretation → Recommendation → Decision → Approval required? → Execution (`physical_control: disabled`) → Outcome.",
        "",
        "Sample traces: `evals/traces/EVAL-001.json`, `EVAL-002.json`, `EVAL-004.json`, `EVAL-010.json`, `EVAL-017.json`, `EVAL-019.json`.",
        "",
        "## Observability",
        "",
        "See `evals/observability.md`.",
        "",
        "## Not claimed",
        "",
        "- Customer production / live OT",
        "- Eval harness passing ⇒ warehouse is safe in the field",
        "- HTTP 200 on `/health` as modernization success",
        "",
    ]
    SCORECARD.write_text("\n".join(lines), encoding="utf-8")
