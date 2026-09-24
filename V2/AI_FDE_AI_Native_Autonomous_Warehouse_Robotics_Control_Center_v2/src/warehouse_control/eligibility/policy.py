"""Deterministic eligibility. Shadow notes and chat never grant a gate (G1–G4, G8)."""

INELIGIBLE_GATES = frozenset({"G1", "G2", "G3", "G4", "I2", "OFFLINE"})
OPEN_CMMS = frozenset({"OPEN", "IN_PROGRESS"})


def _norm(value) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _has_payload(task: dict) -> bool:
    if "payload_kg" not in task:
        return False
    raw = task.get("payload_kg")
    return raw is not None and str(raw).strip() != ""


def _safety_release_ok(context: dict) -> bool:
    """Structured SafetyOfficer record only. Email text is not Approval."""
    release = context.get("safety_release")
    if not isinstance(release, dict):
        return False
    role = _norm(release.get("role"))
    recorded = release.get("recorded")
    wo = release.get("work_order_id") or release.get("wo_id")
    return role == "SAFETYOFFICER" and bool(recorded) and bool(wo)


def evaluate_eligibility(robot: dict, task: dict, context=None) -> dict:
    context = dict(context or {})
    # Untrusted: never used as a waiver (EVAL-020).
    context.pop("shadow_note", None)

    gates_failed: list[str] = []
    conflicts: list[dict] = []
    uncertainty: list[str] = []
    evidence: list[dict] = []

    cert_raw = robot.get("safety_cert_status")
    cert = _norm(cert_raw)
    if cert_raw is None or cert == "" or cert == "EXPIRED":
        gates_failed.append("G1")

    rid = robot.get("robot_id")
    maint = list(context.get("maintenance_rows") or [])
    open_rows = [
        row
        for row in maint
        if row.get("robot_id") == rid and _norm(row.get("cmms_status")) in OPEN_CMMS
    ]
    if open_rows and not _safety_release_ok(context):
        gates_failed.append("G2")
        for row in open_rows:
            evidence.append(
                {
                    "source": "data/raw/maintenance.csv",
                    "id": row.get("wo_id") or row.get("work_order_id"),
                }
            )

    if _norm(robot.get("calibration_status")) == "OVERDUE":
        gates_failed.append("I2")

    conn = _norm(robot.get("connectivity"))
    if conn == "OFFLINE":
        gates_failed.append("OFFLINE")
    elif conn == "INTERMITTENT":
        uncertainty.append("CONNECTIVITY_INTERMITTENT")
        gates_failed.append("G8")

    if _has_payload(task):
        try:
            need = float(task["payload_kg"])
            have = float(robot.get("payload_kg") or 0)
            if have < need:
                gates_failed.append("G3")
        except (TypeError, ValueError):
            gates_failed.append("G8")
    else:
        gates_failed.append("G8")

    zone = context.get("zone") or {}
    if _norm(zone.get("robot_access")) == "RESTRICTED":
        gates_failed.append("G4")
    if _norm(zone.get("occupancy")) == "UNKNOWN":
        gates_failed.append("G4")

    blocked = task.get("blocked_zone")
    robot_zone = robot.get("zone") or task.get("target_zone")
    if blocked and robot_zone and str(blocked) == str(robot_zone):
        gates_failed.append("G4")

    robot_wh = robot.get("warehouse_id")
    task_wh = task.get("warehouse_id")
    if robot_wh and task_wh and robot_wh != task_wh:
        conflicts.append(
            {
                "kind": "SITE_MISMATCH",
                "robot_warehouse_id": robot_wh,
                "task_warehouse_id": task_wh,
            }
        )

    unique_gates = list(dict.fromkeys(gates_failed))
    hard = [g for g in unique_gates if g in INELIGIBLE_GATES]
    if hard:
        eligibility = "INELIGIBLE"
    elif "G8" in unique_gates:
        eligibility = "ABSTAIN"
    else:
        eligibility = "ELIGIBLE"

    return {
        "eligibility": eligibility,
        "gates_failed": unique_gates,
        "conflicts": conflicts,
        "uncertainty": uncertainty,
        "evidence": evidence,
    }
