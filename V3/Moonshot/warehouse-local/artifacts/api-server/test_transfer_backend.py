import copy
import io
import inspect
import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

import pytest
from openpyxl import Workbook

import transfer_api
from transfer_engine import baseline_plan, compare, validate_plan
from transfer_import import WorkbookError, normalize, parse_xlsx, template_bytes
from transfer_snapshot import create_snapshot


def workbook(rows, headers=("Order ID", "SKU", "Qty", "Order Cut-off")):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


@pytest.fixture
def live():
    return create_snapshot()


def test_live_snapshot_has_exact_scene_and_frozen_evidence(live):
    assert live["mode"] == "live"
    assert [z["id"] for z in live["map"]["zones"]] == [f"DC-01-Z{i:02d}" for i in range(1, 13)]
    assert live["selected_robot_ids"] == sorted(r["id"] for r in live["robots"] if r["eligible"])
    assert len(live["map"]["conveyor"]) == 3
    assert live["clock"]["timezone"] == "UTC"
    assert all(row["quantity_semantics"] == "free_net_of_reservations" for row in live["inventory"])
    assert all(robot["battery_at"] for robot in live["robots"])
    import transfer_snapshot
    source = inspect.getsource(transfer_snapshot)
    assert "\nimport fulfillment_api" not in source
    assert "\nfrom fulfillment_api" not in source
    assert "source_rows(" not in source
    assert "ensure_schema" not in source


def test_template_uses_real_stock_and_explicit_cutoffs(live):
    raw = parse_xlsx(template_bytes(live))
    assert raw
    assert all(row["sku"].startswith("SKU-") for row in raw)
    rows, blockers = normalize(raw, live)
    assert blockers == []
    assert all(row["order_cutoff"].endswith("Z") for row in rows)
    assert all(row["allocations"][0]["inventory_source_id"].startswith("inventory_snapshot:") for row in rows)
    max_transfer = max(
        robot["capacity_kg"] for robot in live["robots"]
        if robot["id"] in live["selected_robot_ids"] and robot["eligible"]
        and "transfer" in robot["capabilities"]
    )
    assert sum(row["total_weight_kg"] for row in rows) <= max_transfer


def test_xlsx_bounds_headers_quantities_duplicates_and_timezone(live):
    with pytest.raises(WorkbookError) as exc:
        parse_xlsx(workbook([["O", "S", 1, "x"]], headers=("bad", "SKU", "Qty", "Order Cut-off")))
    assert exc.value.code == "INVALID_HEADERS"
    sku = next(row["sku"] for row in live["inventory"] if row["available_unreserved_qty"] > 2 and row["weight_kg"])
    future = datetime.fromisoformat(live["clock"]["at"].replace("Z", "+00:00")) + timedelta(hours=1)
    raw = parse_xlsx(workbook([["O1", sku, 1.2, future.replace(tzinfo=None)],
                               ["O1", sku, 1, future.isoformat()]]))
    rows, _ = normalize(raw, live)
    codes = {e["code"] for row in rows for e in row["errors"]}
    assert {"INVALID_QUANTITY", "INVALID_CUTOFF", "DUPLICATE_LINE"} <= codes


def test_missing_group_and_cutoff_are_explicitly_repairable(live):
    sku = next(row["sku"] for row in live["inventory"] if row["available_unreserved_qty"] and row["weight_kg"])
    rows, blockers = normalize(parse_xlsx(workbook([[None, sku, 1, None]])), live)
    assert {"MISSING_ORDER_ID", "MISSING_CUTOFF"} == {e["code"] for e in rows[0]["errors"]}
    assert blockers


def test_multi_line_multi_bin_coverage_and_exact_sequence(live):
    candidates = {}
    for stock in live["inventory"]:
        if stock["available_unreserved_qty"] and stock["weight_kg"]:
            candidates.setdefault(stock["sku"], []).append(stock)
    sku = next(key for key, values in candidates.items() if len(values) >= 1)
    stock = candidates[sku][0]
    # Force a deterministic split without touching operational evidence.
    frozen = copy.deepcopy(live)
    matching = [r for r in frozen["inventory"] if r["sku"] == sku]
    matching[0]["available_unreserved_qty"] = 1
    extra = copy.deepcopy(matching[0])
    extra["id"] = 999999
    extra["source_id"] = "inventory_snapshot:999999"
    extra["location"] = extra["location"] + "-SPLIT"
    extra["available_unreserved_qty"] = 2
    frozen["inventory"].append(extra)
    future = datetime.fromisoformat(frozen["clock"]["at"].replace("Z", "+00:00")) + timedelta(hours=2)
    raw = parse_xlsx(workbook([["O1", sku, 3, future.isoformat()]]))
    rows, blockers = normalize(raw, frozen)
    assert not blockers and len(rows[0]["allocations"]) == 2
    scenario = {"rows": rows, "map": frozen["map"], "robots": frozen["robots"],
                "selected_robot_ids": frozen["selected_robot_ids"], "clock": frozen["clock"]}
    plan = baseline_plan(scenario)
    assert validate_plan(scenario, plan)["valid"]
    plan["batches"][0]["stops"][0]["quantity"] += 1
    verdict = validate_plan(scenario, plan)
    assert not verdict["valid"]
    assert any(e["code"] in {"QUANTITY_COVERAGE", "CONCURRENT_STOCK_CLAIMS"} for e in verdict["errors"])

def test_pick_bin_id_must_exactly_match_frozen_allocation(live):
    scenario = _review_from_template(live)
    plan = baseline_plan(scenario)
    pick = next(stop for stop in plan["batches"][0]["stops"] if stop["action"] == "pick")
    pick["bin_id"] += "-WRONG"
    verdict = validate_plan(scenario, plan)
    assert any(error["code"] == "FROZEN_ALLOCATION_MISMATCH" for error in verdict["errors"])


def test_batch_requires_same_dual_capability_robot_and_capacity(live):
    rows, blockers = normalize(parse_xlsx(template_bytes(live)), live)
    assert not blockers
    scenario = {"rows": rows, "map": live["map"], "robots": live["robots"],
                "selected_robot_ids": live["selected_robot_ids"], "clock": live["clock"]}
    plan = baseline_plan(scenario)
    batch = plan["batches"][0]
    transfer = batch["stops"][-1]
    assert batch["pick_robot_ids"] == [batch["transfer_robot_id"]]
    assert transfer["donor_robot_id"] is None
    robot = next(r for r in scenario["robots"] if r["id"] == batch["transfer_robot_id"])
    robot["capacity_kg"] = 0
    errors = validate_plan(scenario, plan)["errors"]
    assert any(e["code"] == "TRANSFER_CAPACITY" for e in errors)
    assert any(e["code"] == "CUMULATIVE_PICK_CAPACITY" for e in errors)


def test_consistent_baseline_and_sequence_driven_comparison(live):
    rows, blockers = normalize(parse_xlsx(template_bytes(live)), live)
    assert not blockers
    scenario = {"rows": rows, "map": live["map"], "robots": live["robots"],
                "selected_robot_ids": live["selected_robot_ids"], "clock": live["clock"]}
    plan = baseline_plan(scenario)
    first = compare(scenario, plan)
    second = compare(scenario, plan)
    assert first == second
    assert [e["event_id"] for e in first["proposed"]["timeline"]] == [
        f"EV-{i}" for i in range(1, len(first["proposed"]["timeline"]) + 1)
    ]
    assert len(first["proposed"]["metrics"]["robot_utilization"]) == len(live["selected_robot_ids"])


def _review_from_template(live):
    rows, blockers = normalize(parse_xlsx(template_bytes(live)), live)
    assert not blockers
    return {"rows": rows, "map": live["map"], "robots": copy.deepcopy(live["robots"]),
            "selected_robot_ids": live["selected_robot_ids"], "clock": live["clock"]}


def test_cumulative_pick_capacity_not_only_each_stop(live):
    scenario = _review_from_template(live)
    plan = baseline_plan(scenario)
    batch = plan["batches"][0]
    picker_id = batch["pick_robot_ids"][0]
    picks = [stop for stop in batch["stops"] if stop["action"] == "pick"]
    # Duplicate a real allocation as a second line so each pick fits but the carried sum does not.
    if len(picks) == 1:
        line = next(row for row in scenario["rows"] if row["row_id"] == picks[0]["line_id"])
        clone = copy.deepcopy(line)
        clone["row_id"] += "-SECOND"
        clone["sku"] += "-SECOND"
        clone["allocations"][0]["inventory_source_id"] += "-SECOND"
        scenario["rows"].append(clone)
        second = copy.deepcopy(picks[0])
        second["line_id"] = clone["row_id"]
        second["inventory_source_id"] = clone["allocations"][0]["inventory_source_id"]
        batch["stops"].insert(1, second)
        for number, stop in enumerate(batch["stops"], 1):
            stop["sequence"] = number
    pick_weights = [
        stop["quantity"] * next(row["unit_weight_kg"] for row in scenario["rows"] if row["row_id"] == stop["line_id"])
        for stop in batch["stops"] if stop["action"] == "pick"
    ]
    robot = next(r for r in scenario["robots"] if r["id"] == picker_id)
    robot["capacity_kg"] = max(pick_weights) + 0.1
    verdict = validate_plan(scenario, plan)
    assert any(error["code"] == "CUMULATIVE_PICK_CAPACITY" for error in verdict["errors"])


def test_split_robot_plan_is_rejected_and_donor_must_be_null(live):
    scenario = _review_from_template(live)
    selected = [r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"]]
    plan = baseline_plan(scenario)
    batch = plan["batches"][0]
    transfer = next(s for s in batch["stops"] if s["action"] == "transfer")
    other = next(r for r in selected if r["id"] != batch["transfer_robot_id"])
    other["capabilities"] = ["pick", "transfer"]
    transfer["robot_id"] = other["id"]
    batch["transfer_robot_id"] = other["id"]
    transfer["donor_robot_id"] = batch["pick_robot_ids"][0]
    errors = validate_plan(scenario, plan)["errors"]
    assert any(e["code"] == "SPLIT_ROBOT_ASSIGNMENT" for e in errors)
    assert any(e["code"] == "TRANSFER_DONOR" for e in errors)


def test_disjoint_capability_fleet_excludes_all_orders(live):
    scenario = _review_from_template(live)
    selected = [r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"]]
    for robot in selected:
        robot["capacity_kg"] = 100000
        robot["capabilities"] = []
    selected[0]["capabilities"] = ["pick"]
    selected[1]["capabilities"] = ["transfer"]

    plan = baseline_plan(scenario)
    assert plan["batches"] == []
    assert len(plan["excluded_orders"]) == len({row["order_id"] for row in scenario["rows"]})
    assert validate_plan(scenario, plan, check_deadlines=False)["valid"]


def test_transfer_route_consumes_service_time_to_conveyor(live):
    scenario = _review_from_template(live)
    plan = baseline_plan(scenario)
    run = compare(scenario, plan)["proposed"]
    for event in (e for e in run["timeline"] if e["action"] == "transfer"):
        assert event["node_id"] == "CONVEYOR"
        assert event["path"][-1] == "CONVEYOR"
        assert event["duration"] >= 45
    assert not any(e["action"] in {"handoff", "deliver"} for e in run["timeline"])


def test_independent_robot_transfer_phases_overlap_without_conveyor_bottleneck():
    snapshot = create_snapshot("synthetic_demo")
    scenario = _review_from_template(snapshot)
    selected = [r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"]]
    for robot in selected:
        robot["capabilities"] = []
        robot["capacity_kg"] = 1000
    selected[0]["capabilities"] = ["pick", "transfer"]
    selected[1]["capabilities"] = ["pick", "transfer"]

    run = compare(scenario, baseline_plan(scenario))["proposed"]
    transfers = [event for event in run["timeline"] if event["action"] == "transfer"]
    assert len(transfers) >= 2
    assert transfers[0]["start"] < transfers[1]["end"]
    assert transfers[1]["start"] < transfers[0]["end"]


def test_execution_order_is_unique_and_batch_first_starts_monotonic(live):
    scenario = _review_from_template(live)
    plan = baseline_plan(scenario)
    plan["batches"][1]["execution_order"] = plan["batches"][0]["execution_order"]
    verdict = validate_plan(scenario, plan)
    assert any(e["code"] == "EXECUTION_ORDER_COVERAGE" for e in verdict["errors"])
    plan = baseline_plan(scenario)
    run = compare(scenario, plan)["proposed"]
    first_starts = []
    for batch in sorted(plan["batches"], key=lambda b: b["execution_order"]):
        first_starts.append(min(e["start"] for e in run["timeline"] if e["batch_id"] == batch["batch_id"]))
    assert first_starts == sorted(first_starts)


def test_baseline_uses_earliest_free_then_smallest_sufficient(live):
    scenario = _review_from_template(live)
    selected = [r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"]]
    maximum = max(row["total_weight_kg"] for row in scenario["rows"])
    for robot in selected:
        robot["capabilities"] = []
    selected[0]["capabilities"] = ["pick", "transfer"]
    selected[0]["capacity_kg"] = maximum + 10
    selected[1]["capabilities"] = ["pick", "transfer"]
    selected[1]["capacity_kg"] = maximum + 100
    plan = baseline_plan(scenario)
    assert plan["batches"][0]["transfer_robot_id"] == selected[0]["id"]
    # The smaller robot is now busy, so the next singleton goes to the free robot.
    assert plan["batches"][1]["transfer_robot_id"] == selected[1]["id"]


def test_baseline_four_orders_use_distinct_dual_robots_for_simultaneous_full_trips():
    scenario = _review_from_template(create_snapshot("synthetic_demo"))
    order_ids = list(dict.fromkeys(row["order_id"] for row in scenario["rows"]))
    fourth = copy.deepcopy(scenario["rows"][0])
    fourth["row_id"] += "-FOURTH"
    fourth["order_id"] = "EXAMPLE-04"
    fourth["allocations"][0]["inventory_source_id"] += "-FOURTH"
    scenario["rows"].append(fourth)
    order_ids.append(fourth["order_id"])
    assert len(order_ids) == 4

    plan = baseline_plan(scenario)
    first_four = plan["batches"][:4]
    assigned = [batch["transfer_robot_id"] for batch in first_four]
    assert len(set(assigned)) == 4
    assert all(batch["pick_robot_ids"] == [batch["transfer_robot_id"]] for batch in first_four)
    assert all(
        [stop["action"] for stop in batch["stops"]]
        == ["pick"] * (len(batch["stops"]) - 1) + ["transfer"]
        for batch in first_four
    )

    run = compare(scenario, plan)["proposed"]
    assert [
        min(event["start"] for event in run["timeline"] if event["batch_id"] == batch["batch_id"])
        for batch in first_four
    ] == [0.0] * 4


def test_baseline_requires_dual_robot_over_free_specialist_pair(live):
    scenario = _review_from_template(live)
    scenario["rows"] = [
        row for row in scenario["rows"]
        if row["order_id"] == scenario["rows"][0]["order_id"]
    ]
    selected = [r for r in scenario["robots"] if r["id"] in scenario["selected_robot_ids"]]
    maximum = sum(row["total_weight_kg"] for row in scenario["rows"])
    for robot in selected:
        robot["capabilities"] = []
        robot["capacity_kg"] = maximum + 100
    selected[0]["capabilities"] = ["pick"]
    selected[1]["capabilities"] = ["transfer"]
    selected[2]["capabilities"] = ["pick", "transfer"]

    batch = baseline_plan(scenario)["batches"][0]
    assert batch["pick_robot_ids"] == [selected[2]["id"]]
    assert batch["transfer_robot_id"] == selected[2]["id"]
    assert batch["stops"][-1]["donor_robot_id"] is None


def test_multi_order_batch_is_one_sequential_collection_trip_then_transfer():
    scenario = _review_from_template(create_snapshot("synthetic_demo"))
    singleton = baseline_plan(scenario)
    first, second = singleton["batches"][:2]
    robot_id = first["transfer_robot_id"]
    order_ids = first["order_ids"] + second["order_ids"]
    picks = [
        copy.deepcopy(stop)
        for batch in (first, second)
        for stop in batch["stops"]
        if stop["action"] == "pick"
    ]
    for stop in picks:
        stop["robot_id"] = robot_id
    transfer = copy.deepcopy(first["stops"][-1])
    transfer["robot_id"] = robot_id
    transfer["donor_robot_id"] = None
    stops = picks + [transfer]
    for sequence, stop in enumerate(stops, 1):
        stop["sequence"] = sequence
    combined = {
        "batch_id": "BATCH-FIRST-TWO",
        "order_ids": order_ids,
        "transfer_robot_id": robot_id,
        "pick_robot_ids": [robot_id],
        "execution_order": 1,
        "order_sequence": order_ids,
        "stops": stops,
        "rationale": "One sequential collection trip.",
    }
    remainder = copy.deepcopy(singleton["batches"][2:])
    for execution_order, batch in enumerate(remainder, 2):
        batch["execution_order"] = execution_order
    plan = {
        "batches": [combined] + remainder,
        "excluded_orders": singleton["excluded_orders"],
    }

    assert validate_plan(scenario, plan)["valid"]
    events = [
        event for event in compare(scenario, plan)["proposed"]["timeline"]
        if event["batch_id"] == combined["batch_id"]
    ]
    assert [event["action"] for event in events] == ["pick"] * len(picks) + ["transfer"]
    assert all(after["start"] == before["end"] for before, after in zip(events, events[1:]))
    assert {event["robot_id"] for event in events} == {robot_id}
    assert all(event["duration"] == 7 for event in events if event["action"] == "pick")


@pytest.mark.parametrize("field,value", [
    ("batch_id", []), ("order_ids", [["nested"]]), ("transfer_robot_id", []),
    ("pick_robot_ids", [["nested"]]), ("order_sequence", [["nested"]]),
])
def test_structural_fuzz_returns_validation_errors_not_type_errors(live, field, value):
    scenario = _review_from_template(live)
    plan = baseline_plan(scenario)
    plan["batches"][0][field] = value
    verdict = validate_plan(scenario, plan)
    assert verdict["valid"] is False
    assert verdict["errors"]


def test_capacity_feasible_workload_cannot_be_excluded(live):
    scenario = _review_from_template(live)
    plan = baseline_plan(scenario)
    removed = plan["batches"].pop()
    plan["excluded_orders"].append({"order_id": removed["order_ids"][0], "reason": "Explicit model exclusion"})
    for number, batch in enumerate(plan["batches"], 1):
        batch["execution_order"] = number
    verdict = validate_plan(scenario, plan)
    assert any(error["code"] == "UNJUSTIFIED_EXCLUSION" for error in verdict["errors"])


def test_capacity_feasible_but_standalone_deadline_impossible_may_be_excluded(live):
    scenario = _review_from_template(live)
    plan = baseline_plan(scenario)
    removed = plan["batches"].pop(0)
    oid = removed["order_ids"][0]
    clock = datetime.fromisoformat(scenario["clock"]["at"].replace("Z", "+00:00"))
    pick_count = sum(
        len(row["allocations"]) for row in scenario["rows"] if row["order_id"] == oid
    )
    impossible_cutoff = clock + timedelta(seconds=pick_count * 7 + 44)
    for row in scenario["rows"]:
        if row["order_id"] == oid:
            row["order_cutoff"] = impossible_cutoff.isoformat().replace("+00:00", "Z")
    plan["excluded_orders"].append(
        {"order_id": oid, "reason": "Cannot meet cut-off even standalone."}
    )
    for number, batch in enumerate(plan["batches"], 1):
        batch["execution_order"] = number
    verdict = validate_plan(scenario, plan, check_deadlines=False)
    assert verdict["valid"]


def test_api_compare_handles_early_overweight_then_later_feasible_orders(live):
    rows, blockers = normalize(parse_xlsx(template_bytes(live)), live)
    assert not blockers and len(rows) >= 2
    rows = copy.deepcopy(rows)
    max_capacity = max(
        robot["capacity_kg"] for robot in live["robots"]
        if robot["id"] in live["selected_robot_ids"] and robot["eligible"]
        and "transfer" in robot["capabilities"]
    )
    # The first (earliest-cutoff) order cannot run; later orders remain feasible.
    rows[0]["unit_weight_kg"] = max_capacity + 1
    rows[0]["total_weight_kg"] = max_capacity + 1
    planning = {"rows": rows, "map": live["map"], "robots": live["robots"],
                "selected_robot_ids": live["selected_robot_ids"], "clock": live["clock"]}
    plan = baseline_plan(planning)
    assert plan["excluded_orders"][0]["order_id"] == rows[0]["order_id"]
    assert [batch["execution_order"] for batch in plan["batches"]] == list(range(1, len(plan["batches"]) + 1))
    assert validate_plan(planning, plan)["valid"]

    recommendation_id = "REC-OVERWEIGHT"
    scenario = {
        "scenario_id": "TEST-OVERWEIGHT", "snapshot": live, "revision": 1,
        "raw_rows": [], "rows": rows, "row_blockers": [],
        "selected_robot_ids": live["selected_robot_ids"],
        "recommendations": {"test": {
            "recommendation_id": recommendation_id, "scenario_id": "TEST-OVERWEIGHT",
            "revision": 1, "source": "llm", "summary": "Valid exclusion",
            "plan": plan, "validation": {"valid": True, "errors": []},
        }},
    }
    transfer_api._put(scenario)
    response = transfer_api.compare_runs(
        "TEST-OVERWEIGHT",
        transfer_api.CompareBody(revision=1, recommendation_id=recommendation_id),
    )
    assert response["proposed"]["metrics"]["excluded_order_count"] == 1
    assert response["proposed"]["metrics"]["completed_order_count"] == len(rows) - 1


def test_api_compare_converts_simulation_value_error_to_422(live, monkeypatch):
    rows, blockers = normalize(parse_xlsx(template_bytes(live)), live)
    assert not blockers
    planning = {"rows": rows, "map": live["map"], "robots": live["robots"],
                "selected_robot_ids": live["selected_robot_ids"], "clock": live["clock"]}
    plan = baseline_plan(planning)
    scenario = {
        "scenario_id": "TEST-SIM-ERROR", "snapshot": live, "revision": 1,
        "raw_rows": [], "rows": rows, "row_blockers": [],
        "selected_robot_ids": live["selected_robot_ids"],
        "recommendations": {"test": {
            "recommendation_id": "REC-SIM-ERROR", "scenario_id": "TEST-SIM-ERROR",
            "revision": 1, "source": "llm", "summary": "test", "plan": plan,
            "validation": {"valid": True, "errors": []},
        }},
    }
    transfer_api._put(scenario)
    monkeypatch.setattr(transfer_api, "compare", lambda *_: (_ for _ in ()).throw(ValueError("safe failure")))
    with pytest.raises(Exception) as exc:
        transfer_api.compare_runs(
            "TEST-SIM-ERROR",
            transfer_api.CompareBody(revision=1, recommendation_id="REC-SIM-ERROR"),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "SIMULATION_REJECTED"


def test_api_import_review_patch_and_server_authority(live):
    sku = next(row["sku"] for row in live["inventory"] if row["available_unreserved_qty"] and row["weight_kg"])
    raw = parse_xlsx(workbook([[None, sku, 1, None]]))
    rows, blockers = normalize(raw, live)
    scenario = {"scenario_id": "TEST-REPAIR", "snapshot": live, "revision": 1, "raw_rows": raw,
                "rows": rows, "row_blockers": blockers, "selected_robot_ids": live["selected_robot_ids"],
                "recommendations": {}}
    transfer_api._put(scenario)
    review = transfer_api.get_scenario("TEST-REPAIR")
    assert not review["ready_for_planning"]
    cutoff = datetime.fromisoformat(live["clock"]["at"].replace("Z", "+00:00")) + timedelta(hours=1)
    repaired = transfer_api.patch_rows("TEST-REPAIR", transfer_api.ReviewPatch(
        revision=1, rows=[transfer_api.RowPatch(row_id=review["rows"][0]["row_id"],
                                                order_id="ORDER-1", order_cutoff=cutoff.isoformat())]))
    assert repaired["ready_for_planning"]
    with pytest.raises(Exception) as stale:
        transfer_api.patch_rows("TEST-REPAIR", transfer_api.ReviewPatch(revision=1))
    assert stale.value.status_code == 409


def test_server_owned_robot_selection_rejects_any_subset(live):
    raw = parse_xlsx(template_bytes(live))
    rows, blockers = normalize(raw, live)
    assert not blockers
    scenario = {"scenario_id": "TEST-FLEET", "snapshot": live, "revision": 1, "raw_rows": raw,
                "rows": rows, "row_blockers": blockers, "selected_robot_ids": live["selected_robot_ids"],
                "recommendations": {}}
    transfer_api._put(scenario)
    with pytest.raises(Exception) as rejected:
        transfer_api.patch_rows("TEST-FLEET", transfer_api.ReviewPatch(
            revision=1, selected_robot_ids=live["selected_robot_ids"][:-1]))
    assert rejected.value.status_code == 422


class _ProviderResponse:
    def __init__(self, output, finish_reason="stop"):
        self.body = json.dumps({"choices": [{
            "finish_reason": finish_reason,
            "message": {"content": json.dumps(output)},
        }]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return self.body


def test_llm_provider_retries_transient_failure_and_requests_strict_schema(monkeypatch):
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_API_KEY", "test-key")
    calls = []
    responses = [
        URLError("temporary"),
        HTTPError("https://provider.test", 503, "busy", {}, None),
        _ProviderResponse({"summary": "provider result", "plan": {}}),
    ]

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(transfer_api, "urlopen", fake_urlopen)
    monkeypatch.setattr(transfer_api.time, "sleep", lambda _seconds: None)
    trace = {"attempts": 0}
    result = transfer_api._request_llm({"scenario_id": "S"}, provider_trace=trace)

    assert result["summary"] == "provider result"
    assert trace["attempts"] == 3
    assert len(calls) == 3
    payload = json.loads(calls[0][0].data)
    prompt = payload["messages"][0]["content"]
    assert "Avoid singleton orders unless necessary" in prompt
    assert "For EVERY remaining singleton" in prompt
    assert "never force an infeasible batch or omit an order" in prompt
    payload = json.loads(calls[-1][0].data)
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_llm_provider_does_not_retry_nontransient_or_malformed_output(monkeypatch):
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_API_KEY", "test-key")
    calls = []

    def unauthorized(*_args, **_kwargs):
        calls.append("unauthorized")
        raise HTTPError("https://provider.test", 401, "unauthorized", {}, None)

    monkeypatch.setattr(transfer_api, "urlopen", unauthorized)
    with pytest.raises(Exception) as failed:
        transfer_api._request_llm({"scenario_id": "S"})
    assert failed.value.status_code == 502
    assert failed.value.detail["code"] == "AI_PROVIDER_ERROR"
    assert failed.value.detail["request_provenance"]["provider_attempts"] == 1
    assert calls == ["unauthorized"]

    calls.clear()
    monkeypatch.setattr(
        transfer_api,
        "urlopen",
        lambda *_args, **_kwargs: (
            calls.append("malformed") or _ProviderResponse({"summary": "missing plan"})
        ),
    )
    with pytest.raises(Exception) as malformed:
        transfer_api._request_llm({"scenario_id": "S"})
    assert malformed.value.detail["code"] == "AI_MALFORMED_STRUCTURED_OUTPUT"
    assert calls == ["malformed"]


def test_suggest_repairs_validation_failure_without_heuristic_fallback(live, monkeypatch):
    raw = parse_xlsx(template_bytes(live))
    rows, blockers = normalize(raw, live)
    assert not blockers
    planning = {"rows": rows, "map": live["map"], "robots": live["robots"],
                "selected_robot_ids": live["selected_robot_ids"], "clock": live["clock"]}
    valid_plan = baseline_plan(planning)
    invalid_plan = copy.deepcopy(valid_plan)
    invalid_plan["batches"][0]["stops"][0]["quantity"] += 1
    responses = [
        {"summary": "first model proposal", "plan": invalid_plan},
        {"summary": "repaired model proposal", "plan": valid_plan},
    ]
    seen_repairs = []

    def fake_request(_context, repair_errors=None, previous_plan=None, provider_trace=None):
        if provider_trace is not None:
            provider_trace["attempts"] += 1
        seen_repairs.append((repair_errors, previous_plan))
        return responses.pop(0)

    scenario_id = "TEST-LLM-REPAIR"
    transfer_api._put({
        "scenario_id": scenario_id, "snapshot": live, "revision": 1,
        "raw_rows": raw, "rows": rows, "row_blockers": [],
        "selected_robot_ids": live["selected_robot_ids"], "recommendations": {},
    })
    monkeypatch.setattr(transfer_api, "_request_llm", fake_request)

    result = transfer_api.suggest(scenario_id, transfer_api.RevisionBody(revision=1))

    assert result["plan"] == valid_plan
    assert result["validation"]["valid"]
    assert result["source"] == "llm"
    assert result["request_provenance"] == {
        "planning_attempts": 2,
        "provider_attempts": 2,
        "repair_attempted": True,
        "repair_reason": "validation",
        "repair_accepted": True,
        "fallback_substituted": False,
    }
    assert seen_repairs[0] == (None, None)
    assert seen_repairs[1][0]
    assert seen_repairs[1][1] == invalid_plan


def test_optional_quality_repair_provider_failure_returns_valid_original(live, monkeypatch):
    raw = parse_xlsx(template_bytes(live))
    rows, blockers = normalize(raw, live)
    assert not blockers
    planning = {"rows": rows, "map": live["map"], "robots": live["robots"],
                "selected_robot_ids": live["selected_robot_ids"], "clock": live["clock"]}
    original_plan = baseline_plan(planning)
    provider_calls = []

    def fake_request(_context, repair_errors=None, previous_plan=None, provider_trace=None):
        if provider_trace is not None:
            provider_trace["attempts"] += 1
        provider_calls.append((repair_errors, previous_plan))
        if repair_errors is not None:
            assert repair_errors[0]["baseline_metrics"]["transfer_service_seconds"] == 135
            assert repair_errors[0]["proposed_metrics"]["overall_completion_seconds"] == 200
            raise transfer_api.HTTPException(504, {
                "code": "AI_PROVIDER_TIMEOUT",
                "message": "repair timed out",
            })
        return {"summary": "validated original model plan", "plan": original_plan}

    real_compare = transfer_api.compare

    def dominated_compare(scenario, plan):
        result = real_compare(scenario, plan)
        result["baseline"]["metrics"]["transfer_service_seconds"] = 135
        result["baseline"]["metrics"]["overall_completion_seconds"] = 100
        result["proposed"]["metrics"]["transfer_service_seconds"] = 135
        result["proposed"]["metrics"]["overall_completion_seconds"] = 200
        result["quality"]["label"] = "dominated_by_baseline"
        result["quality"]["summary"] = "No service advantage and slower."
        result["quality_assessment"] = {
            "label": "dominated_by_baseline",
            "baseline": {
                "transfer_service_seconds": 135,
                "overall_completion_seconds": 100,
            },
            "proposed": {
                "transfer_service_seconds": 135,
                "overall_completion_seconds": 200,
            },
            "warnings": ["No service advantage and slower."],
        }
        return result

    scenario_id = "TEST-QUALITY-REPAIR-PROVIDER-FAILURE"
    transfer_api._put({
        "scenario_id": scenario_id, "snapshot": live, "revision": 1,
        "raw_rows": raw, "rows": rows, "row_blockers": [],
        "selected_robot_ids": live["selected_robot_ids"], "recommendations": {},
    })
    monkeypatch.setattr(transfer_api, "_request_llm", fake_request)
    monkeypatch.setattr(transfer_api, "compare", dominated_compare)

    result = transfer_api.suggest(scenario_id, transfer_api.RevisionBody(revision=1))

    assert result["plan"] == original_plan
    assert result["validation"]["valid"]
    assert result["source"] == "llm"
    assert result["request_provenance"]["repair_reason"] == "baseline_quality"
    assert result["request_provenance"]["repair_accepted"] is False
    assert result["request_provenance"]["quality_repair_failure"]["code"] == "AI_PROVIDER_TIMEOUT"
    assert result["request_provenance"]["fallback_substituted"] is False
    assert any(
        "returning the original validated LLM plan" in warning
        for warning in result["quality_assessment"]["warnings"]
    )
    assert len(provider_calls) == 2


def test_quality_comparison_reports_honest_batching_tradeoff():
    scenario = _review_from_template(create_snapshot("synthetic_demo"))
    singleton = baseline_plan(scenario)
    first, second = singleton["batches"][:2]
    robot_id = first["transfer_robot_id"]
    picks = [
        copy.deepcopy(stop)
        for batch in (first, second)
        for stop in batch["stops"]
        if stop["action"] == "pick"
    ]
    for stop in picks:
        stop["robot_id"] = robot_id
    transfer = copy.deepcopy(first["stops"][-1])
    transfer["robot_id"] = robot_id
    stops = picks + [transfer]
    for number, stop in enumerate(stops, 1):
        stop["sequence"] = number
    combined = {
        "batch_id": "QUALITY-BATCH", "order_ids": first["order_ids"] + second["order_ids"],
        "transfer_robot_id": robot_id, "pick_robot_ids": [robot_id],
        "execution_order": 1, "order_sequence": first["order_ids"] + second["order_ids"],
        "stops": stops, "rationale": "Explicit transfer-service trade-off.",
    }
    remainder = copy.deepcopy(singleton["batches"][2:])
    for number, batch in enumerate(remainder, 2):
        batch["execution_order"] = number
    result = compare(scenario, {
        "batches": [combined] + remainder,
        "excluded_orders": singleton["excluded_orders"],
    })

    assert result["difference"]["transfer_service_seconds"] > 0
    assert result["quality"]["label"] in {"batching_tradeoff", "improves_baseline"}
    assert result["quality"]["globally_optimal"] is False
    assert "not a proof" in result["quality"]["basis"]
    assert result["quality_assessment"]["label"] == result["quality"]["label"]
    assert set(result["quality_assessment"]["baseline"]) == {
        "transfer_service_seconds", "overall_completion_seconds",
    }
    assert set(result["quality_assessment"]["proposed"]) == {
        "transfer_service_seconds", "overall_completion_seconds",
    }
