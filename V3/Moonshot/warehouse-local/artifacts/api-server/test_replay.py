import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

import replay_api
from replay_sources import deterministic_request_id, file_sha256, read_inputs


def test_request_uuid_is_deterministic():
    first = deterministic_request_id("abc", "ORD-1")
    assert first == deterministic_request_id("abc", "ORD-1")
    assert first != deterministic_request_id("abc", "ORD-2")
    assert str(uuid.UUID(first)) == first


def test_attached_archive_has_7000_exact_matches():
    archive = Path(__file__).resolve().parents[2] / "attached_assets" / "Synthetic_Data_1789961144297.zip"
    orders, shipments = read_inputs(archive)
    assert len(orders) == len(shipments) == 7000
    assert {row["order_id"] for row in orders} == set(shipments)
    assert file_sha256(archive) == "01984cf0c31be9c581906f6a9dadc54f155c3da32fb3fbd50d9c2fa33ae55259"


def _fixture(tmp_path: Path, *, wal: bool = False, started_at: str = "2026-01-01T00:00:00Z") -> str:
    run_id = str(uuid.uuid4())
    directory = tmp_path / run_id
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "status": "running", "total_orders": 1,
        "processed_orders": 1, "started_at": started_at,
    }))
    db = sqlite3.connect(directory / "simulation.sqlite")
    if wal:
        db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
      CREATE TABLE replay_orders(
        source_order_id TEXT,core_order_id TEXT,warehouse_id TEXT,sku TEXT,
        quantity INTEGER,priority TEXT,created_at TEXT,cutoff TEXT,status TEXT,
        finished_at TEXT,cycle_time_seconds REAL,benchmark_actual_departure TEXT,
        benchmark_planned_departure TEXT,benchmark_cycle_time_seconds REAL,
        reason TEXT,input_json TEXT,benchmark_json TEXT);
      CREATE TABLE orders(id TEXT,source_order_id TEXT,status TEXT,issues_json TEXT);
      CREATE TABLE tasks(
        id TEXT,order_id TEXT,status TEXT,due_at TEXT,completed_at TEXT);
      CREATE TABLE sub_orders(id TEXT,order_id TEXT);
      CREATE TABLE sub_order_allocations(id TEXT,sub_order_id TEXT);
      CREATE TABLE events(id INTEGER,order_id TEXT,at TEXT,message TEXT);
    """)
    db.execute(
        "INSERT INTO replay_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("ORD-1", None, "DC-01", "SKU-1", 1, "standard", "2026-01-01T00:00:00Z",
         "2026-01-01T06:00:00Z", "rejected", None, None, "2026-01-01T07:00:00Z",
         "2026-01-01T06:30:00Z", 25200, "shortage", "{}", "{}"),
    )
    db.commit()
    db.close()
    return run_id


def test_api_read_only_pagination_auth_and_path(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_api, "ROOT", tmp_path)
    run_id = _fixture(tmp_path)
    assert replay_api.collection("supervisor")["items"][0]["status"] == "running"
    page = replay_api.orders(run_id, limit=25, offset=0, x_demo_persona="admin")
    assert page["total"] == 1
    assert page["items"][0]["status"] == "rejected"
    with pytest.raises(HTTPException) as forbidden:
        replay_api.orders(run_id, x_demo_persona="fleet")
    assert forbidden.value.status_code == 403
    with pytest.raises(HTTPException) as invalid:
        replay_api.summary("../../live", "admin")
    assert invalid.value.status_code == 404


def test_collection_sorts_started_descending(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_api, "ROOT", tmp_path)
    older = _fixture(tmp_path, started_at="2026-01-01T00:00:00Z")
    newer = _fixture(tmp_path, started_at="2026-02-01T00:00:00Z")
    items = replay_api.collection("supervisor")["items"]
    assert [item["run_id"] for item in items] == [newer, older]


def test_api_wal_reader_sees_commits_and_not_uncommitted_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_api, "ROOT", tmp_path)
    run_id = _fixture(tmp_path, wal=True)
    path = tmp_path / run_id / "simulation.sqlite"
    writer = sqlite3.connect(path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            """INSERT INTO replay_orders VALUES(
               'ORD-2',NULL,'DC-02','SKU-2',1,'standard',
               '2026-01-01T01:00:00Z','2026-01-01T07:00:00Z','active',
               NULL,NULL,NULL,NULL,NULL,NULL,'{}','{}')"""
        )
        # Normal read-only WAL participation provides a consistent committed
        # snapshot without blocking on the active writer.
        during = replay_api.orders(run_id, limit=25, offset=0, x_demo_persona="admin")
        assert during["total"] == 1
        writer.commit()
        after = replay_api.orders(run_id, limit=25, offset=0, x_demo_persona="admin")
        assert after["total"] == 2
    finally:
        writer.close()


def test_preparing_database_without_results_table_is_503(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_api, "ROOT", tmp_path)
    run_id = str(uuid.uuid4())
    directory = tmp_path / run_id
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "status": "preparing", "started_at": "2026-01-01T00:00:00Z",
    }))
    sqlite3.connect(directory / "simulation.sqlite").close()
    with pytest.raises(HTTPException) as unavailable:
        replay_api.orders(run_id, x_demo_persona="supervisor")
    assert unavailable.value.status_code == 503


def test_running_api_derives_completed_engine_truth_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_api, "ROOT", tmp_path)
    run_id = _fixture(tmp_path, wal=True)
    path = tmp_path / run_id / "simulation.sqlite"
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["processed_orders"] = 0
    manifest_path.write_text(json.dumps(manifest))
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO replay_orders(source_order_id,status) VALUES('FUTURE','pending')"
    )
    db.execute(
        "UPDATE replay_orders SET status='active',reason=NULL,core_order_id='FUL-1' "
        "WHERE source_order_id='ORD-1'"
    )
    db.execute(
        "INSERT INTO orders VALUES('FUL-1','ORD-1','completed','[]')"
    )
    db.execute(
        """INSERT INTO tasks VALUES(
           'TS-1','FUL-1','completed','2026-01-01T00:01:00Z',
           '2026-01-01T00:01:00Z')"""
    )
    db.commit()
    before = path.stat().st_size
    progress = replay_api.summary(run_id, "supervisor")
    page = replay_api.orders(run_id, status="completed", x_demo_persona="admin")
    detail = replay_api.order_detail(run_id, "ORD-1", "supervisor")
    assert progress["processed_orders"] == 1
    assert progress["completed_orders"] == 1
    assert progress["accepted_orders"] == 1
    assert progress["completed_orders"] <= progress["accepted_orders"]
    assert progress["metrics"]["simulated_average_cycle_seconds"] == pytest.approx(60, abs=0.001)
    assert progress["metrics"]["simulated_on_time_percent"] == 100
    assert progress["metrics"]["benchmark_on_time_percent"] == 0
    assert page["total"] == 1
    assert page["items"][0]["finished_at"] == "2026-01-01T00:01:00Z"
    assert detail["order"]["status"] == "completed"
    assert path.stat().st_size == before
    db.close()