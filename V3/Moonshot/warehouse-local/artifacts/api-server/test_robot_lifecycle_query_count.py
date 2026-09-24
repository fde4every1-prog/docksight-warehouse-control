"""Focused query-count coverage for lifecycle task projection."""
from datetime import timedelta

import fulfillment_api as host
import robot_lifecycle as lifecycle
from test_fulfillment_v2 import order, v2db


ELIGIBLE_TASKS_SQL = """
    SELECT t.* FROM tasks t
    JOIN orders o ON o.id=t.order_id
    WHERE o.policy_version=2
      AND t.status='running' AND t.resource_id IS NOT NULL
      AND t.resource_type IN ('robot','control_asset')
    ORDER BY t.started_at,t.id
"""


def _traced_lifecycle_tasks(db):
    selects = []
    db.set_trace_callback(
        lambda statement: selects.append(statement)
        if statement.lstrip().upper().startswith("SELECT")
        else None
    )
    try:
        result = lifecycle.lifecycle_tasks(db)
    finally:
        db.set_trace_callback(None)
    return result, selects


def test_lifecycle_task_list_queries_are_bounded_and_match_individual_projection(v2db):
    task_ids = []
    for _ in range(12):
        created = host.create_order(order([("A", 1)]))
        task_ids.append(created["sub_orders"][0]["tasks"][0]["id"])

    started_at = host.iso(v2db["now"])
    due_at = host.iso(v2db["now"] + timedelta(seconds=45))
    with host.db_transaction() as db:
        db.execute(
            """UPDATE tasks SET status='running',resource_id='R-BULK-0',
                 resource_type='robot',started_at=?,due_at=?
               WHERE id=?""",
            (started_at, due_at, task_ids[0]),
        )
        first = db.execute(
            "SELECT * FROM tasks WHERE id=?", (task_ids[0],)
        ).fetchone()
        db.execute(
            """INSERT INTO lifecycle_demo_failures(
                 request_id,task_id,request_fingerprint,assignment_token,
                 failed_resource_id,failure_reason,failed_at,intervention_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                "query-count-failure",
                task_ids[0],
                "query-count-fingerprint",
                lifecycle.assignment_token(first),
                "R-BULK-0",
                "Regression failure",
                started_at,
                "INT-QUERY-COUNT",
            ),
        )

        one_result, one_selects = _traced_lifecycle_tasks(db)
        assert len(one_result) == 1
        assert len(one_selects) == 3

        for index, task_id in enumerate(task_ids[1:], start=1):
            db.execute(
                """UPDATE tasks SET status='running',resource_id=?,
                     resource_type='robot',started_at=?,due_at=?
                   WHERE id=?""",
                (f"R-BULK-{index}", started_at, due_at, task_id),
            )

        rows = db.execute(ELIGIBLE_TASKS_SQL).fetchall()
        individually_projected = [
            lifecycle._task_projection(db, task) for task in rows
        ]
        bulk_result, bulk_selects = _traced_lifecycle_tasks(db)

    assert len(bulk_result) == len(task_ids)
    assert bulk_result == individually_projected
    assert len(bulk_selects) == len(one_selects) == 3
    failed = next(item for item in bulk_result if item["task_id"] == task_ids[0])
    assert failed["display_status"] == "Failed (demo) / Recovery required"
    assert failed["assignment_token"] == one_result[0]["assignment_token"]