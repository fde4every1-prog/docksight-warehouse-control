"""Canonical decision-trace shape for deterministic UC-1 (Prompt 14)."""

DISABLED = {"applied": False, "physical_control": "disabled"}


def decision_trace(
    *,
    case_id: str,
    golden_scenario: str,
    evidence: list,
    interpretation: str,
    recommendation: str,
    decision: str,
    approval_required: bool,
    outcome: str,
    must_not: str,
    must_not_ok: bool,
    grades: dict,
    extra: dict | None = None,
) -> dict:
    body = {
        "case_id": case_id,
        "golden_scenario": golden_scenario,
        "loop": [
            {"step": "Evidence", "value": evidence},
            {"step": "Interpretation", "value": interpretation},
            {"step": "Recommendation", "value": recommendation},
            {"step": "Decision", "value": decision},
            {"step": "Approval required?", "value": approval_required},
            {"step": "Execution", "value": dict(DISABLED)},
            {"step": "Outcome", "value": outcome},
        ],
        "must_not": must_not,
        "must_not_ok": must_not_ok,
        "grades": grades,
        "execution": dict(DISABLED),
    }
    if extra:
        body["extra"] = extra
    return body
