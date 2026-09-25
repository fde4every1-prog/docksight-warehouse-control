"""Safety regressions for the offline synthetic fleet correction command."""

import hashlib
import sqlite3

import pytest

import fleet_offline_repair as repair
import fulfillment_api as fulfillment
import persona_api as persona


@pytest.fixture
def repair_store(tmp_path, monkeypatch):
    warehouses = ("W-1", "W-2", "W-3")
    data = {
        "warehouses": tuple({"warehouse_id": warehouse} for warehouse in warehouses),
        "robots": tuple(
            {
                "robot_id": f"R-{warehouse}-{number}",
                "warehouse_id": warehouse,
                "robot_type": "AMR",
                "health_status": "DEGRADED",
                "safety_cert_status": "VALID",
                "connectivity": "OFFLINE",
                "payload_kg": "100",
                "battery_soc": "17",
            }
            for warehouse in warehouses
            for number in range(2)
        ),
        "maintenance": tuple(
            {
                "work_order_id": f"M-{warehouse}-{number}",
                "robot_id": f"R-{warehouse}-{number}",
                "warehouse_id": warehouse,
                "cmms_status": "OPEN",
                "fleet_availability": "UNAVAILABLE",
            }
            for warehouse in warehouses
            for number in range(2)
        ),
        "control_assets": tuple(
            {
                "asset_id": f"A-{warehouse}-{number}",
                "warehouse_id": warehouse,
                "asset_type": "CONVEYOR",
                "state": "OFFLINE",
                "maintenance_state": "DUE",
            }
            for warehouse in warehouses
            for number in range(2)
        ),
        "inventory": (),
        "skus": (),
        "labor_capacity": (),
    }

    def rows(dataset):
        return data.get(dataset, ())

    rows.cache_clear = lambda: None
    monkeypatch.setattr(persona, "_ORIGINAL_RAW_SOURCE_ROWS", rows)
    fulfillment_path = tmp_path / "fulfillment.sqlite"
    bazaar_path = tmp_path / "bazaar.sqlite"
    monkeypatch.setattr(fulfillment, "DB_PATH", fulfillment_path)
    fulfillment._init_db()
    persona._ensure_schema()
    with sqlite3.connect(bazaar_path) as db:
        db.execute("CREATE TABLE marker(value TEXT)")
        db.execute("INSERT INTO marker VALUES ('read-only')")
    return fulfillment_path, bazaar_path


def _digest(path):
    with sqlite3.connect(path) as db:
        logical = "\n".join(db.iterdump()).encode()
    return hashlib.sha256(logical).hexdigest()


def _correction_count(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT COUNT(*) FROM persona_source_corrections").fetchone()[0]


def test_balanced_selection_is_deterministic_and_represents_every_warehouse():
    candidates = []
    for warehouse in ("W-2", "W-1", "W-3"):
        for kind, prefix in (
            ("fleet_readiness", "R"),
            ("control_asset_readiness", "A"),
        ):
            for number in range(3):
                candidates.append(
                    {
                        "id": f"I-{prefix}-{warehouse}-{number}",
                        "entity_id": f"{prefix}-{warehouse}-{number}",
                        "warehouse_id": warehouse,
                        "kind": kind,
                        "impacted": number == 2,
                        "spec": {"blockers": ["unsafe"]},
                    }
                )
    first = repair.select_balanced(list(reversed(candidates)), 12)
    second = repair.select_balanced(candidates, 12)
    assert [item["id"] for item in first] == [item["id"] for item in second]
    summary = repair._summary(first)
    assert summary["warehouse_count"] == 3
    assert set(summary["warehouses"]) == {"W-1", "W-2", "W-3"}
    assert all(abs(counts["robots"] - counts["assets"]) <= 1 for counts in summary["warehouses"].values())


def test_exact_target_validation_refuses_wrong_current_total(repair_store):
    fulfillment_path, bazaar_path = repair_store
    with pytest.raises(RuntimeError, match="expected exactly 13"):
        repair.repair_fleet_issues(
            fulfillment_path,
            bazaar_path,
            target=9,
            expected_total=13,
            dry_run=True,
        )
    assert _correction_count(fulfillment_path) == 0


def test_dry_run_performs_full_plan_without_mutation(repair_store):
    fulfillment_path, bazaar_path = repair_store
    before_fulfillment = _digest(fulfillment_path)
    before_bazaar = _digest(bazaar_path)
    result = repair.repair_fleet_issues(
        fulfillment_path,
        bazaar_path,
        target=9,
        expected_total=12,
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["selected"] == 9
    assert result["remaining"] == 3
    assert result["selection"]["warehouse_count"] == 3
    assert _digest(fulfillment_path) == before_fulfillment
    assert _digest(bazaar_path) == before_bazaar


def test_injected_failure_rolls_back_whole_transaction(repair_store):
    fulfillment_path, bazaar_path = repair_store
    before = _digest(fulfillment_path)

    def failpoint(label):
        if label == "mid_repair":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        repair.repair_fleet_issues(
            fulfillment_path,
            bazaar_path,
            target=9,
            expected_total=12,
            dry_run=False,
            backup_dir=fulfillment_path.parent / "backups",
            failpoint=failpoint,
        )
    assert _digest(fulfillment_path) == before
    assert _correction_count(fulfillment_path) == 0


def test_apply_repairs_exact_target_and_keeps_bazaar_read_only(repair_store):
    fulfillment_path, bazaar_path = repair_store
    bazaar_before = _digest(bazaar_path)
    result = repair.repair_fleet_issues(
        fulfillment_path,
        bazaar_path,
        target=9,
        expected_total=12,
        dry_run=False,
        backup_dir=fulfillment_path.parent / "backups",
    )
    assert result["applied"] is True
    assert result["selected"] == 9
    assert result["remaining"] == 3
    assert result["selection"]["warehouse_count"] == 3
    assert bazaar_before == _digest(bazaar_path)
    assert (fulfillment_path.parent / "backups").is_dir()
    with sqlite3.connect(result["backups"]["fulfillment"]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with sqlite3.connect(fulfillment_path) as db:
        open_count = db.execute(
            "SELECT COUNT(*) FROM persona_interventions WHERE status<>'resolved' "
            "AND kind IN ('fleet_readiness','control_asset_readiness')"
        ).fetchone()[0]
        reasons = {
            row[0]
            for row in db.execute(
                "SELECT DISTINCT reason FROM persona_audit_events "
                "WHERE action='fleet_repair'"
            )
        }
    assert open_count == 3
    assert reasons == {repair.REASON}