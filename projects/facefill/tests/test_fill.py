from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from facefill.fill import fill
from facefill.model import Face, FillPlan, Reserve
from facefill.warehouses import get_warehouse


def plan(**kwargs) -> FillPlan:
    payload = {
        "warehouse": {"preset": "mini_3"},
        "strategy": "auto",
        "faces": [
            {
                "id": "A1-01",
                "sku": "MILK",
                "aisle": 1,
                "bay": 1,
                "min_qty": 12,
                "max_qty": 36,
                "on_hand": 6,
                "case_qty": 6,
            }
        ],
        "reserve": [{"id": "R1", "sku": "MILK", "aisle": 8, "cases": 8}],
        "demand": [],
    }
    payload.update(kwargs)
    return FillPlan.from_dict(payload)


class FillTests(unittest.TestCase):
    def test_below_min_fills_to_max(self) -> None:
        result = fill(plan())
        self.assertTrue(result.all_filled)
        self.assertEqual(result.task_count, 1)
        task = result.tasks[0]
        self.assertEqual(task.face.id, "A1-01")
        self.assertEqual(task.cases, 5)
        self.assertEqual(task.after_qty, 36)
        self.assertEqual(task.trigger, "already below min")
        self.assertEqual(task.pulls[0].reserve_id, "R1")

    def test_healthy_face_is_skipped(self) -> None:
        result = fill(
            plan(
                faces=[
                    {
                        "id": "OK",
                        "sku": "OK",
                        "aisle": 1,
                        "bay": 1,
                        "min_qty": 10,
                        "max_qty": 40,
                        "on_hand": 30,
                        "case_qty": 10,
                    }
                ],
                demand=[{"sku": "OK", "units": 8}],
            )
        )
        self.assertTrue(result.all_filled)
        self.assertEqual(result.task_count, 0)
        self.assertEqual(result.faces[0].status, "healthy")

    def test_wave_demand_triggers_replen(self) -> None:
        result = fill(
            plan(
                faces=[
                    {
                        "id": "WAVE",
                        "sku": "TEA",
                        "aisle": 1,
                        "bay": 2,
                        "min_qty": 20,
                        "max_qty": 80,
                        "on_hand": 40,
                        "case_qty": 10,
                    }
                ],
                reserve=[{"id": "R-TEA", "sku": "TEA", "aisle": 7, "cases": 6}],
                demand=[{"sku": "TEA", "units": 30}],
            )
        )
        self.assertTrue(result.all_filled)
        self.assertEqual(result.tasks[0].trigger, "wave will breach min")
        self.assertEqual(result.tasks[0].cases, 4)
        self.assertEqual(result.faces[0].projected, 10)
        self.assertGreaterEqual(result.faces[0].projected_after, 20)

    def test_no_reserve_is_leftover(self) -> None:
        result = fill(plan(reserve=[]))
        self.assertFalse(result.all_filled)
        self.assertEqual(result.leftover[0]["id"], "A1-01")
        self.assertIn("no reserve stock", result.leftover[0]["reason"])

    def test_case_does_not_fit_is_leftover(self) -> None:
        result = fill(
            plan(
                faces=[
                    {
                        "id": "TIGHT",
                        "sku": "OIL",
                        "aisle": 1,
                        "bay": 1,
                        "min_qty": 20,
                        "max_qty": 24,
                        "on_hand": 22,
                        "case_qty": 8,
                    }
                ],
                reserve=[{"id": "R-OIL", "sku": "OIL", "aisle": 6, "cases": 4}],
                demand=[{"sku": "OIL", "units": 10}],
            )
        )
        self.assertIn("case does not fit remaining face room", result.leftover[0]["reason"])
        self.assertEqual(result.task_count, 0)

    def test_outside_layout_is_leftover(self) -> None:
        result = fill(
            plan(
                faces=[
                    {
                        "id": "LOST",
                        "sku": "X",
                        "aisle": 9,
                        "bay": 1,
                        "min_qty": 4,
                        "max_qty": 20,
                        "on_hand": 1,
                        "case_qty": 4,
                    }
                ]
            )
        )
        self.assertIn("outside layout", result.leftover[0]["reason"])

    def test_nearest_reserve_is_used_first(self) -> None:
        result = fill(
            plan(
                faces=[
                    {
                        "id": "NEAR",
                        "sku": "PEN",
                        "aisle": 3,
                        "bay": 1,
                        "min_qty": 20,
                        "max_qty": 80,
                        "on_hand": 8,
                        "case_qty": 8,
                    }
                ],
                reserve=[
                    {"id": "FAR", "sku": "PEN", "aisle": 20, "cases": 10},
                    {"id": "CLOSE", "sku": "PEN", "aisle": 3, "cases": 2},
                ],
            )
        )
        pulls = result.tasks[0].pulls
        self.assertEqual(pulls[0].reserve_id, "CLOSE")
        self.assertEqual(pulls[0].cases, 2)
        self.assertEqual(pulls[1].reserve_id, "FAR")

    def test_partial_reserve_leaves_short_reason(self) -> None:
        result = fill(
            plan(
                faces=[
                    {
                        "id": "SHORT",
                        "sku": "SALT",
                        "aisle": 2,
                        "bay": 1,
                        "min_qty": 24,
                        "max_qty": 48,
                        "on_hand": 4,
                        "case_qty": 8,
                    }
                ],
                reserve=[{"id": "R-SALT", "sku": "SALT", "aisle": 7, "cases": 1}],
                demand=[{"sku": "SALT", "units": 8}],
            )
        )
        self.assertEqual(result.task_count, 1)
        self.assertEqual(result.tasks[0].cases, 1)
        self.assertEqual(result.leftover[0]["id"], "SHORT")
        self.assertIn("reserve short", result.leftover[0]["reason"])

    def test_labor_cap_stops_later_faces(self) -> None:
        result = fill(
            plan(
                warehouse={"preset": "mini_3", "max_labor_min": 22},
                strategy="cluster",
                faces=[
                    {
                        "id": f"A{aisle}-B{bay}",
                        "sku": f"SKU-{aisle}-{bay}",
                        "aisle": aisle,
                        "bay": bay,
                        "min_qty": 12,
                        "max_qty": 36,
                        "on_hand": 4,
                        "case_qty": 4,
                    }
                    for aisle, bay in ((1, 1), (1, 2), (1, 3), (2, 1), (3, 1))
                ],
                reserve=[
                    {"id": f"R-{aisle}-{bay}", "sku": f"SKU-{aisle}-{bay}", "aisle": 9, "cases": 10}
                    for aisle, bay in ((1, 1), (1, 2), (1, 3), (2, 1), (3, 1))
                ],
            )
        )
        self.assertEqual({task.face.aisle for task in result.tasks}, {1})
        self.assertEqual(result.task_count, 3)
        leftover = {item["id"]: item["reason"] for item in result.leftover}
        self.assertIn("no remaining labor", leftover["A2-B1"])
        self.assertIn("no remaining labor", leftover["A3-B1"])

    def test_cluster_fits_more_than_urgent_when_labor_is_tight(self) -> None:
        payload = {
            "warehouse": {"preset": "mini_3", "max_labor_min": 22},
            "faces": [
                {
                    "id": "A1-B1",
                    "sku": "SKU-A1B1",
                    "aisle": 1,
                    "bay": 1,
                    "min_qty": 12,
                    "max_qty": 36,
                    "on_hand": 8,
                    "case_qty": 4,
                },
                {
                    "id": "A1-B3",
                    "sku": "SKU-A1B3",
                    "aisle": 1,
                    "bay": 3,
                    "min_qty": 12,
                    "max_qty": 36,
                    "on_hand": 6,
                    "case_qty": 4,
                },
                {
                    "id": "A1-B4",
                    "sku": "SKU-A1B4",
                    "aisle": 1,
                    "bay": 4,
                    "min_qty": 12,
                    "max_qty": 36,
                    "on_hand": 10,
                    "case_qty": 4,
                },
                {
                    "id": "A2-B2",
                    "sku": "SKU-A2B2",
                    "aisle": 2,
                    "bay": 2,
                    "min_qty": 12,
                    "max_qty": 36,
                    "on_hand": 4,
                    "case_qty": 4,
                },
                {
                    "id": "A3-B1",
                    "sku": "SKU-A3B1",
                    "aisle": 3,
                    "bay": 1,
                    "min_qty": 12,
                    "max_qty": 36,
                    "on_hand": 1,
                    "case_qty": 4,
                },
            ],
            "reserve": [
                {"id": "R-1", "sku": "SKU-A1B1", "aisle": 9, "cases": 10},
                {"id": "R-2", "sku": "SKU-A1B3", "aisle": 9, "cases": 10},
                {"id": "R-3", "sku": "SKU-A1B4", "aisle": 9, "cases": 10},
                {"id": "R-4", "sku": "SKU-A2B2", "aisle": 9, "cases": 10},
                {"id": "R-5", "sku": "SKU-A3B1", "aisle": 9, "cases": 10},
            ],
        }
        clustered = fill(FillPlan.from_dict({**payload, "strategy": "cluster"}))
        urgent = fill(FillPlan.from_dict({**payload, "strategy": "urgent"}))
        self.assertGreater(clustered.task_count, urgent.task_count)
        self.assertEqual(urgent.tasks[0].face.id, "A3-B1")

    def test_task_cap_is_enforced(self) -> None:
        result = fill(
            plan(
                warehouse={"preset": "mini_3", "max_tasks": 1},
                faces=[
                    {
                        "id": "ONE",
                        "sku": "A",
                        "aisle": 1,
                        "bay": 1,
                        "min_qty": 8,
                        "max_qty": 24,
                        "on_hand": 2,
                        "case_qty": 4,
                    },
                    {
                        "id": "TWO",
                        "sku": "B",
                        "aisle": 1,
                        "bay": 2,
                        "min_qty": 8,
                        "max_qty": 24,
                        "on_hand": 2,
                        "case_qty": 4,
                    },
                ],
                reserve=[
                    {"id": "RA", "sku": "A", "aisle": 8, "cases": 5},
                    {"id": "RB", "sku": "B", "aisle": 8, "cases": 5},
                ],
            )
        )
        self.assertEqual(result.task_count, 1)
        self.assertIn("over task cap", result.leftover[0]["reason"])

    def test_demand_strategy_takes_largest_wave_first(self) -> None:
        result = fill(
            plan(
                warehouse={"preset": "mini_3", "max_tasks": 1},
                strategy="demand",
                faces=[
                    {
                        "id": "SMALL",
                        "sku": "S",
                        "aisle": 1,
                        "bay": 1,
                        "min_qty": 10,
                        "max_qty": 40,
                        "on_hand": 8,
                        "case_qty": 4,
                    },
                    {
                        "id": "BIG",
                        "sku": "L",
                        "aisle": 2,
                        "bay": 1,
                        "min_qty": 10,
                        "max_qty": 40,
                        "on_hand": 8,
                        "case_qty": 4,
                    },
                ],
                reserve=[
                    {"id": "RS", "sku": "S", "aisle": 8, "cases": 8},
                    {"id": "RL", "sku": "L", "aisle": 8, "cases": 8},
                ],
                demand=[{"sku": "S", "units": 4}, {"sku": "L", "units": 20}],
            )
        )
        self.assertEqual(result.tasks[0].face.id, "BIG")
        self.assertEqual(result.leftover[0]["id"], "SMALL")

    def test_morning_grocery_example_all_fits(self) -> None:
        payload = Path(__file__).resolve().parents[1] / "examples" / "morning-grocery.json"
        result = fill(FillPlan.from_dict(json.loads(payload.read_text())))
        self.assertTrue(result.all_filled)
        self.assertEqual(result.task_count, 5)
        self.assertEqual(result.healthy_after, 8)
        ids = {task.face.id for task in result.tasks}
        self.assertEqual(ids, {"A1-03", "A1-06", "A2-05", "A3-04", "A5-07"})

    def test_reserve_short_example(self) -> None:
        payload = Path(__file__).resolve().parents[1] / "examples" / "reserve-short.json"
        result = fill(FillPlan.from_dict(json.loads(payload.read_text())))
        self.assertFalse(result.all_filled)
        leftover = {item["id"]: item["reason"] for item in result.leftover}
        self.assertIn("NONE", leftover)
        self.assertIn("no reserve stock", leftover["NONE"])
        self.assertIn("SHORT", leftover)
        self.assertIn("reserve short", leftover["SHORT"])
        self.assertIn("BLOCK", leftover)
        self.assertIn("case does not fit", leftover["BLOCK"])
        assigned = {task.face.id for task in result.tasks}
        self.assertEqual(assigned, {"OK", "SHORT"})
        keep = next(state for state in result.faces if state.face.id == "KEEP")
        self.assertEqual(keep.status, "healthy")

    def test_labor_capped_example(self) -> None:
        payload = Path(__file__).resolve().parents[1] / "examples" / "labor-capped.json"
        result = fill(FillPlan.from_dict(json.loads(payload.read_text())))
        self.assertEqual(result.task_count, 3)
        self.assertTrue(all(task.face.aisle == 1 for task in result.tasks))
        self.assertEqual(result.leftover_count, 2)

    def test_wave_breach_example_uses_nearest_pen_reserve(self) -> None:
        payload = Path(__file__).resolve().parents[1] / "examples" / "wave-breach.json"
        result = fill(FillPlan.from_dict(json.loads(payload.read_text())))
        self.assertTrue(result.all_filled)
        self.assertEqual(result.task_count, 3)
        pen = next(task for task in result.tasks if task.face.id == "E3-PEN")
        self.assertEqual(pen.pulls[0].reserve_id, "R-PEN-B")
        bag = next(state for state in result.faces if state.face.id == "E1-BAG")
        self.assertEqual(bag.status, "healthy")

    def test_custom_warehouse_from_dict(self) -> None:
        house = get_warehouse(
            {
                "name": "One aisle",
                "aisle_count": 1,
                "bays_per_aisle": 2,
                "max_tasks": 2,
                "max_labor_min": 30,
                "minutes_per_task": 4,
                "aisle_change_min": 1,
            }
        )
        result = fill(
            FillPlan(
                warehouse=house,
                faces=[
                    Face(
                        id="F1",
                        sku="Z",
                        aisle=1,
                        bay=1,
                        min_qty=4,
                        max_qty=12,
                        on_hand=2,
                        case_qty=2,
                    )
                ],
                reserve=[Reserve(id="RZ", sku="Z", aisle=4, cases=6)],
                demand={},
            )
        )
        self.assertTrue(result.all_filled)
        self.assertEqual(result.tasks[0].after_qty, 12)

    def test_does_not_exceed_max_qty(self) -> None:
        result = fill(
            plan(
                faces=[
                    {
                        "id": "CAP",
                        "sku": "C",
                        "aisle": 1,
                        "bay": 1,
                        "min_qty": 10,
                        "max_qty": 20,
                        "on_hand": 7,
                        "case_qty": 6,
                    }
                ],
                reserve=[{"id": "RC", "sku": "C", "aisle": 5, "cases": 20}],
            )
        )
        self.assertEqual(result.tasks[0].after_qty, 19)
        self.assertLessEqual(result.tasks[0].after_qty, 20)
