"""Read-only access to a versioned, offline predictive-maintenance experiment.

No operational database, robot fitness rule, or scheduler is modified here.
Only trainer-produced JSON is served; the API never unpickles model artifacts.
"""
from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query

MODEL_DIR = Path(__file__).parent / "models" / "predictive-maintenance"
router = APIRouter(prefix="/api/predictive-maintenance", tags=["predictive-maintenance"])


def _authorize(role: str):
    # Matches the project's demo persona contract, not production authentication.
    if role not in {"fleet", "supervisor", "admin"}:
        raise HTTPException(403, "Fleet, supervisor or admin persona required")


@lru_cache(maxsize=2)
def _read_bundle(signature):
    summary_path, predictions_path, *_ = signature
    summary = json.loads(Path(summary_path).read_text())
    if not isinstance(summary, dict):
        raise ValueError("Invalid model summary")
    predictions_bytes = Path(predictions_path).read_bytes()
    if summary.get("predictions_sha256") and (
        hashlib.sha256(predictions_bytes).hexdigest() != summary["predictions_sha256"]
    ):
        raise ValueError("Predictions do not match the model summary")
    predictions = json.loads(predictions_bytes)
    if not isinstance(summary, dict) or not isinstance(predictions, list):
        raise ValueError("Invalid model snapshot format")
    date.fromisoformat(summary["data_end"])
    ids = set()
    for item in predictions:
        robot_id = item["robot_id"]
        if robot_id in ids:
            raise ValueError("Duplicate robot in model snapshot")
        ids.add(robot_id)
        probability = item["risk_probability"]
        if item["priority"] not in {"review", "monitor", "unavailable"}:
            raise ValueError("Unknown prediction priority")
        if probability is not None and (
            not isinstance(probability, (int, float))
            or not math.isfinite(probability) or not 0 <= probability <= 1
        ):
            raise ValueError("Invalid risk probability")
    predictions.sort(key=lambda row: (
        row["risk_probability"] is None,
        -(row["risk_probability"] or 0),
        row["robot_id"],
    ))
    return summary, predictions


def _bundle():
    summary = MODEL_DIR / "summary.json"
    predictions = MODEL_DIR / "predictions.json"
    try:
        stats = [p.stat() for p in (summary, predictions)]
        return _read_bundle((
            str(summary.resolve()), str(predictions.resolve()),
            *(value for stat in stats for value in (stat.st_mtime_ns, stat.st_size)),
        ))
    except FileNotFoundError:
        raise HTTPException(503, "No trained maintenance model is available yet") from None
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(503, "The maintenance model snapshot is invalid or unreadable") from exc


def _evaluation(summary):
    """Expose a small stable frontend contract, retaining full metrics in summary."""
    return summary.get("model_comparison", [])


@router.get("/model")
def model(x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")):
    _authorize(x_demo_persona)
    if not (MODEL_DIR / "summary.json").exists() and not (MODEL_DIR / "predictions.json").exists():
        return {
            "available": False, "message": "No trained maintenance model is available yet.",
            "evaluation": [], "warehouses": [],
            "counts": {"total": 0, "review": 0, "monitor": 0, "unavailable": 0},
            "freshness": {"snapshot_only": True, "days_since_observation": None, "stale": True},
        }
    summary, predictions = _bundle()
    elapsed = (datetime.now(timezone.utc).date() - date.fromisoformat(summary["data_end"])).days
    return {
        "available": True, "summary": summary, "evaluation": _evaluation(summary),
        "warehouses": sorted({p["warehouse_id"] for p in predictions}),
        "counts": {
            "total": len(predictions),
            **{key: sum(p["priority"] == key for p in predictions)
               for key in ("review", "monitor", "unavailable")},
        },
        "freshness": {
            "snapshot_only": True, "days_since_observation": max(0, elapsed),
            "stale": elapsed > 1,
        },
    }


@router.get("/predictions")
def predictions(
    warehouse: str = "", search: str = "", priority: str = "",
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona"),
):
    _authorize(x_demo_persona)
    if priority not in {"", "review", "monitor", "unavailable"}:
        raise HTTPException(422, "Unknown review priority")
    summary, rows = _bundle()
    needle = search.strip().casefold()
    selected = [
        row for row in rows
        if (not warehouse or row["warehouse_id"] == warehouse)
        and (not priority or row["priority"] == priority)
        and (not needle or any(needle in str(row[key]).casefold()
                              for key in ("robot_id", "robot_type", "vendor")))
    ]
    return {
        "items": [{k: v for k, v in row.items() if k not in {"history", "signals"}}
                  for row in selected[offset:offset + limit]],
        "total": len(selected), "limit": limit, "offset": offset,
        "model_id": summary["model_id"],
    }


@router.get("/robots/{robot_id}")
def robot(robot_id: str, x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")):
    _authorize(x_demo_persona)
    _, rows = _bundle()
    for row in rows:
        if row["robot_id"] == robot_id:
            return row
    raise HTTPException(404, "Robot not found in this observation snapshot")