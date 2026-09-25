"""Isolated regression tests for the transparent demand baseline."""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import demand_forecast
import pytest


def database():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE inventory_snapshot("
        "id INTEGER PRIMARY KEY,warehouse_id TEXT,sku TEXT,"
        "wms_qty INTEGER,erp_qty INTEGER,vision_qty INTEGER)"
    )
    db.execute(
        "CREATE TABLE orders("
        "id TEXT PRIMARY KEY,status TEXT,created_at TEXT,order_created_at TEXT)"
    )
    db.execute(
        "CREATE TABLE sub_orders("
        "id TEXT PRIMARY KEY,order_id TEXT,warehouse_id TEXT,sku TEXT,"
        "quantity INTEGER,status TEXT)"
    )
    return db


def add_order(db, identity, timestamp, quantity, warehouse="W1", *, order_status="active",
              sub_status="running", sku="A"):
    db.execute(
        "INSERT INTO orders VALUES (?,?,?,?)",
        (identity, order_status, timestamp, timestamp),
    )
    db.execute(
        "INSERT INTO sub_orders VALUES (?,?,?,?,?,?)",
        (f"S-{identity}", identity, warehouse, sku, quantity, sub_status),
    )


def test_quantities_grouping_cancellations_unassigned_zero_days_and_ceil():
    db = database()
    db.executemany(
        "INSERT INTO inventory_snapshot VALUES (?,?,?,?,?,?)",
        [(1, "W1", "A", 9, 9, 9), (2, "W2", "A", 9, 9, 9), (3, "W1", "B", 9, 9, 9)],
    )
    # Forecast date is Jan 11 IST. Earliest operational day is Jan 1, so all
    # ten completed calendar days are the denominator, including zero days.
    add_order(db, "one", "2030-01-01T04:00:00Z", 11, "W1")
    add_order(db, "two", "2030-01-05T04:00:00Z", 3, "W1", sub_status="held")
    add_order(db, "other-site", "2030-01-05T04:00:00Z", 2, "W2")
    add_order(db, "cancelled-order", "2030-01-06T04:00:00Z", 50, "W1",
              order_status="cancelled")
    add_order(db, "cancelled-sub", "2030-01-06T04:00:00Z", 50, "W1",
              sub_status="cancelled")
    add_order(db, "unassigned", "2030-01-07T04:00:00Z", 4, None)
    # Jan 11 00:01 IST is an incomplete current-day order and is excluded.
    add_order(db, "future-day", "2030-01-10T18:31:00Z", 99, "W1")

    result = demand_forecast.generate(
        db, date(2030, 1, 11), datetime(2030, 1, 11, 1, tzinfo=timezone.utc)
    )
    assert result["created"] is True
    run = demand_forecast.latest_run(db)
    assert run["excluded_unassigned_units"] == 4
    rows = {
        (row["warehouse_id"], row["sku"]): dict(row)
        for row in db.execute("SELECT * FROM demand_forecasts")
    }
    w1 = rows[("W1", "A")]
    assert w1["history_units"] == 14  # quantities, not two order records
    assert w1["history_days"] == 10
    assert w1["daily_demand"] == 1.4
    assert w1["forecast_7d"] == 10
    assert w1["forecast_30d"] == 42
    assert w1["history_status"] == "short_history"
    assert rows[("W2", "A")]["history_units"] == 2
    assert rows[("W1", "B")]["history_units"] == 0
    assert rows[("W1", "B")]["history_status"] == "no_history"

    # Same business date is transactionally idempotent.
    assert demand_forecast.generate(
        db, date(2030, 1, 11), datetime(2030, 1, 11, 2, tzinfo=timezone.utc)
    ) == {"run_id": result["run_id"], "created": False}


def test_no_history_is_explicit_zero_for_complete_catalog():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    demand_forecast.generate(
        db, date(2030, 2, 1), datetime(2030, 2, 1, tzinfo=timezone.utc)
    )
    row = db.execute("SELECT * FROM demand_forecasts").fetchone()
    assert (row["forecast_7d"], row["forecast_30d"], row["history_days"]) == (0, 0, 0)
    assert row["history_status"] == "no_history"


def test_rejected_demand_uses_original_timestamp_and_expires_from_lookback():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    add_order(db, "rejected", "2030-01-01T04:00:00Z", 12,
              order_status="rejected", sub_status="rejected")
    db.execute("UPDATE orders SET created_at='2030-03-01T00:00:00Z'")
    demand_forecast.generate(db, date(2030, 1, 2), datetime(2030, 1, 2, tzinfo=timezone.utc))
    first = db.execute("SELECT * FROM demand_forecasts").fetchone()
    assert first["history_units"] == 12
    demand_forecast.generate(db, date(2030, 3, 3), datetime(2030, 3, 3, tzinfo=timezone.utc))
    latest = demand_forecast.latest_run(db)
    row = db.execute("SELECT * FROM demand_forecasts WHERE run_id=?", (latest["id"],)).fetchone()
    assert row["history_units"] == 0
    assert row["history_days"] == 0
    assert row["history_status"] == "no_history"


def test_explicit_current_refresh_archives_snapshot_and_preserves_prior_dates():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    add_order(db, "initial", "2030-01-01T04:00:00Z", 10)
    prior = demand_forecast.generate(db, date(2030, 1, 2), datetime(2030, 1, 2, 1, tzinfo=timezone.utc))
    now = datetime(2030, 1, 3, 1, tzinfo=timezone.utc)
    original = demand_forecast.generate(db, date(2030, 1, 3), now)
    before_run = tuple(db.execute("SELECT * FROM demand_forecast_runs WHERE id=?", (original["run_id"],)).fetchone())
    before_value = tuple(db.execute("SELECT * FROM demand_forecasts WHERE run_id=?", (original["run_id"],)).fetchone())
    add_order(db, "imported-rejected", "2030-01-01T05:00:00Z", 7, order_status="rejected", sub_status="rejected")
    db.execute("BEGIN")
    result = demand_forecast.refresh_current(db, now)
    assert result["superseded_run_id"] == original["run_id"]
    archived = tuple(db.execute("SELECT * FROM demand_forecast_superseded_runs").fetchone())
    assert archived[:-1] == before_run
    assert tuple(db.execute("SELECT * FROM demand_forecast_superseded_values").fetchone()) == before_value
    assert db.execute("SELECT history_units FROM demand_forecasts WHERE run_id=?", (result["run_id"],)).fetchone()[0] == 17
    assert db.execute("SELECT history_units FROM demand_forecasts WHERE run_id=?", (prior["run_id"],)).fetchone()[0] == 10
    assert demand_forecast.generate(db, date(2030, 1, 3), now)["created"] is False


def test_explicit_refresh_rolls_back_with_import():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    now = datetime(2030, 1, 3, 1, tzinfo=timezone.utc)
    old = demand_forecast.generate(db, date(2030, 1, 3), now)
    db.commit()
    db.execute("BEGIN")
    new = demand_forecast.refresh_current(db, now)
    assert old["run_id"] != new["run_id"]
    db.rollback()
    assert demand_forecast.latest_run(db)["id"] == old["run_id"]


def test_ist_schedule_boundary_and_next_run():
    before = datetime(2030, 1, 1, 0, 29, 59, tzinfo=timezone.utc)  # 05:59:59 IST
    at = datetime(2030, 1, 1, 0, 30, 0, tzinfo=timezone.utc)  # 06:00 IST
    assert demand_forecast.expected_forecast_date(before) == date(2029, 12, 31)
    assert demand_forecast.expected_forecast_date(at) == date(2030, 1, 1)
    assert demand_forecast.next_scheduled_at(before) == at
    assert demand_forecast.next_scheduled_at(at) == datetime(
        2030, 1, 2, 0, 30, tzinfo=timezone.utc
    )


def test_before_six_bootstrap_and_restart_use_latest_scheduled_date_only():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")

    @contextmanager
    def transaction():
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise

    before = datetime(2030, 1, 1, 0, 20, tzinfo=timezone.utc)  # 05:50 IST
    first = demand_forecast.ensure_due_run(transaction, before)
    restarted = demand_forecast.ensure_due_run(transaction, before)
    assert first["created"] is True
    assert restarted == {"run_id": first["run_id"], "created": False}
    assert [
        row["forecast_date"]
        for row in db.execute(
            "SELECT forecast_date FROM demand_forecast_runs ORDER BY forecast_date"
        )
    ] == ["2029-12-31"]

    scheduled = demand_forecast.ensure_due_run(
        transaction, datetime(2030, 1, 1, 0, 30, tzinfo=timezone.utc)
    )
    assert scheduled["created"] is True
    assert [
        row["forecast_date"]
        for row in db.execute(
            "SELECT forecast_date FROM demand_forecast_runs ORDER BY forecast_date"
        )
    ] == ["2029-12-31", "2030-01-01"]


def test_rolling_sixty_day_cutoff_and_large_integer_ceil_are_exact():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    units = 9_007_199_254_740_993
    # Forecast Mar 3 starts Jan 2 00:00 IST. The first two orders straddle that
    # exact boundary; the older history also proves the denominator clamps at 60.
    add_order(db, "very-old", "2029-12-01T00:00:00Z", 999_999, "W1")
    add_order(db, "before-cutoff", "2030-01-01T18:29:59Z", 777_777, "W1")
    add_order(db, "at-cutoff", "2030-01-01T18:30:00Z", units, "W1")
    demand_forecast.generate(
        db, date(2030, 3, 3), datetime(2030, 3, 3, tzinfo=timezone.utc)
    )
    row = db.execute("SELECT * FROM demand_forecasts").fetchone()
    assert row["history_days"] == 60
    assert row["history_units"] == units
    assert row["forecast_7d"] == (units * 7 + 59) // 60
    assert row["forecast_30d"] == (units * 30 + 59) // 60
    assert row["history_status"] == "observed"


def test_extended_history_and_exact_exclusive_end():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    end = datetime(2030, 3, 3, tzinfo=demand_forecast.IST)
    for days, quantity in [(45, 45), (31, 31), (1, 1), (0, 999), (-1, 999)]:
        add_order(db, str(days), (end - timedelta(days=days)).isoformat(), quantity)
    add_order(db, "rejected", (end - timedelta(days=40)).isoformat(), 3,
              order_status="rejected", sub_status="rejected")
    add_order(db, "cancelled", (end - timedelta(days=55)).isoformat(), 999,
              order_status="cancelled")
    demand_forecast.generate(db, end.date(), end)
    row = db.execute("SELECT * FROM demand_forecasts").fetchone()
    assert row["history_units"] == 80
    assert row["history_days"] == 45
    assert row["history_status"] == "short_history"
    assert row["forecast_7d"] == 13
    assert row["forecast_30d"] == 54
    assert demand_forecast.run_lookback_days(demand_forecast.latest_run(db)) == 60


def test_legacy_metadata_survives_upgrade_and_refresh(monkeypatch):
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    add_order(db, "older-demand", "2030-01-10T00:00:00Z", 45)
    now = datetime(2030, 3, 3, 1, tzinfo=timezone.utc)
    with monkeypatch.context() as patch:
        patch.setattr(demand_forecast, "LOOKBACK_DAYS", 30)
        patch.setattr(demand_forecast, "METHOD", demand_forecast.LEGACY_METHOD)
        old = demand_forecast.generate(db, now.date(), now)
    before = dict(demand_forecast.latest_run(db))
    assert demand_forecast.run_lookback_days(before) == 30
    assert db.execute("SELECT history_units FROM demand_forecasts").fetchone()[0] == 0
    # Model configuration changes alone never mutate a saved snapshot.
    assert demand_forecast.generate(db, now.date(), now)["created"] is False
    db.execute("BEGIN")
    refreshed = demand_forecast.refresh_current(db, now)
    db.commit()
    assert refreshed["superseded_run_id"] == old["run_id"]
    archived = dict(db.execute("SELECT * FROM demand_forecast_superseded_runs").fetchone())
    archived.pop("superseded_at")
    assert archived == before
    assert demand_forecast.run_lookback_days(archived) == 30
    assert demand_forecast.run_lookback_days(demand_forecast.latest_run(db)) == 60
    assert db.execute("SELECT history_units FROM demand_forecasts").fetchone()[0] == 45


def test_failed_transaction_leaves_no_partial_run_and_retry_succeeds():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    db.execute("BEGIN IMMEDIATE")
    created = demand_forecast.generate(
        db, date(2030, 1, 2), datetime(2030, 1, 2, tzinfo=timezone.utc)
    )
    assert created["created"] is True
    db.execute("ROLLBACK")
    # DDL and both run/item writes participate in the caller transaction.
    assert db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='demand_forecast_runs'"
    ).fetchone() is None

    db.execute("BEGIN IMMEDIATE")
    retried = demand_forecast.generate(
        db, date(2030, 1, 2), datetime(2030, 1, 2, tzinfo=timezone.utc)
    )
    db.execute("COMMIT")
    assert retried["created"] is True
    assert db.execute("SELECT COUNT(*) FROM demand_forecast_runs").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM demand_forecasts").fetchone()[0] == 1


def test_restart_catches_up_only_latest_date_after_multiple_missed_days():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")

    @contextmanager
    def transaction():
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise

    old_now = datetime(2030, 1, 1, 1, tzinfo=timezone.utc)
    demand_forecast.ensure_due_run(transaction, old_now)
    assert demand_forecast.latest_run(db)["forecast_date"] == "2030-01-01"
    restart = datetime(2030, 1, 4, 1, tzinfo=timezone.utc)
    assert demand_forecast.latest_run(db)["forecast_date"] < (
        demand_forecast.expected_forecast_date(restart).isoformat()
    )
    demand_forecast.ensure_due_run(transaction, restart)
    assert [
        row["forecast_date"]
        for row in db.execute(
            "SELECT forecast_date FROM demand_forecast_runs ORDER BY forecast_date"
        )
    ] == ["2030-01-01", "2030-01-04"]


def test_generation_reads_canonical_demand_once_as_catalog_grows():
    db = database()
    db.executemany(
        "INSERT INTO inventory_snapshot VALUES (?,?,?,?,?,?)",
        [(index, f'W{index % 10}', f'SKU-{index}', 1, 1, 1) for index in range(1, 1001)],
    )
    add_order(db, "one", "2030-01-01T00:00:00Z", 2, "W1", sku="SKU-1")
    demand_reads = []
    db.set_trace_callback(
        lambda sql: demand_reads.append(sql)
        if "FROM sub_orders s" in sql
        else None
    )
    demand_forecast.generate(
        db, date(2030, 1, 2), datetime(2030, 1, 2, tzinfo=timezone.utc)
    )
    db.set_trace_callback(None)
    assert len(demand_reads) == 1
    assert db.execute("SELECT COUNT(*) FROM demand_forecasts").fetchone()[0] == 1000


def test_saved_daily_evidence_reconciles_and_survives_mutation_and_refresh():
    db = database()
    db.executemany(
        "INSERT INTO inventory_snapshot VALUES (?,?,?,?,?,?)",
        [(1, "W1", "A", 1, 1, 1), (2, "W2", "A", 1, 1, 1),
         (3, "W1", "B", 1, 1, 1)],
    )
    # UTC Jan 1 becomes Jan 2 IST, including the exact midnight boundary.
    add_order(db, "first", "2030-01-01T18:30:00Z", 10)
    add_order(db, "rejected", "2030-01-07T18:30:00Z", 3,
              order_status="rejected", sub_status="rejected")
    add_order(db, "other-site", "2030-01-02T00:00:00Z", 80, "W2")
    add_order(db, "cancelled-parent", "2030-01-03T00:00:00Z", 99,
              order_status="cancelled")
    add_order(db, "cancelled-child", "2030-01-03T00:00:00Z", 99,
              sub_status="cancelled")
    add_order(db, "unassigned", "2030-01-03T00:00:00Z", 7, None)
    add_order(db, "negative", "2030-01-03T00:00:00Z", -8)
    add_order(db, "current-day", "2030-01-09T18:30:00Z", 99)
    now = datetime(2030, 1, 10, 1, tzinfo=timezone.utc)
    db.execute("BEGIN IMMEDIATE")
    generated = demand_forecast.generate(db, now.date(), now)
    db.commit()
    detail = demand_forecast.saved_detail(db, "W1", "A")
    assert detail["history_available"]
    history = detail["history"]
    assert [row["ordered_units"] for row in history] == [10, 0, 0, 0, 0, 0, 3, 0]
    assert history[0]["date"] == "2030-01-02"
    assert history[-1]["date"] == "2030-01-09"
    assert all(row["rolling_7d"] is None for row in history[:6])
    assert history[6]["rolling_7d"] == pytest.approx(13 / 7)
    assert history[7]["rolling_7d"] == pytest.approx(3 / 7)
    assert sum(row["ordered_units"] for row in history) == detail["item"]["history_units"] == 13
    assert detail["item"]["daily_demand"] == 13 / 8
    assert detail["item"]["forecast_7d"] == 12
    assert detail["item"]["forecast_30d"] == 49
    assert detail["run"]["excluded_unassigned_units"] == 7
    assert len(detail["projection"]) == 30
    assert detail["projection"][0] == {"date": "2030-01-10", "daily_demand": 13 / 8}
    assert detail["projection"][-1]["date"] == "2030-02-08"
    assert all(row["daily_demand"] == 13 / 8 for row in detail["projection"])
    assert demand_forecast.saved_detail(db, "W2", "A")["history"][0]["ordered_units"] == 80
    assert all(row["ordered_units"] == 0 for row in demand_forecast.saved_detail(db, "W1", "B")["history"])
    assert demand_forecast.saved_detail(db, "W3", "A") is None
    assert demand_forecast.saved_detail(db, "W1", "A", "missing") is None

    db.execute("UPDATE sub_orders SET quantity=400")
    db.execute("UPDATE orders SET status='cancelled'")
    assert demand_forecast.saved_detail(db, "W1", "A") == detail
    assert demand_forecast.generate(db, now.date(), now)["created"] is False
    assert demand_forecast.saved_detail(db, "W1", "A") == detail
    db.execute("BEGIN IMMEDIATE")
    refreshed = demand_forecast.refresh_current(db, now)
    db.commit()
    assert refreshed["superseded_run_id"] == generated["run_id"]
    archived = demand_forecast.saved_detail(db, "W1", "A", generated["run_id"])
    archived["run"].pop("superseded_at")
    assert archived == detail
    assert demand_forecast.saved_detail(db, "W1", "A")["history"] == []


def test_empty_captured_window_is_distinct_from_unavailable_legacy():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    now = datetime(2030, 1, 10, 1, tzinfo=timezone.utc)
    generated = demand_forecast.generate(db, now.date(), now)
    detail = demand_forecast.saved_detail(db, "W1", "A")
    assert detail["history_available"] is True
    assert detail["history"] == []
    assert detail["item"]["history_status"] == "no_history"
    assert detail["item"]["history_days"] == 0
    # Simulate a pre-feature database, without falsely asserting evidence exists.
    db.execute("DROP TABLE demand_forecast_captures")
    db.execute("DROP TABLE demand_forecast_daily_inputs")
    add_order(db, "new", "2030-01-09T00:00:00Z", 9)
    assert demand_forecast.generate(db, now.date(), now)["created"] is False
    legacy = demand_forecast.saved_detail(db, "W1", "A")
    assert legacy["history_available"] is False
    assert legacy["history"] == []
    db.execute("BEGIN IMMEDIATE")
    demand_forecast.refresh_current(db, now)
    db.commit()
    assert demand_forecast.saved_detail(db, "W1", "A", generated["run_id"])["history_available"] is False
    current = demand_forecast.saved_detail(db, "W1", "A")
    assert current["history_available"] is True
    assert current["history"] == [{"date": "2030-01-09", "ordered_units": 9, "rolling_7d": None}]


def test_capture_and_refresh_rollback_are_atomic():
    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    add_order(db, "one", "2030-01-09T00:00:00Z", 4)
    now = datetime(2030, 1, 10, 1, tzinfo=timezone.utc)
    demand_forecast.ensure_schema(db)
    db.execute("BEGIN IMMEDIATE")
    demand_forecast.generate(db, now.date(), now)
    assert db.execute("SELECT COUNT(*) FROM demand_forecast_daily_inputs").fetchone()[0] == 1
    db.rollback()
    for table in ("demand_forecast_runs", "demand_forecasts",
                  "demand_forecast_captures", "demand_forecast_daily_inputs"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    db.execute("BEGIN IMMEDIATE")
    demand_forecast.generate(db, now.date(), now)
    db.commit()
    before = demand_forecast.saved_detail(db, "W1", "A")
    db.execute("BEGIN IMMEDIATE")
    demand_forecast.refresh_current(db, now)
    db.rollback()
    assert demand_forecast.saved_detail(db, "W1", "A") == before
    assert db.execute("SELECT COUNT(*) FROM demand_forecast_captures").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM demand_forecast_daily_inputs").fetchone()[0] == 1


def test_detail_api_live_stock_exact_selection_and_no_generation(monkeypatch):
    import fulfillment_api as api

    db = database()
    db.execute("INSERT INTO inventory_snapshot VALUES (1,'W1','A',1,1,1)")
    add_order(db, "one", "2030-01-09T00:00:00Z", 4)
    now = datetime(2030, 1, 10, 1, tzinfo=timezone.utc)
    demand_forecast.generate(db, now.date(), now)

    @contextmanager
    def read_db():
        yield db

    stock = [
        {"warehouse_id": "W1", "sku": "A", "wms_qty": 10, "erp_qty": 3, "vision_qty": 8},
        {"warehouse_id": "W1", "sku": "A", "wms_qty": 9, "erp_qty": 9, "vision_qty": 2},
        {"warehouse_id": "W1", "sku": "A", "wms_qty": -1, "erp_qty": 9, "vision_qty": 2},
    ]

    def inventory(db, warehouse_id=None, sku=None):
        assert warehouse_id in (None, "W1")
        assert sku in (None, "A")
        return stock

    monkeypatch.setattr(api, "_read_db", read_db)
    monkeypatch.setattr(api, "inventory_rows", inventory)
    monkeypatch.setattr(demand_forecast, "generate", lambda *args: pytest.fail("GET must not generate"))
    result = api.demand_forecast_detail("W1", "A", None)
    listing = api.demand_forecasts(None, None)
    assert result["run"] == listing["run"]
    assert result["item"] == listing["items"][0]
    assert result["item"]["available_qty"] == 5
    assert result["minimum_replenishment"] == 23
    assert result["stock_checked_at"].endswith("Z")
    stock[0]["erp_qty"] = 40
    again = api.demand_forecast_detail("W1", "A", result["run"]["id"])
    assert again["item"]["available_qty"] == 10
    assert again["minimum_replenishment"] == 18
    assert again["history"] == result["history"]
    for warehouse, sku, run_id in [("W2", "A", None), ("W1", "B", None), ("W1", "A", "missing")]:
        with pytest.raises(api.HTTPException) as error:
            api.demand_forecast_detail(warehouse, sku, run_id)
        assert error.value.status_code == 404