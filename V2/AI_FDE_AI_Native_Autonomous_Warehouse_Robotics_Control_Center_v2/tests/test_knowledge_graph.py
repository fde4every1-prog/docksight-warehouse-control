"""Overall knowledge-graph schema — types only, not instance ids."""

import json
from pathlib import Path

from warehouse_control.api import health

ROOT = Path(__file__).resolve().parents[1]
KG = ROOT / "specs" / "09_knowledge_graph.json"
MD = ROOT / "specs" / "09_knowledge_graph.md"
MMD = ROOT / "specs" / "09_knowledge_graph.mmd"

INSTANCE_MARKERS = ("SKU-", "RBT-", "ORD-", "TSK-", "WO-", "BOT-COLLISION", "DC-01-Z03")


def _load():
    return json.loads(KG.read_text(encoding="utf-8"))


def test_knowledge_graph_files_exist():
    assert KG.is_file()
    assert MD.is_file()
    assert MMD.is_file()


def test_graph_is_schema_not_runtime():
    meta = _load()["meta"]
    assert meta["scope"] == "schema"
    assert meta["instances"] is False
    assert meta["runtime"] is False
    assert meta["write_path"] is False
    assert meta["rag"] is False
    assert meta["vector_db"] is False
    assert meta["queried_by_decision_engine"] is False
    assert meta["physical_control"] == "disabled"


def test_schema_has_four_layers_and_core_types():
    data = _load()
    assert [layer["id"] for layer in data["layers"]] == ["L1", "L2", "L3", "L4"]
    ids = {n["id"] for n in data["nodes"]}
    for needed in (
        "ctx:identity",
        "ctx:inventory",
        "ctx:fulfillment",
        "ctx:care",
        "ctx:decision",
        "ctx:shadow",
        "sor:wms",
        "sor:fleet",
        "sor:erp",
        "ent:robot",
        "ent:invobs",
        "ent:order",
        "ent:task",
        "concept:inventory_qty",
        "concept:availability",
        "gate:G1",
        "gate:G8",
        "inv:I12",
        "act:ABSTAIN",
        "pkg:decision",
    ):
        assert needed in ids, needed


def test_all_gates_and_invariants_present():
    ids = {n["id"] for n in _load()["nodes"]}
    for n in range(1, 9):
        assert f"gate:G{n}" in ids
    for n in range(1, 13):
        assert f"inv:I{n}" in ids


def test_no_row_level_instance_ids():
    blob = json.dumps(_load())
    for marker in INSTANCE_MARKERS:
        assert marker not in blob, marker
    md = MD.read_text(encoding="utf-8")
    mmd = MMD.read_text(encoding="utf-8")
    for marker in INSTANCE_MARKERS:
        assert marker not in md, marker
        assert marker not in mmd, marker


def test_no_physical_control_enable_edge():
    forbidden = {"ENABLES_PHYSICAL_CONTROL", "EXECUTES_OT", "WRITES_WMS"}
    types = {e["type"] for e in _load()["edges"]}
    assert types.isdisjoint(forbidden)


def test_markdown_is_overall_mapping():
    text = MD.read_text(encoding="utf-8")
    assert "Overall knowledge-graph mapping" in text
    assert "Who claims which concept" in text
    assert "Neo4j" in text


def test_health_unchanged_by_knowledge_graph():
    assert health()["physical_control"] == "disabled"
