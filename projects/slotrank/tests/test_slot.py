from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from slotrank.model import SlotPlan
from slotrank.slot import classify_abc, slot
from slotrank.warehouses import generate_locations, get_warehouse


def sku(
    name: str,
    picks: int,
    current: str = "",
    cube: int = 8,
    weight_kg: float = 2,
    slot_type: str = "case",
    family: str = "",
    heavy: bool | None = None,
) -> dict:
    row = {
        "sku": name,
        "picks": picks,
        "cube": cube,
        "weight_kg": weight_kg,
        "slot_type": slot_type,
        "family": family,
        "current": current,
    }
    if heavy is not None:
        row["heavy"] = heavy
    return row


def plan(**kwargs) -> SlotPlan:
    payload = {
        "warehouse": {"preset": "mini_3"},
        "strategy": "auto",
        "skus": [sku("MILK", 40, "A3-04")],
    }
    payload.update(kwargs)
    return SlotPlan.from_dict(payload)


class AbcTests(unittest.TestCase):
    def test_bands_follow_cumulative_picks(self) -> None:
        from slotrank.model import Sku

        items = [
            Sku("A1", 100, 8, 1, "case"),
            Sku("A2", 40, 8, 1, "case"),
            Sku("B1", 20, 8, 1, "case"),
            Sku("B2", 10, 8, 1, "case"),
            Sku("C1", 5, 8, 1, "case"),
        ]
        classes = classify_abc(items, 0.80, 0.15)
        self.assertEqual(classes["A1"], "A")
        self.assertEqual(classes["A2"], "A")
        self.assertEqual(classes["B1"], "B")
        self.assertEqual(classes["B2"], "B")
        self.assertEqual(classes["C1"], "C")

    def test_zero_picks_are_all_c(self) -> None:
        from slotrank.model import Sku

        items = [Sku("X", 0, 8, 1, "case"), Sku("Y", 0, 8, 1, "case")]
        self.assertEqual(classify_abc(items, 0.80, 0.15), {"X": "C", "Y": "C"})


class SlotTests(unittest.TestCase):
    def test_fast_mover_takes_golden_zone(self) -> None:
        result = slot(plan(skus=[sku("MILK", 80, "A3-04"), sku("CANDLE", 2, "A1-01")]))
        milk = next(item for item in result.placements if item.sku.sku == "MILK")
        self.assertEqual(milk.abc, "A")
        self.assertIsNotNone(milk.location)
        assert milk.location is not None
        self.assertTrue(result.warehouse.is_golden(milk.location.aisle, milk.location.bay))
        self.assertGreater(result.a_golden_after, result.a_golden_before)

    def test_already_home_is_kept(self) -> None:
        result = slot(plan(skus=[sku("MILK", 80, "A1-01")]))
        self.assertTrue(result.all_slotted)
        self.assertEqual(result.keep_count, 1)
        self.assertEqual(result.move_count, 0)
        self.assertEqual(result.placements[0].status, "keep")
        self.assertEqual(result.placements[0].location.id, "A1-01")

    def test_type_mismatch_is_leftover(self) -> None:
        result = slot(plan(skus=[sku("EACH", 20, slot_type="piece")]))
        self.assertFalse(result.all_slotted)
        self.assertEqual(result.leftover[0]["reason"], "no-slot")

    def test_cube_overflow_is_leftover(self) -> None:
        result = slot(plan(skus=[sku("TOTE", 20, cube=200)]))
        self.assertEqual(result.leftover[0]["reason"], "no-slot")

    def test_heavy_needs_floor_bay(self) -> None:
        result = slot(
            plan(
                strategy="heavy",
                skus=[sku("OIL", 30, "A2-03", weight_kg=18, heavy=True)],
            )
        )
        oil = result.placements[0]
        self.assertIsNotNone(oil.location)
        assert oil.location is not None
        self.assertTrue(oil.location.allow_heavy)
        self.assertEqual(oil.location.bay, 1)

    def test_no_heavy_slot_reason(self) -> None:
        result = slot(
            SlotPlan.from_dict(
                {
                    "warehouse": {"preset": "mini_3", "heavy_bays": []},
                    "skus": [sku("OIL", 20, weight_kg=18, heavy=True)],
                }
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "no-heavy-slot")

    def test_affinity_keeps_family_on_one_aisle(self) -> None:
        result = slot(
            plan(
                strategy="affinity",
                skus=[
                    sku("TEA-A", 50, "A3-04", family="tea"),
                    sku("TEA-B", 40, "A2-04", family="tea"),
                    sku("TEA-C", 12, "A3-03", family="tea"),
                    sku("CABLE", 8, "A1-04", family="tech"),
                ],
            )
        )
        tea = [item for item in result.placements if item.sku.family == "tea" and item.location]
        aisles = {item.location.aisle for item in tea}
        self.assertEqual(len(aisles), 1)

    def test_labor_cap_marks_later_moves(self) -> None:
        result = slot(
            SlotPlan.from_dict(
                {
                    "warehouse": {
                        "preset": "mini_3",
                        "max_labor_min": 14,
                        "minutes_per_move": 5,
                        "aisle_change_min": 2,
                    },
                    "strategy": "velocity",
                    "skus": [
                        sku("MILK", 200, "A3-04"),
                        sku("BREAD", 160, "A3-03"),
                        sku("EGGS", 140, "A3-02"),
                        sku("SPICE", 6, "A1-01"),
                    ],
                }
            )
        )
        self.assertGreaterEqual(result.move_count, 1)
        self.assertGreaterEqual(result.later_count, 1)
        self.assertTrue(any(item["reason"] == "capped" for item in result.leftover))
        self.assertLessEqual(result.labor_min, 14)
        self.assertEqual(main_exit_if_capped(result), 2)

    def test_move_cap_stops_after_one(self) -> None:
        result = slot(
            SlotPlan.from_dict(
                {
                    "warehouse": {"preset": "mini_3", "max_moves": 1},
                    "strategy": "velocity",
                    "skus": [
                        sku("MILK", 80, "A3-04"),
                        sku("BREAD", 70, "A3-03"),
                        sku("CANDLE", 2, "A2-04"),
                    ],
                }
            )
        )
        self.assertEqual(result.move_count, 1)
        self.assertGreaterEqual(result.later_count, 1)

    def test_travel_falls_when_a_moves_forward(self) -> None:
        result = slot(plan(skus=[sku("MILK", 90, "A3-04"), sku("CANDLE", 3, "A1-02")]))
        self.assertLess(result.travel_after, result.travel_before)

    def test_generated_grid_matches_layout(self) -> None:
        house = get_warehouse({"preset": "grocery_6"})
        locations = generate_locations(house)
        self.assertEqual(len(locations), 48)
        self.assertTrue(any(loc.id == "A1-01" and loc.allow_heavy for loc in locations))
        self.assertFalse(next(loc for loc in locations if loc.id == "A2-03").allow_heavy)

    def test_example_grocery_improves_golden_share(self) -> None:
        path = Path(__file__).resolve().parents[1] / "examples" / "mis-slotted-grocery.json"
        result = slot(SlotPlan.from_dict(json.loads(path.read_text())))
        self.assertGreater(result.a_golden_after, result.a_golden_before)
        self.assertGreater(result.move_count, 0)
        milk = next(item for item in result.placements if item.sku.sku == "MILK-1L")
        self.assertTrue(milk.golden)

    def test_duplicate_sku_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan(skus=[sku("MILK", 10), sku("MILK", 8)])


def main_exit_if_capped(result) -> int:
    return 0 if result.all_slotted else 2


class ModelTests(unittest.TestCase):
    def test_custom_warehouse(self) -> None:
        result = slot(
            SlotPlan.from_dict(
                {
                    "warehouse": {
                        "name": "Tiny",
                        "aisle_count": 2,
                        "bays_per_aisle": 3,
                        "golden_aisles": 1,
                        "golden_bays": 2,
                        "default_slot_type": "piece",
                        "default_max_cube": 10,
                        "max_moves": 4,
                        "max_labor_min": 30,
                        "minutes_per_move": 4,
                    },
                    "skus": [sku("USB", 12, slot_type="piece")],
                }
            )
        )
        self.assertTrue(result.all_slotted)
        self.assertEqual(result.warehouse.id, "custom")
        self.assertEqual(len(result.locations), 6)
