from warehouse_control.diagnostics import run
from warehouse_control.legacy.inventory import legacy_available_qty

def test_diagnostics_has_population():
    d=run(); assert d['robots'] > 400

def test_legacy_inventory_math():
    assert legacy_available_qty({'wms_qty':'10','reserved_qty':'3'}) == 7

def test_conflicts_exist_for_capstone():
    d=run(); assert d['inventory_truth_conflicts'] > 100 and d['wes_fleet_task_conflicts'] > 100
