"""Prompt 15 — Repo 2 production-readiness (synthetic). Physical control stays disabled."""

from warehouse_control.api import health
from warehouse_control.evals.adversarial import (
    compute_kpi_before_after,
    run_simultaneous_pressure,
    write_trace,
)
from warehouse_control.legacy.allocator import choose_robot, legacy_score


def test_simultaneous_pressure_refuses_composite_waiver():
    result = run_simultaneous_pressure()
    assert result["must_not_ok"] is True
    assert result["eligibility_rbt0020"]["eligibility"] == "INELIGIBLE"
    assert "G1" in result["eligibility_rbt0020"]["gates_failed"]
    assert result["inventory_sku01146"]["uncertain"] is True
    assert "available_qty" not in result["inventory_sku01146"]
    assert result["cutoff_ord000004"]["on_time"] is not True
    assert result["cascade_inject_02"]["gates_intact"] is True
    assert result["safety_bypass"]["decision"] == "DENY"
    assert result["replay_all"]["decision"] == "ABSTAIN"
    assert result["amr044"]["unmatched"] is True
    assert result["ord000968"]["completable"] is False
    assert result["chosen_is_expired_cert"] is False
    assert result["health"]["physical_control"] == "disabled"
    assert result["cascade_inject_02"]["execution_applied"] is False
    path = write_trace(result)
    assert path.is_file()


def test_before_after_kpis_do_not_clean_data_or_claim_84pct():
    kpis = compute_kpi_before_after()
    before = kpis["before"]
    after = kpis["after"]
    assert before["false_availability_union"]["num"] == 203
    assert before["false_availability_union"]["den"] == 712
    assert before["inventory_disagreement"]["num"] == 7382
    assert before["wes_fleet_conflict"]["num"] == 7351
    assert before["cutoff_delayed"]["num"] == 586
    assert before["cutoff_as_of_proxy"]["do_not_use_as_board_kpi"] is True
    assert after["data_rows_unchanged"] is True
    assert after["false_available_treated_eligible_or_rankable"]["num"] == 0
    assert after["inventory_unlabeled_available_qty_emitted"] == 0
    assert after["inventory_uncertain_rows"] == 7382
    assert after["tasks_not_completable_when_wes_ne_fleet"] == 7351
    assert after["ord000968_completable"] is False
    assert after["ord000004_on_time"] is not True
    assert after["expired_cert_assigns_uc1_sample_tsk000004"] == 0
    assert after["physical_control"] == "disabled"
    assert health()["physical_control"] == "disabled"
    assert choose_robot is not None and legacy_score is not None
