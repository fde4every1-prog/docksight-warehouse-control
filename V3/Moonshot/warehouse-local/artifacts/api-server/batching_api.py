"""Read-only, detached what-if API. Never imports operational persistence."""
import copy
import hashlib
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from batching_scenario import scenario
from batching_engine import compare, enumerate_candidates, validate_plan

router = APIRouter(prefix="/api/batching", tags=["batching"])
_lock = threading.Lock()
_cache = {}
_failure_until = 0.0


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1, max_length=120)


class CompareInput(ScenarioInput):
    candidate_ids: list[str] = Field(max_length=20)


def checked_scenario(scenario_id):
    s = scenario()
    if scenario_id != s["scenario_id"]:
        raise HTTPException(409, "Scenario changed. Reload the scenario and generate suggestions again.")
    return s


def resolve_batches(s, ids, reasons=None):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Duplicate candidate IDs are not allowed.")
    candidates = {b["id"]: b for b in enumerate_candidates(s)["candidates"]}
    if any(i not in candidates for i in ids):
        raise HTTPException(422, "Unknown or infeasible candidate ID.")
    batches = [dict(candidates[i], reason=(reasons or {}).get(i, candidates[i].get("reason", ""))) for i in ids]
    verdict = validate_plan(s, {"scenario_id": s["scenario_id"], "batches": batches})
    if not verdict["valid"]:
        raise HTTPException(422, {"message": "Proposal rejected by deterministic validation.", "errors": verdict["errors"]})
    return batches


@router.get("/scenario")
def get_scenario():
    s = scenario()
    return {"scenario": s, **enumerate_candidates(s)}


@router.post("/compare")
def compare_plan(body: CompareInput):
    s = checked_scenario(body.scenario_id)
    batches = resolve_batches(s, body.candidate_ids)
    try:
        return compare(s, batches)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def request_llm(context):
    base = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
    key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
    if not base or not key:
        raise HTTPException(503, "AI integration is not configured. No AI suggestion was generated.")
    payload = {
        "model": "gpt-5.4-mini",
        "max_completion_tokens": 4096,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "You are a warehouse batching advisor for a detached synthetic sandbox, not a dispatcher. "
                "Review the full scenario, order lines, locations, stock, readiness, payloads, deadlines, "
                "and feasible candidates. Select a useful non-overlapping set of candidate IDs; prefer "
                "a feasible nearby three-order batch if available. Do not invent IDs. All unselected "
                "orders remain singleton. Candidate feasibility individually does not guarantee combined feasibility. "
                "Explain exclusions and recommendations based on the supplied evidence. Never claim observed savings. "
                "Timing is 45+22.5*(n-1) for EACH pick and move operation only, not a whole order. "
                "Return ONLY JSON with selected_candidate_ids: string[], reasons: "
                "[{candidate_id:string,reason:string}], summary:string, "
                "exclusions:[{order_ids:string[],reason:string}]."
            )},
            {"role": "user", "content": json.dumps(context, separators=(",", ":"))},
        ],
    }
    request = Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=75) as response:
            data = json.loads(response.read(250_000))
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Incomplete response")
        return json.loads(choice["message"]["content"])
    except HTTPError as exc:
        # Provider response bodies may contain request credentials; never forward them.
        raise HTTPException(502, f"AI provider could not generate suggestions (HTTP {exc.code}). Retry later; no fallback was substituted.") from None
    except (URLError, TimeoutError):
        raise HTTPException(504, "AI request timed out or is unavailable. Retry; no fallback was substituted.") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, "AI returned an incomplete or malformed response. Retry; no fallback was substituted.") from None


def validate_llm(s, output):
    """Validate model shape before ever handing it to the deterministic engine."""
    if not isinstance(output, dict):
        raise ValueError("Expected a JSON object")
    ids = output.get("selected_candidate_ids")
    if not isinstance(ids, list) or len(ids) > 20 or any(not isinstance(i, str) for i in ids):
        raise ValueError("Invalid candidate membership")
    summary = output.get("summary")
    if not isinstance(summary, str) or not 1 <= len(summary) <= 5000:
        raise ValueError("Missing or excessive summary")
    reasons = output.get("reasons")
    if not isinstance(reasons, list) or len(reasons) != len(ids):
        raise ValueError("Each recommendation needs one reason")
    by_id = {}
    for r in reasons:
        if not isinstance(r, dict) or r.get("candidate_id") not in ids:
            raise ValueError("Unknown reason membership")
        ident = r["candidate_id"]
        if ident in by_id or not isinstance(r.get("reason"), str) or not 1 <= len(r["reason"]) <= 3000:
            raise ValueError("Invalid or duplicate reason")
        by_id[ident] = r["reason"]
    exclusions = output.get("exclusions")
    if not isinstance(exclusions, list) or len(exclusions) > 30:
        raise ValueError("Invalid exclusions")
    order_ids = {o["id"] for o in s["orders"]}
    for e in exclusions:
        if not isinstance(e, dict) or not isinstance(e.get("order_ids"), list) or not e["order_ids"]:
            raise ValueError("Exclusions must identify orders")
        if any(not isinstance(i, str) or i not in order_ids for i in e["order_ids"]):
            raise ValueError("Unknown excluded order")
        if not isinstance(e.get("reason"), str) or not 1 <= len(e["reason"]) <= 3000:
            raise ValueError("Invalid exclusion reason")
    batches = resolve_batches(s, ids, by_id)
    return {"scenario_id": s["scenario_id"], "batches": batches,
            "selected_candidate_ids": ids, "summary": summary,
            "exclusions": exclusions, "source": "llm", "cached": False}


@router.post("/suggest")
def suggest_plan(body: ScenarioInput):
    global _failure_until
    s = checked_scenario(body.scenario_id)
    context = {"scenario": s, **enumerate_candidates(s)}
    cache_key = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    # Single-flight requests and bounded cache limit accidental duplicate model spending.
    if not _lock.acquire(blocking=False):
        raise HTTPException(429, "A suggestion is already being generated. Please retry shortly.")
    try:
        if cache_key in _cache:
            return {**copy.deepcopy(_cache[cache_key]), "cached": True}
        if time.monotonic() < _failure_until:
            raise HTTPException(429, "Please wait a few seconds before retrying the AI request.")
        try:
            result = validate_llm(s, request_llm(context))
        except ValueError as exc:
            _failure_until = time.monotonic() + 5
            raise HTTPException(502, f"AI proposal rejected: {exc}. Retry; no fallback was substituted.") from None
        except HTTPException:
            _failure_until = time.monotonic() + 5
            raise
        _cache.clear()
        _cache[cache_key] = copy.deepcopy(result)
        return result
    finally:
        _lock.release()