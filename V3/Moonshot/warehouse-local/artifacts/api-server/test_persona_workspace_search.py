"""Focused paging and search tests for the persona workspace."""

from datetime import datetime, timezone

import pytest

import fulfillment_api as fulfillment
import persona_api as persona


@pytest.fixture
def populated_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(fulfillment, "DB_PATH", tmp_path / "workspace-search.sqlite")
    monkeypatch.setattr(
        fulfillment, "utc_now", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    fulfillment._init_db()
    persona._ensure_schema()
    monkeypatch.setattr(persona, "_detect_all", lambda db: None)
    monkeypatch.setattr(persona, "_detect_v2", lambda db: None)

    rows = []
    for index in range(26):
        title = f"Routine issue {index:02d}"
        description = "Routine warehouse exception"
        entity_id = f"entity-{index:02d}"
        warehouse_id = "DC-01"
        if index == 12:
            title = "Mixed CASE Needle in title"
        elif index == 18:
            description = "Description contains NEEDLE"
        elif index == 23:
            entity_id = "entity-needle-23"
        elif index == 24:
            warehouse_id = "dc-needle"
        rows.append(
            (
                f"item-{index:02d}",
                f"dedupe-{index:02d}",
                "inventory_mismatch",
                warehouse_id,
                entity_id,
                title,
                description,
                "supervisor",
                "resolved" if index == 24 else "open",
                "{}",
                None,
                f"2030-01-01T00:{index:02d}:00Z",
                f"2030-01-01T00:{index:02d}:00Z",
            )
        )
    with fulfillment.db_transaction() as db:
        db.executemany(
            "INSERT INTO persona_interventions "
            "(id,dedupe_key,kind,warehouse_id,entity_id,title,description,owner,"
            "status,evidence_json,proposed_action_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )


def test_workspace_returns_nonoverlapping_ten_item_pages(populated_workspace):
    first = persona._workspace("supervisor", limit=10, offset=0)
    second = persona._workspace("supervisor", limit=10, offset=10)

    assert len(first["interventions"]) == len(second["interventions"]) == 10
    assert len(first["issues"]) == len(second["issues"]) == 10
    assert first["pagination"]["intervention_total"] == 26
    assert first["pagination"]["issue_total"] == 25
    assert {row["id"] for row in first["interventions"]}.isdisjoint(
        row["id"] for row in second["interventions"]
    )
    assert {row["id"] for row in first["issues"]}.isdisjoint(
        row["id"] for row in second["issues"]
    )


def test_search_filters_before_counts_and_paging(populated_workspace):
    result = persona._workspace("supervisor", limit=10, offset=0, q="nEeDlE")

    assert result["pagination"]["intervention_total"] == 4
    assert result["pagination"]["issue_total"] == 3
    assert {row["id"] for row in result["interventions"]} == {
        "item-12",
        "item-18",
        "item-23",
        "item-24",
    }
    assert {row["id"] for row in result["issues"]} == {
        "item-12",
        "item-18",
        "item-23",
    }
    assert all(row["status"] != "resolved" for row in result["issues"])
    assert result["summary"] == {
        "open": 25,
        "awaiting_approval": 0,
        "resolved": 1,
    }


def test_omitting_query_preserves_existing_direct_caller_default(populated_workspace):
    omitted = persona.workspace("supervisor")
    explicit_empty = persona._workspace("supervisor", q="")

    assert omitted == explicit_empty
    assert len(omitted["interventions"]) == 26
    assert len(omitted["issues"]) == 25


def test_discrepancies_section_excludes_replenishment_before_counts_and_pages(
    populated_workspace,
):
    with fulfillment.db_transaction() as db:
        db.execute(
            "INSERT INTO persona_interventions "
            "(id,dedupe_key,kind,warehouse_id,entity_id,title,description,owner,"
            "status,evidence_json,proposed_action_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "restock-only",
                "restock-only",
                "replenishment_alert",
                "DC-01",
                "SKU-RESTOCK@BIN-1",
                "Needle replenishment",
                "Needle stock issue",
                "supervisor",
                "open",
                '{"sku":"SKU-RESTOCK","location":"BIN-1"}',
                None,
                "2030-01-01T01:00:00Z",
                "2030-01-01T01:00:00Z",
            ),
        )

    old = persona._workspace("supervisor", limit=500)
    result = persona._workspace(
        "supervisor", limit=10, q="needle", section="discrepancies"
    )

    assert old["pagination"]["intervention_total"] == 27
    assert result["pagination"]["intervention_total"] == 4
    assert result["pagination"]["issue_total"] == 3
    assert all(row["kind"] != "replenishment_alert" for row in result["interventions"])
    assert all(row["kind"] != "replenishment_alert" for row in result["issues"])
    assert result["summary"] == {
        "open": 26,
        "awaiting_approval": 0,
        "resolved": 1,
    }
