"""Durable simulation state. All operations join the caller's write transaction."""
import json
import math
import hashlib
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from fleet_readiness import robot_readiness, asset_readiness


def stamp(now):
    return now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS resource_lifecycle(
        resource_id TEXT PRIMARY KEY, resource_kind TEXT NOT NULL,
        resource_type TEXT, warehouse_id TEXT, fitness_status TEXT NOT NULL,
        fitness_reasons TEXT NOT NULL, charging TEXT NOT NULL DEFAULT 'N',
        battery_pct REAL, battery_at TEXT NOT NULL, current_task_id TEXT,
        current_stage TEXT, updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)""")
    db.execute("""CREATE TABLE IF NOT EXISTS lifecycle_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
        resource_id TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS lifecycle_scheduler(
        id INTEGER PRIMARY KEY CHECK(id=1),last_assignment_at TEXT,next_assignment_at TEXT,
        last_observed_at TEXT)""")
    if "last_observed_at" not in {r[1] for r in db.execute("PRAGMA table_info(lifecycle_scheduler)")}:
        db.execute("ALTER TABLE lifecycle_scheduler ADD COLUMN last_observed_at TEXT")
    db.execute("INSERT OR IGNORE INTO lifecycle_scheduler(id) VALUES(1)")
    task_columns = {r[1] for r in db.execute("PRAGMA table_info(tasks)")}
    if "assignment_version" not in task_columns:
        db.execute(
            "ALTER TABLE tasks ADD COLUMN assignment_version INTEGER NOT NULL DEFAULT 0"
        )
    db.execute("""CREATE TABLE IF NOT EXISTS lifecycle_demo_failures(
        request_id TEXT PRIMARY KEY, task_id TEXT NOT NULL
        REFERENCES tasks(id) ON DELETE CASCADE,
        request_fingerprint TEXT NOT NULL,
        assignment_token TEXT NOT NULL, failed_resource_id TEXT NOT NULL,
        failure_reason TEXT NOT NULL, failed_at TEXT NOT NULL,
        intervention_id TEXT NOT NULL UNIQUE, response_json TEXT,
        resolved_at TEXT)""")
    failure_info = list(db.execute("PRAGMA table_info(lifecycle_demo_failures)"))
    failure_columns = {r[1] for r in failure_info}
    if "response_json" not in failure_columns:
        db.execute("ALTER TABLE lifecycle_demo_failures ADD COLUMN response_json TEXT")
    if "resolved_at" not in failure_columns:
        db.execute("ALTER TABLE lifecycle_demo_failures ADD COLUMN resolved_at TEXT")
    # The first release keyed failures by task_id, which discarded history and
    # prevented a recovered assignment of the same task from failing again.
    # Rebuild in the caller's transaction and preserve every recorded command.
    if any(r[1] == "task_id" and r[5] for r in failure_info):
        db.execute("""CREATE TABLE lifecycle_demo_failures_v2(
            request_id TEXT PRIMARY KEY, task_id TEXT NOT NULL
            REFERENCES tasks(id) ON DELETE CASCADE,
            request_fingerprint TEXT NOT NULL, assignment_token TEXT NOT NULL,
            failed_resource_id TEXT NOT NULL, failure_reason TEXT NOT NULL,
            failed_at TEXT NOT NULL, intervention_id TEXT NOT NULL UNIQUE,
            response_json TEXT, resolved_at TEXT)""")
        db.execute(
            """INSERT INTO lifecycle_demo_failures_v2(
                 request_id,task_id,request_fingerprint,assignment_token,
                 failed_resource_id,failure_reason,failed_at,intervention_id,
                 response_json,resolved_at)
               SELECT request_id,task_id,request_fingerprint,assignment_token,
                 failed_resource_id,failure_reason,failed_at,intervention_id,
                 response_json,resolved_at
               FROM lifecycle_demo_failures"""
        )
        db.execute("DROP TABLE lifecycle_demo_failures")
        db.execute(
            "ALTER TABLE lifecycle_demo_failures_v2 RENAME TO lifecycle_demo_failures"
        )
    db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS lifecycle_one_active_failure_per_task
           ON lifecycle_demo_failures(task_id) WHERE resolved_at IS NULL"""
    )
    db.execute("""CREATE TABLE IF NOT EXISTS lifecycle_simulator_failures(
        request_id TEXT PRIMARY KEY, task_id TEXT NOT NULL
        REFERENCES tasks(id) ON DELETE CASCADE,
        request_fingerprint TEXT NOT NULL, assignment_token TEXT NOT NULL,
        failed_resource_id TEXT NOT NULL, failed_resource_kind TEXT NOT NULL,
        failure_reason TEXT NOT NULL, failed_at TEXT NOT NULL,
        replacement_status TEXT NOT NULL, replacement_resource_id TEXT,
        response_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS lifecycle_failed_resources(
        resource_id TEXT PRIMARY KEY, resource_kind TEXT NOT NULL,
        task_id TEXT NOT NULL, request_id TEXT NOT NULL,
        reason TEXT NOT NULL, failed_at TEXT NOT NULL, recovered_at TEXT)""")
    # These are the existing persona recovery ledger tables.  Creating them
    # here on the caller's connection keeps failure injection in one atomic
    # transaction even when lifecycle is the first persona feature used.
    db.execute("""CREATE TABLE IF NOT EXISTS persona_interventions(
        id TEXT PRIMARY KEY, dedupe_key TEXT UNIQUE, kind TEXT NOT NULL,
        warehouse_id TEXT NOT NULL, entity_id TEXT NOT NULL, title TEXT NOT NULL,
        description TEXT NOT NULL, owner TEXT NOT NULL, status TEXT NOT NULL,
        evidence_json TEXT NOT NULL, proposed_action_json TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        recurrence_count INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS persona_intervention_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, intervention_id TEXT NOT NULL,
        at TEXT NOT NULL, persona TEXT NOT NULL, action TEXT NOT NULL,
        reason TEXT NOT NULL, details_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS persona_audit_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
        persona TEXT NOT NULL, action TEXT NOT NULL, entity_id TEXT NOT NULL,
        reason TEXT NOT NULL, details_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS persona_task_pauses(
        task_id TEXT PRIMARY KEY, remaining_seconds INTEGER NOT NULL,
        resource_id TEXT, reason TEXT NOT NULL, intervention_id TEXT NOT NULL,
        paused_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS persona_resource_blocks(
        resource_id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL,
        reason TEXT NOT NULL, intervention_id TEXT NOT NULL,
        created_at TEXT NOT NULL)""")


def event(db, now, resource_id, action, details):
    db.execute("INSERT INTO lifecycle_events(at,resource_id,action,details) VALUES(?,?,?,?)",
               (stamp(now), resource_id, action, json.dumps(details)))


def assignment_token(task):
    """Opaque identity for one acquisition, not merely a task/resource pair."""
    raw = "\0".join(
        str(value or "")
        for value in (
            task["id"],
            task["resource_id"],
            task["resource_type"],
            task["started_at"],
            task["assignment_version"],
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _task_projection(db, task, failure=None, sub=None, *, failure_loaded=False):
    if failure is None and not failure_loaded:
        failure = db.execute(
            """SELECT * FROM lifecycle_demo_failures
               WHERE task_id=? AND resolved_at IS NULL""",
            (task["id"],),
        ).fetchone()
    if sub is None:
        sub = db.execute(
            "SELECT sku,warehouse_id FROM sub_orders WHERE id=?",
            (task["sub_order_id"],),
        ).fetchone()
    failed_resource = failure["failed_resource_id"] if failure else None
    failed_at = failure["failed_at"] if failure else None
    intervention_id = failure["intervention_id"] if failure else None
    return {
        "task_id": task["id"],
        "order_id": task["order_id"],
        "sub_order_id": task["sub_order_id"],
        "sku": sub["sku"],
        "robot_id": task["resource_id"] or failed_resource,
        "resource_id": task["resource_id"] or failed_resource,
        "resource_kind": task["resource_type"] or (
            "robot" if failure else None
        ),
        "warehouse_id": sub["warehouse_id"],
        "stage": task["stage"],
        "status": task["status"],
        "display_status": (
            "Failed (demo) / Recovery required"
            if failure
            else {"running": "Running", "paused": "Paused", "queued": "Queued"}.get(
                task["status"], task["status"].replace("_", " ").title()
            )
        ),
        "started_at": task["started_at"],
        "due_at": task["due_at"],
        "assignment_token": (
            failure["assignment_token"] if failure else assignment_token(task)
        ),
        "failure_reason": failure["failure_reason"] if failure else None,
        "failed_at": failed_at,
        "intervention_id": intervention_id,
        "recovery_url": (
            f"/workspace/interventions/{intervention_id}" if intervention_id else None
        ),
    }


def lifecycle_tasks(db):
    """Currently running, assigned robot and control-asset functions."""
    ensure_schema(db)
    rows = db.execute(
        """SELECT t.* FROM tasks t
           JOIN orders o ON o.id=t.order_id
           WHERE o.policy_version=2
             AND t.status='running' AND t.resource_id IS NOT NULL
             AND t.resource_type IN ('robot','control_asset')
           ORDER BY t.started_at,t.id"""
    ).fetchall()
    if not rows:
        return []
    failures = {
        row["task_id"]: row
        for row in db.execute(
            """SELECT f.* FROM lifecycle_demo_failures f
               JOIN tasks t ON t.id=f.task_id
               JOIN orders o ON o.id=t.order_id
               WHERE o.policy_version=2
                 AND t.status='running' AND t.resource_id IS NOT NULL
                 AND t.resource_type IN ('robot','control_asset')
                 AND f.resolved_at IS NULL"""
        )
    }
    sub_orders = {
        row["id"]: row
        for row in db.execute(
            """SELECT s.id,s.sku,s.warehouse_id FROM sub_orders s
               JOIN tasks t ON t.sub_order_id=s.id
               JOIN orders o ON o.id=t.order_id
               WHERE o.policy_version=2
                 AND t.status='running' AND t.resource_id IS NOT NULL
                 AND t.resource_type IN ('robot','control_asset')"""
        )
    }
    return [
        _task_projection(
            db,
            task,
            failures.get(task["id"]),
            sub_orders.get(task["sub_order_id"]),
            failure_loaded=True,
        )
        for task in rows
    ]


def kill_task(db, task_id, request_id, token, reason, now, source_rows, append_event):
    """End one exact assignment and promptly ask Core for a replacement."""
    ensure_schema(db)
    clean_reason = reason.strip()
    fingerprint = hashlib.sha256(
        json.dumps(
            {"task_id": task_id, "assignment_token": token, "reason": reason},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing = db.execute(
        "SELECT * FROM lifecycle_simulator_failures WHERE request_id=?", (request_id,)
    ).fetchone()
    if existing:
        if existing["request_fingerprint"] != fingerprint:
            raise HTTPException(
                409, "request_id is already associated with a different kill payload"
            )
        return json.loads(existing["response_json"])

    task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise HTTPException(404, "Unknown lifecycle task")
    order = db.execute(
        "SELECT policy_version FROM orders WHERE id=?", (task["order_id"],)
    ).fetchone()
    if not order or order["policy_version"] != 2:
        raise HTTPException(
            409, "Only Core policy-v2 assignments support automatic replacement"
        )
    if (
        task["status"] != "running"
        or not task["resource_id"]
        or task["resource_type"] not in {"robot", "control_asset"}
    ):
        raise HTTPException(409, "Function is no longer a running assigned function")
    if assignment_token(task) != token:
        raise HTTPException(409, "Function assignment changed; refresh and retry")

    failed_resource = task["resource_id"]
    failed_kind = task["resource_type"]
    at = stamp(now)
    db.execute(
        """INSERT INTO lifecycle_failed_resources(
             resource_id,resource_kind,task_id,request_id,reason,failed_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(resource_id) DO UPDATE SET
             resource_kind=excluded.resource_kind,task_id=excluded.task_id,
             request_id=excluded.request_id,reason=excluded.reason,
             failed_at=excluded.failed_at,recovered_at=NULL""",
        (failed_resource, failed_kind, task_id, request_id, clean_reason, at),
    )
    changed = db.execute(
        """UPDATE tasks SET status='queued',resource_id=NULL,resource_type=NULL,
             started_at=NULL,due_at=NULL,
             wait_reason='WAITING_FOR_RESOURCE: simulator assignment killed'
           WHERE id=? AND status='running' AND resource_id=?""",
        (task_id, failed_resource),
    ).rowcount
    if not changed:
        raise HTTPException(409, "Function assignment changed; refresh and retry")
    db.execute(
        """UPDATE sub_orders SET status='reserved',
             hold_reason='WAITING_FOR_RESOURCE: simulator assignment killed'
           WHERE id=?""",
        (task["sub_order_id"],),
    )
    import fulfillment_v2
    fulfillment_v2._update_parent(db, task["order_id"])
    event(
        db, now, failed_resource, "simulator_function_killed",
        {
            "task_id": task_id, "order_id": task["order_id"],
            "assignment_token": token, "reason": clean_reason,
            "automatic_replacement": True,
        },
    )
    append_event(
        db, task["order_id"],
        f"Simulator killed {task_id} on {failed_resource}; Core seeking automatic replacement",
        now,
    )
    replacement = fulfillment_v2.replace_queued_task(
        db, task_id, now, source_rows, append_event,
        excluded_resources={failed_resource},
    )
    current = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    replacement_status = "replaced" if replacement else "waiting"
    message = (
        f"Core replaced {failed_resource} with {replacement} for {current['stage']}."
        if replacement
        else f"{failed_resource} was blocked. Core is waiting for an eligible replacement."
    )
    response = {
        **_task_projection(db, current),
        "replacement_status": replacement_status,
        "message": message,
    }
    db.execute(
        """INSERT INTO lifecycle_simulator_failures(
             request_id,task_id,request_fingerprint,assignment_token,
             failed_resource_id,failed_resource_kind,failure_reason,failed_at,
             replacement_status,replacement_resource_id,response_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            request_id, task_id, fingerprint, token, failed_resource, failed_kind,
            clean_reason, at, replacement_status, replacement,
            json.dumps(response, sort_keys=True),
        ),
    )
    return response


def recover_resource(db, resource_id, now, append_event=None):
    ensure_schema(db)
    row = db.execute(
        "SELECT * FROM lifecycle_failed_resources WHERE resource_id=?",
        (resource_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Resource has no simulator failure record")
    if row["recovered_at"] is None:
        db.execute(
            "UPDATE lifecycle_failed_resources SET recovered_at=? WHERE resource_id=?",
            (stamp(now), resource_id),
        )
        event(db, now, resource_id, "simulator_resource_recovered", {})
        task = db.execute(
            "SELECT order_id FROM tasks WHERE id=?", (row["task_id"],)
        ).fetchone()
        if append_event is not None and task:
            append_event(
                db, task["order_id"],
                f"Core marked simulator-failed resource {resource_id} recovered",
                now,
            )
    return {"resource_id": resource_id, "resource_kind": row["resource_kind"], "status": "recovered"}


def fail_task(db, task_id, request_id, token, reason, now, append_event):
    """Atomically pause one exact running robot assignment via persona recovery."""
    ensure_schema(db)
    clean_reason = reason.strip()
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "task_id": task_id,
                "assignment_token": token,
                "reason": reason,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing = db.execute(
        "SELECT * FROM lifecycle_demo_failures WHERE request_id=?", (request_id,)
    ).fetchone()
    if existing:
        if existing["request_fingerprint"] != fingerprint:
            raise HTTPException(
                409, "request_id is already associated with a different failure payload"
            )
        if existing["response_json"]:
            return json.loads(existing["response_json"])
        task = db.execute("SELECT * FROM tasks WHERE id=?", (existing["task_id"],)).fetchone()
        return _task_projection(db, task, existing)

    task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise HTTPException(404, "Unknown lifecycle task")
    if task["status"] != "running":
        raise HTTPException(409, "Task is no longer running; refresh and retry")
    if task["resource_type"] != "robot" or not task["resource_id"]:
        raise HTTPException(409, "Only a currently running robot task can be failed")
    if assignment_token(task) != token:
        raise HTTPException(409, "Task assignment changed; refresh and retry")

    # Reuse the authoritative incident pause/recovery implementation.  The
    # explicit command is already fleet-authorized, so it records an approved
    # pause directly rather than fabricating source-health evidence.
    import persona_api

    at = stamp(now)
    intervention_id = f"INT-{uuid.uuid4()}"
    evidence = {
        "demo_failure": True,
        "provenance": "lifecycle_demo_override",
        "task_id": task_id,
        "order_id": task["order_id"],
        "resource_id": task["resource_id"],
        "assignment_token": token,
        "source_unchanged": True,
    }
    proposed = {
        "type": "pause_task",
        "task_id": task_id,
        "resource_id": task["resource_id"],
        "assigned_to": None,
        "remaining_seconds": 45,
        "source_unchanged": True,
        "approved": True,
        "demo_failure": True,
    }
    sub = db.execute(
        "SELECT warehouse_id FROM sub_orders WHERE id=?", (task["sub_order_id"],)
    ).fetchone()
    db.execute(
        """INSERT INTO persona_interventions(
             id,dedupe_key,kind,warehouse_id,entity_id,title,description,owner,status,
             evidence_json,proposed_action_json,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            intervention_id, None, "resource_failure", sub["warehouse_id"],
            task["resource_id"], f"Demo task failure: {task_id}", clean_reason,
            "fleet", "investigating", json.dumps(evidence, sort_keys=True),
            None, at, at,
        ),
    )
    incident = db.execute(
        "SELECT * FROM persona_interventions WHERE id=?", (intervention_id,)
    ).fetchone()
    persona_api._apply_approval(db, incident, proposed, intervention_id)
    db.execute(
        """INSERT INTO lifecycle_demo_failures(
             task_id,request_id,request_fingerprint,assignment_token,
             failed_resource_id,failure_reason,failed_at,intervention_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            task_id, request_id, fingerprint, token, task["resource_id"],
            clean_reason, at, intervention_id,
        ),
    )
    # Keep aggregate/sub-order truth held while preserving all stock accounting.
    db.execute(
        "UPDATE tasks SET wait_reason=? WHERE id=?",
        (f"DEMO_FAILURE: {clean_reason}", task_id),
    )
    db.execute(
        "UPDATE sub_orders SET status='recovery_required',hold_reason=? WHERE id=?",
        (f"DEMO_FAILURE: {clean_reason}", task["sub_order_id"]),
    )
    import fulfillment_v2
    fulfillment_v2._update_parent(db, task["order_id"])
    persona_api._add_event(
        db, incident, "fleet", "demo_failure", clean_reason,
        {"task_id": task_id, "order_id": task["order_id"], "source_unchanged": True},
    )
    event(
        db, now, task["resource_id"], "demo_task_failed",
        {
            "task_id": task_id, "order_id": task["order_id"],
            "intervention_id": intervention_id, "reason": clean_reason,
            "source_unchanged": True,
        },
    )
    append_event(
        db, task["order_id"],
        f"Demo failure paused {task_id} on {task['resource_id']}; recovery required: {clean_reason}",
        now,
    )
    response = _task_projection(
        db,
        db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone(),
        db.execute(
            """SELECT * FROM lifecycle_demo_failures
               WHERE task_id=? AND resolved_at IS NULL""",
            (task_id,),
        ).fetchone(),
    )
    db.execute(
        "UPDATE lifecycle_demo_failures SET response_json=? WHERE request_id=?",
        (json.dumps(response, sort_keys=True), request_id),
    )
    return response


def reconcile(db, now, source_rows):
    import persona_v2
    ensure_schema(db)
    at = stamp(now)
    maintenance = persona_v2.effective_source_rows(db, "maintenance", source_rows("maintenance"))
    claims = {}
    for row in db.execute("""SELECT id,resource_id,stage FROM tasks
                            WHERE status IN ('running','paused') AND resource_id IS NOT NULL ORDER BY id"""):
        claims[row["resource_id"]] = (row["id"], row["stage"])
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='task_resources'").fetchone():
        for row in db.execute("""SELECT t.id,tr.resource_id,t.stage FROM task_resources tr
                JOIN tasks t ON t.id=tr.task_id WHERE t.status IN ('pending','queued','running','paused')"""):
            claims[row["resource_id"]] = (row["id"], row["stage"])
    for dataset, kind, identity, type_field in (
        ("robots", "robot", "robot_id", "robot_type"),
        ("control_assets", "control_asset", "asset_id", "asset_type"),
    ):
        for resource in persona_v2.effective_source_rows(db, dataset, source_rows(dataset)):
            rid = resource.get(identity)
            if not rid:
                continue
            fit, reasons = (robot_readiness(resource, maintenance) if kind == "robot"
                            else asset_readiness(resource))
            old = db.execute("SELECT * FROM resource_lifecycle WHERE resource_id=?", (rid,)).fetchone()
            task, stage = claims.get(rid, (None, None))
            if old is None:
                battery = None
                if kind == "robot":
                    try:
                        value = float(resource.get("battery_soc"))
                        if math.isfinite(value) and 0 <= value <= 100:
                            battery = value
                    except (ValueError, TypeError):
                        pass
                charging = (
                    "Y"
                    if kind == "robot" and battery is not None
                    and battery < 10 and task is None
                    else "N"
                )
                db.execute("""INSERT INTO resource_lifecycle(resource_id,resource_kind,resource_type,
                    warehouse_id,fitness_status,fitness_reasons,charging,battery_pct,battery_at,
                    current_task_id,current_stage,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid, kind, resource.get(type_field), resource.get("warehouse_id"),
                     "Y" if fit else "N", json.dumps(reasons), charging, battery, at,
                     task, stage, at))
                event(db, now, rid, "registered", {"fitness_status": "Y" if fit else "N"})
                if charging == "Y":
                    event(db, now, rid, "charging_started", {"automatic": True})
                continue
            elapsed = max(0, (now - datetime.fromisoformat(old["battery_at"].replace("Z", "+00:00"))).total_seconds())
            battery = old["battery_pct"]
            if battery is not None:
                # A claim always wins over a stale persisted charging flag.
                # Normal assignment paths reconcile at acquisition time; this
                # also makes imported/legacy claims safe on their first pass.
                was_charging = old["charging"] == "Y" and task is None
                battery = max(
                    0, min(100, battery + elapsed * (5 / 60 if was_charging else -5 / 3600))
                )
            charging = old["charging"]
            if kind == "robot" and battery is not None:
                if task is not None or battery >= 100:
                    charging = "N"
                elif battery < 10:
                    charging = "Y"
            charging_changed = charging != old["charging"]
            changed = (old["fitness_status"] != ("Y" if fit else "N") or
                       old["fitness_reasons"] != json.dumps(reasons) or
                       old["current_task_id"] != task or old["current_stage"] != stage or
                       old["warehouse_id"] != resource.get("warehouse_id") or
                       old["resource_type"] != resource.get(type_field) or
                       charging_changed)
            if changed:
                event(db, now, rid, "state_changed", {"fitness_status": "Y" if fit else "N",
                                                      "current_task_id": task, "current_stage": stage,
                                                      "charging": charging})
            if charging_changed:
                event(
                    db, now, rid,
                    "charging_started" if charging == "Y" else "charging_stopped",
                    {
                        "automatic": True,
                        "reason": (
                            "low_battery"
                            if charging == "Y"
                            else "resource_claimed"
                            if task is not None
                            else "battery_full"
                        ),
                    },
                )
            db.execute("""UPDATE resource_lifecycle SET resource_type=?,warehouse_id=?,
                fitness_status=?,fitness_reasons=?,charging=?,battery_pct=?,battery_at=?,
                current_task_id=?,current_stage=?,updated_at=?,revision=revision+? WHERE resource_id=?""",
                (resource.get(type_field), resource.get("warehouse_id"), "Y" if fit else "N",
                 json.dumps(reasons), charging, battery,
                 at if elapsed > 0 else old["battery_at"],
                 task, stage, at if changed or elapsed > 0 else old["updated_at"], int(changed), rid))


def blockers(row):
    result = []
    if row["fitness_status"] != "Y":
        result.extend(json.loads(row["fitness_reasons"]))
    if row["current_task_id"]:
        result.append("Resource is already claimed")
    if row["charging"] == "Y":
        result.append("Resource is charging")
    if row["resource_kind"] == "robot":
        if row["battery_pct"] is None:
            result.append("Battery evidence is unknown")
        elif row["battery_pct"] <= 10:
            result.append("Battery must be strictly greater than 10%")
    return result


def snapshot(db, now):
    resources = []
    for row in db.execute("SELECT * FROM resource_lifecycle ORDER BY resource_id"):
        item = dict(row)
        item.pop("battery_at")
        item["fitness_reasons"] = json.loads(item["fitness_reasons"])
        item["Docked_for_charging"] = item["charging"]
        item["task_assigned"] = "Y" if item["current_task_id"] else "N"
        item["assignment_blockers"] = blockers(row)
        for table, field, extra, label in (
            ("persona_safety_holds", "robot_id", " AND released_at IS NULL", "Explicit safety hold is active"),
            ("persona_resource_blocks", "resource_id", "", "Explicit resource block is active"),
            ("lifecycle_failed_resources", "resource_id", " AND recovered_at IS NULL", "Simulator failure block is active"),
        ):
            if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                if db.execute(f"SELECT 1 FROM {table} WHERE {field}=?{extra}", (row["resource_id"],)).fetchone():
                    item["assignment_blockers"].append(label)
        resources.append(item)
    events = [dict(row) for row in db.execute("SELECT * FROM lifecycle_events ORDER BY id DESC LIMIT 200")]
    scheduler = dict(db.execute("SELECT last_assignment_at,next_assignment_at FROM lifecycle_scheduler WHERE id=1").fetchone())
    return {"resources": resources, "events": events, "scheduler": scheduler, "server_time": stamp(now)}


def set_charging(db, resource_id, charging, revision, now):
    row = db.execute("SELECT * FROM resource_lifecycle WHERE resource_id=?", (resource_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown lifecycle resource")
    if row["revision"] != revision:
        raise HTTPException(409, "Lifecycle revision is stale; refresh and retry")
    if row["resource_kind"] != "robot" or row["battery_pct"] is None:
        raise HTTPException(422, "Charging requires a robot with known battery evidence")
    if row["current_task_id"]:
        raise HTTPException(409, "A claimed resource cannot change charging state")
    db.execute("UPDATE resource_lifecycle SET charging=?,revision=revision+1,updated_at=? WHERE resource_id=?",
               ("Y" if charging else "N", stamp(now), resource_id))
    event(db, now, resource_id, "charging_started" if charging else "charging_stopped", {})


def assignment_due(db, now, force=False):
    ensure_schema(db)
    row = db.execute("SELECT * FROM lifecycle_scheduler WHERE id=1").fetchone()
    if row["last_observed_at"] and now < datetime.fromisoformat(row["last_observed_at"].replace("Z", "+00:00")):
        return False
    db.execute("UPDATE lifecycle_scheduler SET last_observed_at=? WHERE id=1", (stamp(now),))
    if row["last_assignment_at"] and now < datetime.fromisoformat(row["last_assignment_at"].replace("Z", "+00:00")):
        return False
    if not force and row["next_assignment_at"] and now < datetime.fromisoformat(row["next_assignment_at"].replace("Z", "+00:00")):
        return False
    db.execute("UPDATE lifecycle_scheduler SET last_assignment_at=?,next_assignment_at=? WHERE id=1",
               (stamp(now), stamp(now + timedelta(seconds=60))))
    return True