import json
from pathlib import Path

import pytest
from fastapi import HTTPException

import predictive_api as api


@pytest.fixture()
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "MODEL_DIR", tmp_path)
    api._read_bundle.cache_clear()
    summary = {
        "model_id": "test-model", "data_end": "2026-01-01",
        "model_comparison": [{"model": "baseline", "test_average_precision": 0.02}],
    }
    rows = [
        {"robot_id": "RBT-1", "warehouse_id": "DC-01", "robot_type": "AMR", "vendor": "one",
         "risk_probability": 0.1, "priority": "review", "signals": [], "history": []},
        {"robot_id": "RBT-2", "warehouse_id": "DC-02", "robot_type": "AGV", "vendor": "two",
         "risk_probability": None, "priority": "unavailable", "signals": [], "history": []},
    ]
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    (tmp_path / "predictions.json").write_text(json.dumps(rows))
    return tmp_path


def test_model_is_snapshot_and_explicitly_stale(bundle):
    result = api.model("fleet")
    assert result["available"] is True
    assert result["freshness"]["snapshot_only"] is True
    assert result["freshness"]["stale"] is True
    assert result["counts"] == {"total": 2, "review": 1, "monitor": 0, "unavailable": 1}
    assert result["evaluation"][0]["model"] == "baseline"


def test_filter_pagination_and_robot_detail(bundle):
    response = api.predictions("DC-02", "", "", 20, 0, "supervisor")
    assert response["total"] == 1
    assert response["items"][0]["robot_id"] == "RBT-2"
    assert "history" not in response["items"][0]
    assert "history" in api.robot("RBT-2", "admin")
    assert api.predictions("", "amr", "review", 20, 0, "fleet")["total"] == 1
    assert api.predictions("", "", "", 20, 2, "fleet")["items"] == []


def test_unknown_role_and_robot_fail(bundle):
    with pytest.raises(HTTPException) as exc:
        api.model("visitor")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        api.robot("unknown", "fleet")
    assert exc.value.status_code == 404


def test_missing_model_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "MODEL_DIR", tmp_path)
    assert api.model("fleet")["available"] is False
    with pytest.raises(HTTPException) as exc:
        api.robot("RBT-1", "fleet")
    assert exc.value.status_code == 503


def test_corrupt_and_partial_model_fail_closed(bundle):
    (bundle / "predictions.json").write_text("not json")
    with pytest.raises(HTTPException) as exc:
        api.model("fleet")
    assert exc.value.status_code == 503
    (bundle / "predictions.json").unlink()
    with pytest.raises(HTTPException) as exc:
        api.model("fleet")
    assert exc.value.status_code == 503


def test_reads_never_modify_artifacts(bundle):
    before = {p.name: p.read_bytes() for p in bundle.iterdir()}
    api.model("fleet")
    api.predictions("", "", "", 20, 0, "fleet")
    api.robot("RBT-1", "fleet")
    assert before == {p.name: p.read_bytes() for p in bundle.iterdir()}