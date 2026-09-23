"""Deliberately simplistic legacy allocator.
It is runnable but embodies brownfield assumptions participants should challenge.
"""

def legacy_score(robot: dict, task: dict) -> float:
    # Ignores expired safety certification, maintenance, congestion and payload mismatch.
    battery = float(robot.get("battery_soc", 0))
    connectivity_bonus = 10.0 if robot.get("connectivity") == "ONLINE" else 0.0
    return battery + connectivity_bonus

def choose_robot(robots: list[dict], task: dict) -> dict | None:
    candidates = [r for r in robots if r.get("health_status") != "MAINTENANCE" and r.get("connectivity") != "OFFLINE"]
    return max(candidates, key=lambda r: legacy_score(r, task)) if candidates else None
