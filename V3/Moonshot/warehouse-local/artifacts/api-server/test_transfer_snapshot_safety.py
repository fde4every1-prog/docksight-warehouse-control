import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import transfer_api
import transfer_snapshot


def _scenario(snapshot, scenario_id="SAFETY"):
    return {
        "scenario_id": scenario_id,
        "snapshot": snapshot,
        "revision": 1,
        "raw_rows": [],
        "rows": [],
        "row_blockers": [],
        "selected_robot_ids": list(snapshot.get("selected_robot_ids", [])),
        "recommendations": {},
    }


def test_get_returns_detached_scenario_and_revision_replace_is_cas():
    snapshot = transfer_snapshot.create_snapshot("synthetic_demo")
    scenario = _scenario(snapshot)
    transfer_api._put(scenario)

    detached = transfer_api._get(scenario["scenario_id"])
    detached["revision"] = 99
    assert transfer_api._get(scenario["scenario_id"])["revision"] == 1

    replacement = copy.deepcopy(scenario)
    replacement["revision"] = 2
    transfer_api._replace_if_revision(scenario["scenario_id"], 1, replacement)
    with pytest.raises(HTTPException) as stale:
        transfer_api._replace_if_revision(scenario["scenario_id"], 1, replacement)
    assert stale.value.status_code == 409


def test_all_scenario_reads_reject_expired_embedded_snapshot():
    snapshot = transfer_snapshot.create_snapshot("synthetic_demo")
    snapshot["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat().replace("+00:00", "Z")
    scenario = _scenario(snapshot, "EXPIRED")
    transfer_api._put(scenario)

    with pytest.raises(HTTPException) as expired:
        transfer_api._get(scenario["scenario_id"])
    assert expired.value.status_code == 409


def test_recommendation_store_rejects_changed_revision():
    snapshot = transfer_snapshot.create_snapshot("synthetic_demo")
    scenario = _scenario(snapshot, "SUGGEST-RACE")
    transfer_api._put(scenario)
    changed = copy.deepcopy(scenario)
    changed["revision"] = 2
    transfer_api._replace_if_revision(scenario["scenario_id"], 1, changed)

    with pytest.raises(HTTPException) as stale:
        transfer_api._store_recommendation_if_revision(
            scenario["scenario_id"], 1, "key", {"recommendation_id": "REC"}
        )
    assert stale.value.status_code == 409


def test_read_connection_begins_transaction(tmp_path, monkeypatch):
    path = tmp_path / "read-only.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE evidence(value TEXT)")
    monkeypatch.setattr(transfer_snapshot, "DB_PATH", path)

    with transfer_snapshot._ro_db() as db:
        assert db.in_transaction
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO evidence VALUES ('mutation')")


def test_overlay_absence_is_supported_but_query_failure_is_explicit(tmp_path):
    path = tmp_path / "overlays.sqlite"
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        assert transfer_snapshot._overlays(db, "robots") == {}
        db.execute(
            "CREATE TABLE scenario_overrides("
            "dataset TEXT, row_index INTEGER, values_json TEXT)"
        )
        db.execute(
            "INSERT INTO scenario_overrides VALUES (?,?,?)",
            ("robots", 0, json.dumps({"robot_type": "AMR"})),
        )
        assert transfer_snapshot._overlays(db, "robots")[0]["robot_type"] == "AMR"
        db.execute(
            "INSERT INTO scenario_overrides VALUES (?,?,?)",
            ("robots", 1, "{broken"),
        )
        with pytest.raises(transfer_snapshot.SnapshotError):
            transfer_snapshot._overlays(db, "robots")


def test_malformed_and_stale_lifecycle_evidence_blocks_robot():
    clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale = (clock - timedelta(seconds=61)).isoformat().replace("+00:00", "Z")
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE resource_lifecycle("
        "resource_id TEXT, resource_kind TEXT, resource_type TEXT, warehouse_id TEXT,"
        "fitness_status TEXT, fitness_reasons TEXT, charging TEXT, battery_pct REAL,"
        "battery_at TEXT, current_task_id TEXT, current_stage TEXT, updated_at TEXT,"
        "revision INTEGER)"
    )
    db.execute(
        "INSERT INTO resource_lifecycle VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("R1", "robot", "AMR", "DC-01", "Y", "[]", "N", 80, stale,
         None, None, "not-a-timestamp", 1),
    )
    map_data = {"zones": [{"id": "Z1"}]}
    robots = transfer_snapshot._robots(
        db,
        [{"robot_id": "R1", "warehouse_id": "DC-01", "robot_type": "AMR", "payload_kg": "10"}],
        map_data,
        clock,
    )

    assert not robots[0]["eligible"]
    assert robots[0]["lifecycle_updated_at"] == "not-a-timestamp"
    assert robots[0]["lifecycle_evidence_age_seconds"] is None
    assert robots[0]["battery_evidence_age_seconds"] == 61
    assert "Malformed lifecycle updated_at evidence" in robots[0]["exclusion_reasons"]
    assert "Battery evidence is older than 60 seconds" in robots[0]["exclusion_reasons"]