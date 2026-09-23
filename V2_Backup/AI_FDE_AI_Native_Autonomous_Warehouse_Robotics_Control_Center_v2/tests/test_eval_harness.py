"""Prompt 14 — eval harness over GS-1–15 and EVAL-001–006."""

from warehouse_control.evals.harness import run_harness


def test_eval_harness_seed_and_golden_pass():
    summary = run_harness(write_artifacts=True)
    for i in range(1, 7):
        assert summary["seed_eval_001_006"][f"EVAL-00{i}"] == "PASS"
    assert summary["fail_count"] == 0
    assert summary["pass_count"] == 22
    assert summary["unsafe_expired_cert_assigns_uc1"] == 0
    assert summary["operational_success"] is True
    gs = {row["id"]: row["status"] for row in summary["golden_scenarios"]}
    for n in range(1, 16):
        assert gs[f"GS-{n}"] == "PASS"
    from pathlib import Path
    from warehouse_control.repository import ROOT

    assert (ROOT / "evals" / "scorecard.md").is_file()
    assert (ROOT / "evals" / "traces" / "EVAL-001.json").is_file()
    assert (ROOT / "evals" / "observability.md").is_file()
