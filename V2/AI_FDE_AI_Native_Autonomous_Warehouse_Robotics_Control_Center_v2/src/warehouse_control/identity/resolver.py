"""Alias resolution that reports collisions instead of collapsing them (I9)."""

from collections import defaultdict

from warehouse_control.repository import csv_rows

KNOWN_UNMATCHED_FLOOR_NAMES = frozenset({"AMR-044", "AMR044"})


def _alias_rows():
    return csv_rows("robot_aliases.csv")


def _index():
    by_robot = defaultdict(list)
    by_alias = defaultdict(list)
    for row in _alias_rows():
        by_robot[row["robot_id"]].append({"source": row["source"], "alias": row["alias"]})
        by_alias[row["alias"]].append(row["robot_id"])
    return by_robot, by_alias


def _collision_for_alias(alias: str, robot_ids: list[str]) -> dict | None:
    unique = sorted(set(robot_ids))
    if len(unique) <= 1:
        return None
    return {"kind": "IDENTITY_COLLISION", "alias": alias, "robot_ids": unique}


def resolve_robot(robot_id: str) -> dict:
    by_robot, by_alias = _index()
    aliases = list(by_robot.get(robot_id, []))
    conflicts = []
    seen = set()
    for item in aliases:
        alias = item["alias"]
        if alias in seen:
            continue
        seen.add(alias)
        collision = _collision_for_alias(alias, by_alias.get(alias, []))
        if collision:
            conflicts.append(collision)
    return {
        "robot_id": robot_id,
        "aliases": aliases,
        "conflicts": conflicts,
        "unmatched_floor_names": [],
    }


def resolve_alias(alias: str) -> dict:
    """Never coerce AMR-044 to RBT-0044. Return every robot_id that claims the alias."""
    if alias in KNOWN_UNMATCHED_FLOOR_NAMES:
        return {
            "alias": alias,
            "robot_ids": [],
            "conflicts": [],
            "uncertain": True,
            "unmatched": True,
        }
    _by_robot, by_alias = _index()
    robot_ids = sorted(set(by_alias.get(alias, [])))
    if not robot_ids:
        return {
            "alias": alias,
            "robot_ids": [],
            "conflicts": [],
            "uncertain": True,
            "unmatched": True,
        }
    collision = _collision_for_alias(alias, robot_ids)
    return {
        "alias": alias,
        "robot_ids": robot_ids,
        "conflicts": [collision] if collision else [],
        "uncertain": False,
        "unmatched": False,
    }
