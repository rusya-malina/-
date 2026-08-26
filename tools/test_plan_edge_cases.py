"""Unit tests for hourly KPI plan boundary conditions."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.kpi_service import build_plan_projection


class PlanProjectionEdgeCaseTests(unittest.TestCase):
    def test_completed_and_overachieved_facts_clamp_remaining_to_zero(self) -> None:
        projection = build_plan_projection(
            {
                "gt_plan": 90,
                "gt_fact": 120,
                "micro_plan": 128,
                "micro_las_fact": 100,
                "micro_lau_fact": 100,
            },
            as_of=date(2026, 8, 21),
        )
        for row in projection["rows"]:
            self.assertEqual(row["gt_remaining"], 0)
            self.assertEqual(row["las_remaining"], 0)
            self.assertEqual(row["lau_remaining"], 0)
            self.assertEqual(row["micro_total_remaining"], 0)
            self.assertEqual(row["gt_per_hour_rounded"], 0)
            self.assertEqual(row["las_per_hour_rounded"], 0)
            self.assertEqual(row["lau_per_hour_rounded"], 0)

    def test_zero_plan_and_zero_fact_produce_zero_rates(self) -> None:
        projection = build_plan_projection(
            {
                "gt_plan": 0,
                "gt_fact": 0,
                "micro_plan": 0,
                "micro_las_fact": 0,
                "micro_lau_fact": 0,
            },
            as_of=date(2026, 8, 21),
        )
        for row in projection["rows"]:
            self.assertEqual(row["gt_remaining"], 0)
            self.assertEqual(row["las_remaining"], 0)
            self.assertEqual(row["lau_remaining"], 0)
            self.assertEqual(row["micro_total_remaining"], 0)
            self.assertEqual(row["gt_per_hour"], 0)
            self.assertEqual(row["las_per_hour"], 0)
            self.assertEqual(row["lau_per_hour"], 0)

    def test_small_positive_remainder_rounds_up_to_one_per_hour(self) -> None:
        projection = build_plan_projection(
            {
                "gt_plan": 90,
                "gt_fact": 89.9,
                "micro_plan": 128,
                "micro_las_fact": 51.19,
                "micro_lau_fact": 76.79,
            },
            as_of=date(2026, 8, 21),
        )
        for row in projection["rows"]:
            self.assertGreater(row["gt_remaining"], 0)
            self.assertGreater(row["las_remaining"], 0)
            self.assertGreater(row["lau_remaining"], 0)
            self.assertEqual(row["las_per_hour_rounded"], 1)
            self.assertEqual(row["lau_per_hour_rounded"], 1)

    def test_no_working_hours_does_not_divide_by_zero(self) -> None:
        projection = build_plan_projection(
            {
                "gt_plan": 90,
                "gt_fact": 0,
                "micro_plan": 128,
                "micro_las_fact": 0,
                "micro_lau_fact": 0,
            },
            as_of=date(2026, 8, 31),
        )
        self.assertEqual(projection["workdays_left"], 0)
        self.assertEqual(projection["hours_left"], 0)
        for row in projection["rows"]:
            self.assertEqual(row["gt_per_hour"], 0)
            self.assertEqual(row["las_per_hour"], 0)
            self.assertEqual(row["lau_per_hour"], 0)
            self.assertEqual(row["gt_per_hour_rounded"], 0)
            self.assertEqual(row["las_per_hour_rounded"], 0)
            self.assertEqual(row["lau_per_hour_rounded"], 0)

    def test_non_positive_workday_duration_is_rejected(self) -> None:
        record = {"gt_plan": 90, "micro_plan": 128}
        with self.assertRaises(ValueError):
            build_plan_projection(record, as_of=date(2026, 8, 21), hours_per_workday=0)
        with self.assertRaises(ValueError):
            build_plan_projection(record, as_of=date(2026, 8, 21), hours_per_workday=-4)


if __name__ == "__main__":
    unittest.main()
