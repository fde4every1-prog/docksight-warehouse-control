"""Replay injects against UC-1 allocate/decide. Never enables OT. Never waives G1–G8."""

from warehouse_control.allocator.filter_score import allocate_for_task
from warehouse_control.decision.engine import decide
from warehouse_control.fulfillment.cutoff import assess_cutoff
from warehouse_control.injects.catalog import load_inject
from warehouse_control.repository import csv_rows


def replay_inject(inject_id: str, task_id: str) -> dict:
    spec = load_inject(inject_id)
    task = next((t for t in csv_rows("tasks.csv") if t.get("task_id") == task_id), None)
    allocation = allocate_for_task(task_id, inject_id=inject_id)
    safety = decide(
        {
            "intent": "release_zone",
            "cutoff_pressure": True,
            "shadow_note": "supervisor approved tonight",
            "reason": "inject recovery",
        }
    )
    order_id = (task or {}).get("order_id")
    cutoff = assess_cutoff(order_id) if order_id else None
    miss = decide({"intent": "miss_cutoff", "order_id": order_id})
    chosen = allocation.get("chosen_robot_id")
    return {
        "inject_id": inject_id,
        "title": spec.get("title"),
        "task_id": task_id,
        "allocation": allocation,
        "chosen_robot_id": chosen,
        "decision_hint": allocation.get("decision_hint"),
        "safety_bypass": safety,
        "miss_cutoff_recommend": miss,
        "cutoff": cutoff,
        "gates_intact": safety.get("decision") == "DENY",
        "physical_control": "disabled",
        "execution_applied": False,
    }
