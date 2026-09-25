"""Tests intentionally import only the detached router, never baseline_demo."""
import copy
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import batching_api as api


class BatchingAPITest(unittest.TestCase):
    def setUp(self):
        api._cache.clear()
        api._failure_until = 0
        self.s = api.scenario()
        self.candidate = api.enumerate_candidates(self.s)["candidates"][0]
        self.output = {
            "selected_candidate_ids": [self.candidate["id"]],
            "reasons": [{"candidate_id": self.candidate["id"], "reason": "Nearby, within capacity and deadlines."}],
            "summary": "Synthetic batching recommendation.",
            "exclusions": [],
        }

    def test_real_request_is_cached_and_bound_to_inputs(self):
        body = api.ScenarioInput(scenario_id=self.s["scenario_id"])
        with patch.object(api, "request_llm", return_value=self.output) as llm:
            first = api.suggest_plan(body)
            second = api.suggest_plan(body)
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            self.assertEqual(llm.call_count, 1)
            changed = copy.deepcopy(self.s)
            changed["seed"] += 1
            with patch.object(api, "scenario", return_value=changed):
                api.suggest_plan(body)
            self.assertEqual(llm.call_count, 2)

    def test_malformed_response_rejected_not_cached(self):
        with patch.object(api, "request_llm", return_value={"summary": "bad"}):
            with self.assertRaises(HTTPException) as exc:
                api.suggest_plan(api.ScenarioInput(scenario_id=self.s["scenario_id"]))
        self.assertEqual(exc.exception.status_code, 502)
        self.assertFalse(api._cache)

    def test_unknown_duplicate_and_stale_membership_rejected(self):
        for ids in [["invented"], [self.candidate["id"]] * 2]:
            with self.assertRaises(HTTPException):
                api.resolve_batches(self.s, ids)
        with self.assertRaises(HTTPException) as exc:
            api.checked_scenario("old-version")
        self.assertEqual(exc.exception.status_code, 409)

    def test_no_database_or_operational_imports_required(self):
        with patch("sqlite3.connect", side_effect=AssertionError("Live DB access forbidden")):
            initial = api.get_scenario()
            result = api.compare_plan(api.CompareInput(
                scenario_id=self.s["scenario_id"], candidate_ids=[self.candidate["id"]]))
            self.assertEqual(initial["scenario"], self.s)
            self.assertEqual(result["baseline"]["scenario_id"], self.s["scenario_id"])
            self.assertEqual(api.scenario(), self.s)

    def test_reasons_and_exclusions_are_bounded_and_valid(self):
        for key, value in [
            ("reasons", []),
            ("summary", ""),
            ("exclusions", [{"order_ids": ["unknown"], "reason": "invented"}]),
        ]:
            output = {**self.output, key: value}
            with self.assertRaises(ValueError):
                api.validate_llm(self.s, output)

    def test_no_hidden_provider_fallback(self):
        with patch.object(api, "request_llm", side_effect=HTTPException(504, "AI unavailable")):
            with self.assertRaises(HTTPException) as exc:
                api.suggest_plan(api.ScenarioInput(scenario_id=self.s["scenario_id"]))
            self.assertEqual(exc.exception.status_code, 504)
            self.assertFalse(api._cache)


if __name__ == "__main__":
    unittest.main()