"""OM 21 spine files exist; OT still disabled. Does not require agents or live deploy."""

from pathlib import Path

from warehouse_control.api import health

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "discovery/FDE_OM21_SPINE.md",
    "specs/01_context_map.md",
    "specs/09_information_architecture.md",
    "specs/11_agent_suitability.md",
    "docs/COMPONENT_REGISTER.md",
    "specs/13_delivery_specification.md",
    "specs/14_as_built_c4.md",
    ".github/workflows/pytest.yml",
    "discovery/16_OPERATIONS_RUNBOOK.md",
    "discovery/17_21_LIFECYCLE_DEFERRED.md",
]


def test_om21_spine_artifacts_present():
    missing = [rel for rel in REQUIRED if not (ROOT / rel).is_file()]
    assert missing == [], missing


def test_agent_suitability_is_nogo():
    text = (ROOT / "specs/11_agent_suitability.md").read_text(encoding="utf-8")
    assert "NO-GO" in text
    assert "Option C" in text


def test_lifecycle_17_21_not_faked_as_live():
    text = (ROOT / "discovery/17_21_LIFECYCLE_DEFERRED.md").read_text(encoding="utf-8")
    assert "DEFER" in text
    assert "Do not create fake deployment records" in text


def test_health_still_disabled_after_spine_pass():
    assert health()["physical_control"] == "disabled"
