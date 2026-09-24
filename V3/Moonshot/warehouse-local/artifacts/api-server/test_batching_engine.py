import copy
import json
import unittest
from batching_scenario import scenario
from batching_engine import compare, duration, enumerate_candidates, simulate, validate_plan


class BatchingEngineTests(unittest.TestCase):
    def setUp(self):
        self.s = scenario()
        self.triple = {"id": "three", "order_ids": ["NEAR-1", "NEAR-2", "NEAR-3"]}

    def valid(self, batches):
        return validate_plan(self.s, {"scenario_id": self.s["scenario_id"], "batches": batches})

    def test_exact_fractional_timing(self):
        self.assertEqual([duration(n) for n in (1, 2, 3)], [45, 67.5, 90])
        run = simulate(self.s, [{"id": "two", "order_ids": ["NEAR-1", "NEAR-2"]}])
        self.assertEqual([e["duration"] for e in run["timeline"] if len(e["order_ids"]) == 2], [67.5, 67.5])

    def test_reproducibility_and_no_mutation(self):
        before = json.dumps(self.s, sort_keys=True)
        first = compare(self.s, [self.triple])
        self.assertEqual(first, compare(scenario(), [self.triple]))
        self.assertEqual(before, json.dumps(self.s, sort_keys=True))
        self.assertEqual(first["baseline"], compare(self.s, [])["batched"])
        # Playback controls are not engine inputs; replay has no advancing wall clock.
        self.assertEqual(first, compare(self.s, [self.triple]))

    def test_candidates_exclude_urgent_and_heavy(self):
        result = enumerate_candidates(self.s)
        self.assertEqual(len(result["candidates"]), 4)
        self.assertTrue(all(set(b["order_ids"]) <= {"NEAR-1", "NEAR-2", "NEAR-3"} for b in result["candidates"]))
        self.assertTrue(any("deadline" in e["reason"] for e in result["exclusions"]))
        self.assertTrue(any("Payload" in e["reason"] for e in result["exclusions"]))

    def test_deadlines_include_downstream(self):
        result = self.valid([{"id": "urgent", "order_ids": ["URGENT", "NEAR-1"]}])
        self.assertFalse(result["valid"])
        self.assertIn("downstream deadline", result["errors"][0])
        self.assertTrue(all(o["on_time"] for o in simulate(self.s, [])["orders"]))

    def test_duplicates_and_malformed(self):
        for batches in (None, {}, [None], [{"id": "x", "order_ids": ["NEAR-1", "NEAR-1"]}],
                        [self.triple, {"id": "other", "order_ids": ["NEAR-1", "NEAR-2"]}],
                        [{"id": "x", "order_ids": ["missing", "NEAR-1"]}]):
            self.assertFalse(self.valid(batches)["valid"])
        self.assertFalse(validate_plan(self.s, {"scenario_id": "stale", "batches": []})["valid"])
        self.s["orders"][1]["lines"][0]["id"] = self.s["orders"][0]["lines"][0]["id"]
        self.assertIn("Duplicate order-line", self.valid([])["errors"][0])

    def test_stock_and_payload(self):
        self.s["map"]["bins"][0]["stock"] = 0
        self.assertIn("Stock overcommitment", self.valid([])["errors"][0])
        self.s = scenario()
        self.assertIn("Payload", self.valid([{"id": "heavy", "order_ids": ["HEAVY", "NEAR-1"]}])["errors"][0])
        for r in self.s["robots"]:
            r["capacity_kg"] = None
        self.assertFalse(self.valid([])["valid"])

    def test_readiness_and_exclusivity(self):
        run = simulate(self.s, [self.triple])
        self.assertNotIn("R-03", {e["resource_id"] for e in run["timeline"]})
        for a in run["timeline"]:
            for b in run["timeline"]:
                if a["id"] != b["id"] and a["resource_id"] == b["resource_id"]:
                    self.assertTrue(a["end"] <= b["start"] or b["end"] <= a["start"])
        self.assertEqual(len([e for e in run["timeline"] if e["start"] == 0]), 2)
        for r in self.s["robots"]:
            r["battery_percent"] = 10
        self.assertFalse(self.valid([])["valid"])

    def test_source_ordering_and_downstream(self):
        run = simulate(self.s, [])
        self.assertEqual(run["timeline"][0]["order_ids"], ["URGENT"])
        self.assertEqual(run["timeline"][0]["resource_id"], "R-01")
        for order in self.s["orders"]:
            events = [e for e in run["timeline"] if order["id"] in e["order_ids"]]
            self.assertEqual([e["stage"] for e in events], ["pick", "move", "pack_feed", "stage"])
            self.assertTrue(all(a["end"] <= b["start"] for a, b in zip(events, events[1:])))

    def test_lineage_metrics_and_graph_paths(self):
        result = compare(self.s, [self.triple])
        self.assertEqual(result["savings"]["service_seconds"], 90)
        self.assertEqual(result["batched"]["metrics"]["logical_tasks"], 20)
        self.assertEqual(result["batched"]["metrics"]["completed_tasks"], 16)
        self.assertEqual(result["baseline"]["inventory"], result["batched"]["inventory"])
        edges = {frozenset((e["from"], e["to"])) for e in self.s["map"]["edges"]}
        for event in result["batched"]["timeline"]:
            self.assertEqual(len(event["line_ids"]), len(event["order_ids"]))
            self.assertEqual(len(event["tote_ids"]), len(event["order_ids"]))
            for a, b in zip(event["path"], event["path"][1:]):
                self.assertIn(frozenset((a["node_id"], b["node_id"])), edges)
                self.assertLessEqual(a["at"], b["at"])
            if event["stage"] in ("stage", "pack_feed"):
                self.assertEqual(event["duration"], 45)

    def test_zones_proximity_unreachable(self):
        self.s["map"]["bins"][1]["zone"] = "OTHER"
        self.assertIn("zones", self.valid([self.triple])["errors"][0])
        self.s = scenario()
        self.s["constraints"]["max_proximity"] = 20
        self.assertIn("proximity", self.valid([self.triple])["errors"][0])
        self.s = scenario()
        self.s["map"]["edges"] = []
        self.assertIn("Unreachable", self.valid([self.triple])["errors"][0])

    def test_empty_and_infeasible_assets_and_running(self):
        self.s["orders"] = []
        self.assertEqual(simulate(self.s, [])["metrics"]["makespan_seconds"], 0)
        self.s = scenario()
        self.s["assets"] = []
        with self.assertRaisesRegex(ValueError, "resource schedule"):
            simulate(self.s, [])
        self.s = scenario()
        self.s["orders"][0]["status"] = "running"
        self.assertIn("already running", self.valid([])["errors"][0])

    def test_no_operational_imports(self):
        import ast
        from pathlib import Path
        allowed = {"collections", "itertools", "heapq", "math"}
        for name in ("batching_engine.py", "batching_scenario.py"):
            tree = ast.parse(Path(__file__).with_name(name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(n.name in allowed for n in node.names))
                if isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed)


if __name__ == "__main__":
    unittest.main()