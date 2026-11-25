from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vasline.model import Workbook
from vasline.schedule import plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def book(**kwargs) -> Workbook:
    payload = {
        "benches": [
            {
                "id": "B1",
                "name": "Label",
                "skills": ["relabel", "ticket", "insert"],
                "shift_min": 480,
            },
            {
                "id": "B2",
                "name": "Kit",
                "skills": ["kit", "shrink", "insert"],
                "shift_min": 480,
            },
            {
                "id": "B3",
                "name": "Pack",
                "skills": ["wrap", "inspect", "rework", "shrink"],
                "shift_min": 480,
            },
        ],
        "jobs": [
            {
                "id": "J1",
                "sku": "SKU-A",
                "units": 10,
                "due_min": 60,
                "priority": 2,
                "family": "STORE",
                "steps": [{"op": "relabel", "seconds_per_unit": 8, "setup_seconds": 90}],
            }
        ],
    }
    payload.update(kwargs)
    return Workbook.from_dict(payload)


class ScheduleTests(unittest.TestCase):
    def test_single_job_starts_at_origin(self) -> None:
        result = plan(book())
        self.assertTrue(result.all_fit)
        self.assertEqual(len(result.tasks), 1)
        task = result.tasks[0]
        self.assertEqual(task.bench, "B1")
        self.assertEqual((task.start_sec, task.finish_sec, task.setup_sec), (0, 80, 0))

    def test_two_jobs_queue_on_one_bench(self) -> None:
        result = plan(
            book(
                jobs=[
                    {
                        "id": "A",
                        "sku": "S",
                        "units": 10,
                        "due_min": 30,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "relabel", "seconds_per_unit": 8, "setup_seconds": 90}],
                    },
                    {
                        "id": "B",
                        "sku": "S",
                        "units": 5,
                        "due_min": 40,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "relabel", "seconds_per_unit": 8, "setup_seconds": 90}],
                    },
                ]
            )
        )
        by_job = {task.job: task for task in result.tasks}
        self.assertEqual(by_job["A"].start_sec, 0)
        self.assertEqual(by_job["A"].finish_sec, 80)
        self.assertEqual(by_job["B"].start_sec, 80)
        self.assertEqual(by_job["B"].finish_sec, 120)
        self.assertEqual(by_job["B"].setup_sec, 0)

    def test_second_step_waits_for_first_on_another_bench(self) -> None:
        result = plan(
            book(
                jobs=[
                    {
                        "id": "KIT-WRAP",
                        "sku": "GIFT",
                        "units": 4,
                        "due_min": 60,
                        "priority": 2,
                        "family": "GIFT",
                        "steps": [
                            {"op": "kit", "seconds_per_unit": 25, "setup_seconds": 180},
                            {"op": "wrap", "seconds_per_unit": 40, "setup_seconds": 120},
                        ],
                    }
                ]
            )
        )
        self.assertTrue(result.all_fit)
        kit, wrap = result.tasks[0], result.tasks[1]
        if kit.op != "kit":
            kit, wrap = wrap, kit
        self.assertEqual(kit.bench, "B2")
        self.assertEqual(wrap.bench, "B3")
        self.assertEqual(kit.finish_sec, 100)
        self.assertEqual(wrap.start_sec, 100)
        self.assertEqual(wrap.finish_sec, 260)

    def test_family_change_pays_setup_first_job_does_not(self) -> None:
        result = plan(
            Workbook.from_dict(json.loads((EXAMPLES / "changeover-hit.json").read_text()))
        )
        by_job = {task.job: task for task in result.tasks}
        self.assertEqual(by_job["STORE-40"].setup_sec, 0)
        self.assertEqual(by_job["STORE-40"].start_sec, 0)
        self.assertEqual(by_job["STORE-40"].finish_sec, 320)
        self.assertEqual(by_job["DTC-40"].setup_sec, 90)
        self.assertEqual(by_job["DTC-40"].start_sec, 410)
        self.assertEqual(by_job["DTC-40"].finish_sec, 730)

    def test_skill_miss_is_atomic_leftover(self) -> None:
        result = plan(Workbook.from_dict(json.loads((EXAMPLES / "skill-miss.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual([item["job"] for item in result.leftover], ["ORD-202"])
        self.assertIn("wrap", result.leftover[0]["reason"])
        self.assertEqual([task.job for task in result.tasks], ["ORD-201"])

    def test_partial_job_does_not_occupy_a_bench(self) -> None:
        result = plan(
            book(
                benches=[
                    {
                        "id": "B2",
                        "name": "Kit",
                        "skills": ["kit"],
                        "shift_min": 480,
                    }
                ],
                jobs=[
                    {
                        "id": "HALF",
                        "sku": "PROMO",
                        "units": 4,
                        "due_min": 60,
                        "priority": 2,
                        "family": "KIT",
                        "steps": [
                            {"op": "kit", "seconds_per_unit": 25, "setup_seconds": 180},
                            {"op": "wrap", "seconds_per_unit": 40, "setup_seconds": 120},
                        ],
                    }
                ],
            )
        )
        self.assertEqual(result.tasks, [])
        self.assertEqual(result.leftover[0]["job"], "HALF")
        self.assertIn("wrap", result.leftover[0]["reason"])

    def test_shift_overflow_leaves_the_second_job(self) -> None:
        result = plan(Workbook.from_dict(json.loads((EXAMPLES / "late-due.json").read_text())))
        self.assertEqual([item.job for item in result.scheduled], ["RUSH-A"])
        self.assertEqual(result.scheduled[0].finish_sec, 800)
        self.assertTrue(result.scheduled[0].tardy)
        self.assertEqual(result.scheduled[0].tardy_sec, 200)
        self.assertEqual(result.leftover[0]["job"], "BULK-B")
        self.assertIn("shift end", result.leftover[0]["reason"])

    def test_priority_one_cuts_ahead_of_a_listed_bulk_job(self) -> None:
        result = plan(Workbook.from_dict(json.loads((EXAMPLES / "priority-cut.json").read_text())))
        by_job = {task.job: task for task in result.tasks}
        self.assertEqual(by_job["RUSH-01"].start_sec, 0)
        self.assertEqual(by_job["RUSH-01"].finish_sec, 80)
        self.assertEqual(by_job["BIG-STORE"].start_sec, 80)
        self.assertEqual(by_job["BIG-STORE"].finish_sec, 880)

    def test_same_priority_uses_earlier_due(self) -> None:
        result = plan(
            book(
                jobs=[
                    {
                        "id": "LATE",
                        "sku": "S",
                        "units": 10,
                        "due_min": 90,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "relabel", "seconds_per_unit": 8, "setup_seconds": 90}],
                    },
                    {
                        "id": "EARLY",
                        "sku": "S",
                        "units": 10,
                        "due_min": 20,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "relabel", "seconds_per_unit": 8, "setup_seconds": 90}],
                    },
                ]
            )
        )
        by_job = {task.job: task for task in result.tasks}
        self.assertEqual(by_job["EARLY"].start_sec, 0)
        self.assertEqual(by_job["LATE"].start_sec, 80)

    def test_parallel_benches_both_start_at_zero(self) -> None:
        result = plan(
            book(
                jobs=[
                    {
                        "id": "LBL",
                        "sku": "A",
                        "units": 10,
                        "due_min": 30,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "relabel", "seconds_per_unit": 8, "setup_seconds": 90}],
                    },
                    {
                        "id": "KIT",
                        "sku": "B",
                        "units": 4,
                        "due_min": 30,
                        "priority": 2,
                        "family": "KIT",
                        "steps": [{"op": "kit", "seconds_per_unit": 25, "setup_seconds": 180}],
                    },
                ]
            )
        )
        starts = {task.job: task.start_sec for task in result.tasks}
        self.assertEqual(starts["LBL"], 0)
        self.assertEqual(starts["KIT"], 0)

    def test_balanced_shift_places_every_job(self) -> None:
        result = plan(Workbook.from_dict(json.loads((EXAMPLES / "balanced-shift.json").read_text())))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.tardy_count, 0)
        self.assertEqual(len(result.scheduled), 5)

    def test_duplicate_job_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            book(
                jobs=[
                    {
                        "id": "SAME",
                        "sku": "A",
                        "units": 1,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "relabel"}],
                    },
                    {
                        "id": "SAME",
                        "sku": "B",
                        "units": 1,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "relabel"}],
                    },
                ]
            )

    def test_unknown_op_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            book(
                jobs=[
                    {
                        "id": "X",
                        "sku": "A",
                        "units": 1,
                        "priority": 2,
                        "family": "STORE",
                        "steps": [{"op": "laser-etch"}],
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
