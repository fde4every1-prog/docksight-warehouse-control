import copy
import asyncio
import json
import unittest
from fastapi import FastAPI, HTTPException

from monthly_kpi_api import router, monthly_kpis, source_coverage
from monthly_kpi_metrics import aggregate, changes, timestamp
from monthly_kpi_sources import bundle, generate, valid_august_pairs


def fixture():
    return {
        "orders": [{"order_id": "O", "warehouse_id": "W", "created_at": "2026-08-01T00:00:00"}],
        "shipments": [{"shipment_id": "S", "order_id": "O", "warehouse_id": "W",
                       "planned_departure": "2026-08-01T02:00:00", "actual_departure": "2026-08-01T02:00:00"}],
        "tasks": [{"task_id": "T", "warehouse_id": "W", "created_at": "2026-08-01T00:00:00",
                   "task_type": "MOVE", "assigned_robot": "", "wes_status": "BLOCKED", "fleet_status": "FAILED"}],
        "robots": [{"robot_id": "R", "warehouse_id": "W", "safety_cert_status": "EXPIRED", "connectivity": "INTERMITTENT"}],
        "inventory_snapshot": [{"warehouse_id": "W", "sku": "K", "location": "L",
                                 "wms_qty": "0", "erp_qty": "0", "vision_qty": ""}],
    }


class MonthlyTests(unittest.TestCase):
    def test_recalibrated_comparison_and_unchanged_metrics(self):
        response = monthly_kpis(x_demo_persona="admin")
        metrics = {m["id"]: m for m in response["metrics"]}
        cycle = metrics["cycle_time"]
        self.assertAlmostEqual(cycle["august"]["value"], 11.308080434246236)
        self.assertAlmostEqual(cycle["september"]["value"], 7.38)
        self.assertAlmostEqual(cycle["change"]["absolute"], -3.928080434246236)
        self.assertAlmostEqual(cycle["change"]["relative_percent"], -34.737, places=2)
        for period in ("august", "september"):
            value = cycle[period]
            self.assertAlmostEqual(value["value"], value["numerator"] / value["denominator"])
            self.assertEqual(value["sample_size"], value["denominator"])
        expected = {
            "on_time_departure": (21.801665404996214, 97.03923019985197),
            "inventory_accuracy": (21.132478632478634, 99.01709401709402),
            "false_availability": (4.915730337078652, 0.2808988764044944),
            "interventions": (369.05384213277574, 34.63146889702039),
        }
        for key, (before, after) in expected.items():
            self.assertAlmostEqual(metrics[key]["august"]["value"], before)
            self.assertAlmostEqual(metrics[key]["september"]["value"], after)
        self.assertEqual(response["periods"]["august"]["start"], "2026-08-01")
        self.assertEqual(response["periods"]["september"]["end"], "2026-09-30")
        self.assertNotIn("0.42", json.dumps(response))

    def test_global_scaling_preserves_filtered_variation_and_timestamps(self):
        source, scenario, manifest = bundle()
        multiplier = manifest["generation"]["duration_multiplier"]
        filtered_values = []
        for warehouse in monthly_kpis(x_demo_persona="admin")["warehouses"]:
            before = aggregate(source, "2026-08", warehouse)["cycle_time"]
            after = aggregate(scenario, "2026-09", warehouse)["cycle_time"]
            self.assertEqual(before["denominator"], after["denominator"])
            self.assertAlmostEqual(after["value"], before["value"] * multiplier)
            filtered_values.append(after["value"])
        self.assertGreater(len(set(round(v, 2) for v in filtered_values)), 1)
        arrivals = {r["order_id"]: timestamp(r["created_at"]) for r in scenario["orders"]}
        for row in scenario["shipments"]:
            actual, planned = timestamp(row["actual_departure"]), timestamp(row["planned_departure"])
            self.assertGreaterEqual(actual, arrivals[row["order_id"]])
            self.assertEqual(actual.strftime("%Y-%m"), "2026-09")
            self.assertEqual(planned.strftime("%Y-%m"), "2026-09")

    def test_calibration_uses_only_valid_baseline_pairs(self):
        for invalid in ("warehouse", "year", "duplicate", "future", "negative"):
            data = fixture()
            if invalid == "warehouse":
                data["shipments"][0]["warehouse_id"] = "OTHER"
            elif invalid == "year":
                data["orders"][0]["created_at"] = "2025-08-01"
            elif invalid == "duplicate":
                data["shipments"].append({**data["shipments"][0], "shipment_id": "OTHER"})
            elif invalid == "future":
                data["shipments"][0]["actual_departure"] = "2026-09-23"
            else:
                data["shipments"][0]["actual_departure"] = "2026-07-31"
            self.assertEqual(valid_august_pairs(data), [])
            with self.assertRaises(ValueError):
                generate(data)

    def test_http_headers(self):
        app = FastAPI()
        app.include_router(router)

        async def request(role):
            messages = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                       "method": "GET", "scheme": "http", "path": "/api/monthly-kpis",
                       "raw_path": b"/api/monthly-kpis", "query_string": b"warehouse=DC-01",
                       "root_path": "", "headers": [(b"x-demo-persona", role.encode())],
                       "server": ("test", 80), "client": ("test", 1)}, receive, send)
            return next(m["status"] for m in messages if m["type"] == "http.response.start")

        for role in ("fleet", "supervisor", "admin"):
            self.assertEqual(asyncio.run(request(role)), 200)
        self.assertEqual(asyncio.run(request("unknown")), 403)

    def test_formulas_and_missing_quantities(self):
        result = aggregate(fixture(), "2026-08", snapshots=True)
        self.assertEqual(result["cycle_time"]["value"], 2)
        self.assertEqual(result["on_time_departure"]["value"], 100)
        self.assertEqual(result["interventions"]["numerator"], 1)
        self.assertEqual(result["false_availability"]["value"], 100)
        self.assertIsNone(result["inventory_accuracy"]["value"])
        self.assertEqual(result["inventory_accuracy"]["exclusions"]["unknown_quantities"], 1)

    def test_unknown_planned_stays_in_denominator(self):
        data = fixture()
        data["shipments"][0]["planned_departure"] = ""
        result = aggregate(data, "2026-08")["on_time_departure"]
        self.assertEqual(result["denominator"], 1)
        self.assertEqual(result["exclusions"]["unknown_planned_departure_in_denominator"], 1)

    def test_missing_invalid_negative_departures(self):
        for departure in ("", "bad", "2026-07-31T23:00:00"):
            data = fixture()
            data["shipments"][0]["actual_departure"] = departure
            self.assertIsNone(aggregate(data, "2026-08")["cycle_time"]["value"])

    def test_duplicate_join_never_multiplies(self):
        data = fixture()
        data["orders"].append(dict(data["orders"][0]))
        self.assertEqual(aggregate(data, "2026-08")["cycle_time"]["denominator"], 1)
        data["shipments"].append({**data["shipments"][0], "shipment_id": "S2"})
        self.assertIsNone(aggregate(data, "2026-08")["cycle_time"]["value"])
        data = fixture()
        data["orders"].append({**data["orders"][0], "created_at": "2026-08-02T00:00:00"})
        self.assertIsNone(aggregate(data, "2026-08")["cycle_time"]["value"])

    def test_conflicting_robots_remain_in_denominator(self):
        data = fixture()
        data["robots"].append({**data["robots"][0], "safety_cert_status": "VALID"})
        result = aggregate(data, "2026-08", snapshots=True)["false_availability"]
        self.assertEqual(result["denominator"], 1)
        self.assertEqual(result["numerator"], 0)
        self.assertEqual(result["exclusions"]["unknown_status"], 1)

    def test_cycle_audit_reports_shipment_conflicts_and_pairs(self):
        data = fixture()
        data["shipments"].append(dict(data["shipments"][0]))
        result = aggregate(data, "2026-08")["cycle_time"]
        self.assertEqual(result["matched_pair_count"], 1)
        self.assertEqual(result["exclusions"]["shipment_duplicate_rows"], 1)
        data["shipments"][1]["actual_departure"] = "2026-08-01T03:00:00"
        result = aggregate(data, "2026-08")["cycle_time"]
        self.assertEqual(result["matched_pair_count"], 0)
        self.assertEqual(result["exclusions"]["shipment_ambiguous_identities"], 1)

    def test_source_as_of_excludes_future_actuals_and_cohorts(self):
        data = fixture()
        data["shipments"][0]["planned_departure"] = "2026-08-01T01:00:00"
        result = aggregate(data, "2026-08", as_of="2026-08-01T01:30:00Z")
        self.assertIsNone(result["cycle_time"]["value"])
        self.assertIsNone(result["on_time_departure"]["value"])
        self.assertEqual(result["cycle_time"]["exclusions"]["future_actual_departure"], 1)
        self.assertEqual(result["on_time_departure"]["exclusions"]["future_actual_departure"], 1)
        self.assertEqual(aggregate(data, "2026-08")["cycle_time"]["value"], 2)
        result = aggregate(data, "2026-08", as_of="2026-07-31T23:00:00Z")
        self.assertEqual(result["interventions"]["denominator"], 0)

    def test_coverage_derived_from_scoped_records(self):
        data = fixture()
        self.assertEqual(source_coverage(data)["orders"], ("2026-08-01", "2026-08-01"))
        self.assertIsNone(source_coverage(data, warehouse="absent")["orders"])
        self.assertIsNone(source_coverage(data, as_of="2026-07-31T23:00:00Z")["shipments"])

    def test_or_unique_unassigned_tasks(self):
        data = fixture()
        data["tasks"].append({**data["tasks"][0], "wes_status": "COMPLETE"})
        result = aggregate(data, "2026-08")["interventions"]
        self.assertEqual((result["numerator"], result["denominator"]), (1, 1))

    def test_filters_zeros_and_snapshots(self):
        data = fixture()
        result = aggregate(data, "2026-08", "other", snapshots=True)
        self.assertTrue(all(v["value"] is None for v in result.values()))
        self.assertIsNone(aggregate(data, "2026-09")["false_availability"]["value"])
        self.assertIsNone(changes({"value": 0}, {"value": 5})["relative_percent"])
        self.assertEqual(changes({"value": 10}, {"value": 20}, True)["percentage_points"], 10)

    def test_deterministic_and_immutable(self):
        source, scenario, manifest = bundle()
        before = copy.deepcopy(source)
        self.assertEqual(scenario, generate(source))
        self.assertEqual(before, source)
        self.assertFalse(manifest["archive_benchmark"]["used_in_metrics"])
        for metric in monthly_kpis(x_demo_persona="supervisor")["metrics"]:
            self.assertIsNotNone(metric["august"]["value"])
            self.assertIsNotNone(metric["september"]["value"])

    def test_all_personas_and_validation(self):
        self.assertTrue(any(route.path == "/api/monthly-kpis" for route in router.routes))
        for role in ("fleet", "supervisor", "admin"):
            response = monthly_kpis(warehouse="DC-01", x_demo_persona=role)
            self.assertEqual(response["warehouse"], "DC-01")
            self.assertNotIn("synthetic", json.dumps(response).lower())
        with self.assertRaises(HTTPException) as denied:
            monthly_kpis(x_demo_persona="stranger")
        self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(HTTPException) as invalid:
            monthly_kpis(warehouse="unknown", x_demo_persona="admin")
        self.assertEqual(invalid.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()