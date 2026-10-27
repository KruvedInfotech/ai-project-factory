from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from slotfold.fold import fold
from slotfold.model import FoldPlan, Location


def plan(**kwargs) -> FoldPlan:
    payload = {
        "warehouse": {"preset": "small_dc"},
        "labor_minutes": 48,
        "minutes_per_move": 4,
        "keep_last_pick_face": True,
        "locations": [
            {
                "aisle": "A",
                "bay": 1,
                "level": 1,
                "sku": "A",
                "qty": 4,
                "max_qty": 10,
                "kind": "reserve",
            },
            {
                "aisle": "A",
                "bay": 5,
                "level": 1,
                "sku": "A",
                "qty": 6,
                "max_qty": 10,
                "kind": "reserve",
            },
        ],
    }
    payload.update(kwargs)
    return FoldPlan.from_dict(payload)


class FoldTests(unittest.TestCase):
    def test_same_aisle_partials_fold_and_free_a_slot(self) -> None:
        result = fold(plan())
        self.assertTrue(result.all_folded)
        self.assertEqual(result.move_count, 1)
        self.assertEqual(result.freed_count, 1)
        self.assertEqual(result.moves[0].from_id, "A-01-1")
        self.assertEqual(result.moves[0].to_id, "A-05-1")
        self.assertEqual(result.moves[0].qty, 4)

    def test_mixed_example_frees_four_slots(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mixed-partials.json"
        result = fold(FoldPlan.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_folded)
        self.assertEqual(result.freed_count, 4)
        self.assertEqual(result.units_moved, 5 + 4 + 8 + 3)

    def test_same_aisle_example_leaves_pick_face(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "same-aisle.json"
        result = fold(FoldPlan.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_folded)
        self.assertEqual(result.freed[0]["id"], "B-02-1")
        pick = next(item for item in result.locations if item["id"] == "B-07-2")
        self.assertEqual(pick["qty"], 20)

    def test_last_pick_face_does_not_donate(self) -> None:
        result = fold(
            plan(
                locations=[
                    {
                        "aisle": "C",
                        "bay": 2,
                        "level": 1,
                        "sku": "RICE",
                        "qty": 4,
                        "max_qty": 20,
                        "kind": "reserve",
                    },
                    {
                        "aisle": "C",
                        "bay": 2,
                        "level": 3,
                        "sku": "RICE",
                        "qty": 10,
                        "max_qty": 20,
                        "kind": "pick",
                    },
                ]
            )
        )
        self.assertTrue(result.all_folded)
        self.assertEqual(result.moves[0].from_id, "C-02-1")
        self.assertEqual(result.moves[0].to_id, "C-02-3")
        pick = next(item for item in result.locations if item["id"] == "C-02-3")
        self.assertEqual(pick["qty"], 14)

    def test_locked_location_does_not_donate(self) -> None:
        result = fold(
            plan(
                locations=[
                    {
                        "aisle": "A",
                        "bay": 1,
                        "level": 1,
                        "sku": "SOAP",
                        "qty": 3,
                        "max_qty": 10,
                        "kind": "reserve",
                        "locked": True,
                    },
                    {
                        "aisle": "A",
                        "bay": 8,
                        "level": 1,
                        "sku": "SOAP",
                        "qty": 4,
                        "max_qty": 10,
                        "kind": "reserve",
                    },
                ]
            )
        )
        self.assertFalse(result.all_folded)
        self.assertEqual(result.moves, [])
        self.assertEqual(result.leftover[0]["reason"], "locked")

    def test_quality_hold_does_not_receive(self) -> None:
        result = fold(
            plan(
                locations=[
                    {
                        "aisle": "B",
                        "bay": 1,
                        "level": 1,
                        "sku": "MILK",
                        "qty": 2,
                        "max_qty": 10,
                        "kind": "reserve",
                        "hold": True,
                    },
                    {
                        "aisle": "B",
                        "bay": 4,
                        "level": 1,
                        "sku": "MILK",
                        "qty": 3,
                        "max_qty": 10,
                        "kind": "reserve",
                    },
                ]
            )
        )
        self.assertFalse(result.all_folded)
        reasons = {item["reason"] for item in result.leftover}
        self.assertIn("quality hold", reasons)

    def test_temperature_families_do_not_mix(self) -> None:
        result = fold(
            plan(
                locations=[
                    {
                        "aisle": "A",
                        "bay": 1,
                        "level": 1,
                        "sku": "JUICE",
                        "qty": 4,
                        "max_qty": 10,
                        "kind": "reserve",
                        "temp": "chill",
                    },
                    {
                        "aisle": "A",
                        "bay": 5,
                        "level": 1,
                        "sku": "JUICE",
                        "qty": 4,
                        "max_qty": 10,
                        "kind": "reserve",
                        "temp": "dry",
                    },
                ]
            )
        )
        self.assertTrue(result.all_folded)
        self.assertEqual(result.moves, [])

    def test_weight_cap_blocks_a_sink(self) -> None:
        result = fold(
            plan(
                locations=[
                    {
                        "aisle": "A",
                        "bay": 1,
                        "level": 1,
                        "sku": "HEAVY",
                        "qty": 4,
                        "max_qty": 10,
                        "kind": "reserve",
                        "unit_kg": 5,
                        "max_kg": 50,
                    },
                    {
                        "aisle": "A",
                        "bay": 6,
                        "level": 1,
                        "sku": "HEAVY",
                        "qty": 8,
                        "max_qty": 10,
                        "kind": "reserve",
                        "unit_kg": 5,
                        "max_kg": 45,
                    },
                ]
            )
        )
        self.assertFalse(result.all_folded)
        self.assertEqual(result.moves[0].qty, 1)
        leftover = next(item for item in result.leftover if item["id"] == "A-01-1")
        self.assertEqual(leftover["qty"], 3)
        self.assertEqual(leftover["reason"], "no sink capacity")

    def test_labor_cap_stops_after_two_trips(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "labor-capped.json"
        result = fold(FoldPlan.from_dict(json.loads(example.read_text())))
        self.assertFalse(result.all_folded)
        self.assertEqual(result.move_count, 2)
        self.assertEqual(result.labor_used, 8)
        reasons = {item["reason"] for item in result.leftover}
        self.assertIn("labor cap", reasons)
        self.assertIn("locked", reasons)
        self.assertIn("quality hold", reasons)

    def test_prefers_same_aisle_over_fuller_cross_aisle(self) -> None:
        result = fold(
            plan(
                locations=[
                    {
                        "aisle": "A",
                        "bay": 2,
                        "level": 1,
                        "sku": "TEE",
                        "qty": 3,
                        "max_qty": 12,
                        "kind": "reserve",
                    },
                    {
                        "aisle": "A",
                        "bay": 9,
                        "level": 1,
                        "sku": "TEE",
                        "qty": 5,
                        "max_qty": 12,
                        "kind": "reserve",
                    },
                    {
                        "aisle": "C",
                        "bay": 2,
                        "level": 1,
                        "sku": "TEE",
                        "qty": 8,
                        "max_qty": 12,
                        "kind": "reserve",
                    },
                ]
            )
        )
        self.assertEqual(result.moves[0].to_id, "A-09-1")

    def test_volume_and_labor_utilization_are_ratios(self) -> None:
        result = fold(plan())
        self.assertGreater(result.labor_utilization, 0)
        self.assertLessEqual(result.labor_utilization, 1)


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_locations(self) -> None:
        with self.assertRaises(ValueError):
            FoldPlan.from_dict(
                {
                    "warehouse": {"preset": "small_dc"},
                    "locations": [
                        {
                            "aisle": "A",
                            "bay": 1,
                            "level": 1,
                            "sku": "A",
                            "qty": 1,
                            "max_qty": 4,
                        },
                        {
                            "aisle": "A",
                            "bay": 1,
                            "level": 1,
                            "sku": "B",
                            "qty": 1,
                            "max_qty": 4,
                        },
                    ],
                }
            )

    def test_rejects_empty_plan(self) -> None:
        with self.assertRaises(ValueError):
            FoldPlan.from_dict({"warehouse": {"preset": "small_dc"}, "locations": []})

    def test_rejects_location_outside_grid(self) -> None:
        with self.assertRaises(ValueError):
            FoldPlan.from_dict(
                {
                    "warehouse": {"preset": "small_dc"},
                    "locations": [
                        {
                            "aisle": "Z",
                            "bay": 1,
                            "level": 1,
                            "sku": "A",
                            "qty": 1,
                            "max_qty": 4,
                        }
                    ],
                }
            )

    def test_location_id_pads_bay(self) -> None:
        loc = Location(aisle="B", bay=2, level=1, sku="X", qty=1, max_qty=4)
        self.assertEqual(loc.id, "B-02-1")


if __name__ == "__main__":
    unittest.main()
