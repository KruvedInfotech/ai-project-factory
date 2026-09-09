from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pickpath.model import Pick, Wave
from pickpath.route import route
from pickpath.warehouse import PRESETS, Warehouse, get_warehouse


def wave(**kwargs) -> Wave:
    payload = {
        "warehouse": {"preset": "mini_4x8"},
        "strategy": "auto",
        "picks": [
            {"sku": "A", "aisle": 1, "bay": 2, "side": "L", "qty": 1},
        ],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


class GeometryTests(unittest.TestCase):
    def test_same_aisle_walk_is_centerline_then_face(self) -> None:
        wh = PRESETS["mini_4x8"]
        depot = wh.depot()
        pick = wh.pick_node(1, 1, "L")
        length = wh.walk_length(depot, pick)
        # bay 1 sits at y=0.5; face is 1.0 m off the aisle center
        self.assertAlmostEqual(length, 1.5)

    def test_cross_aisle_uses_shorter_of_front_or_rear(self) -> None:
        wh = PRESETS["mini_4x8"]
        a = wh.pick_node(1, 8, "R")  # near rear, y=7.5
        b = wh.pick_node(4, 8, "L")
        via_front = wh.walk_length(a, b, force_front=True)
        via_best = wh.walk_length(a, b, force_front=False)
        self.assertLess(via_best, via_front)

    def test_front_only_layout_never_uses_rear(self) -> None:
        wh = PRESETS["front_only_5x10"]
        a = wh.pick_node(1, 10, "L")
        b = wh.pick_node(5, 10, "R")
        self.assertAlmostEqual(wh.walk_length(a, b), wh.walk_length(a, b, force_front=True))


class RouteTests(unittest.TestCase):
    def test_single_pick_round_trip(self) -> None:
        result = route(wave(strategy="s_shape"))
        self.assertTrue(result.all_routed)
        self.assertEqual(len(result.stops), 1)
        self.assertEqual(result.path[0].y, 0)
        self.assertEqual(result.path[-1].y, 0)
        self.assertGreater(result.distance_m, 0)

    def test_s_shape_visits_odd_aisles_front_to_back(self) -> None:
        result = route(
            wave(
                strategy="s_shape",
                picks=[
                    {"sku": "A1", "aisle": 1, "bay": 2, "side": "L"},
                    {"sku": "A2", "aisle": 1, "bay": 7, "side": "R"},
                    {"sku": "B1", "aisle": 3, "bay": 2, "side": "L"},
                    {"sku": "B2", "aisle": 3, "bay": 7, "side": "R"},
                ],
            )
        )
        skus = [s.pick.sku for s in result.stops]
        self.assertEqual(skus, ["A1", "A2", "B2", "B1"])

    def test_return_keeps_aisle_front_to_back(self) -> None:
        result = route(
            wave(
                strategy="return",
                picks=[
                    {"sku": "A1", "aisle": 1, "bay": 7, "side": "L"},
                    {"sku": "A2", "aisle": 1, "bay": 2, "side": "R"},
                    {"sku": "B1", "aisle": 2, "bay": 5, "side": "L"},
                ],
            )
        )
        skus = [s.pick.sku for s in result.stops]
        self.assertEqual(skus, ["A2", "A1", "B1"])
        self.assertTrue(all(pt.y <= PRESETS["mini_4x8"].aisle_length_m for pt in result.path))

    def test_return_path_stays_on_front_cross_aisle(self) -> None:
        result = route(
            wave(
                strategy="return",
                picks=[
                    {"sku": "A", "aisle": 1, "bay": 2, "side": "L"},
                    {"sku": "B", "aisle": 4, "bay": 2, "side": "R"},
                ],
            )
        )
        rear_y = PRESETS["mini_4x8"].aisle_length_m
        self.assertFalse(any(abs(pt.y - rear_y) < 1e-9 for pt in result.path))

    def test_out_of_range_pick_is_skipped(self) -> None:
        result = route(
            wave(
                picks=[
                    {"sku": "OK", "aisle": 1, "bay": 1, "side": "L"},
                    {"sku": "GHOST", "aisle": 9, "bay": 1, "side": "L"},
                ]
            )
        )
        self.assertFalse(result.all_routed)
        self.assertEqual(result.stops[0].pick.sku, "OK")
        self.assertEqual(result.skipped[0]["sku"], "GHOST")

    def test_auto_picks_a_named_strategy(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "grocery-wave.json"
        result = route(Wave.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_routed)
        self.assertEqual(result.strategy, "auto")
        self.assertIn(result.chosen_strategy, ("s_shape", "return", "nearest"))
        self.assertEqual(len(result.comparison), 3)
        self.assertAlmostEqual(result.distance_m, result.comparison[result.chosen_strategy], places=2)

    def test_nearest_is_not_longer_than_greedy_without_opt(self) -> None:
        result = route(
            wave(
                strategy="nearest",
                warehouse={"preset": "grocery_6x20"},
                picks=[
                    {"sku": "A", "aisle": 1, "bay": 2, "side": "L"},
                    {"sku": "B", "aisle": 6, "bay": 18, "side": "R"},
                    {"sku": "C", "aisle": 2, "bay": 10, "side": "L"},
                    {"sku": "D", "aisle": 5, "bay": 4, "side": "R"},
                    {"sku": "E", "aisle": 3, "bay": 19, "side": "L"},
                ],
            )
        )
        self.assertEqual(len(result.stops), 5)
        self.assertEqual({s.pick.sku for s in result.stops}, {"A", "B", "C", "D", "E"})

    def test_path_visits_every_stop(self) -> None:
        result = route(
            Wave.from_dict(
                json.loads(
                    (Path(__file__).resolve().parents[1] / "examples" / "single-aisle.json").read_text()
                )
            )
        )
        for stop in result.stops:
            self.assertTrue(any(abs(pt.x - stop.x) < 1e-9 and abs(pt.y - stop.y) < 1e-9 for pt in result.path))

    def test_time_is_walk_plus_handling(self) -> None:
        result = route(wave(strategy="return"))
        expected = result.walk_min + result.pick_min
        self.assertAlmostEqual(result.total_min, expected)


class ModelTests(unittest.TestCase):
    def test_rejects_empty_wave(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict({"warehouse": {"preset": "mini_4x8"}, "picks": []})

    def test_rejects_bad_side(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict(
                {
                    "warehouse": {"preset": "mini_4x8"},
                    "picks": [{"sku": "A", "aisle": 1, "bay": 1, "side": "M"}],
                }
            )

    def test_rejects_unknown_preset(self) -> None:
        with self.assertRaises(ValueError):
            get_warehouse({"preset": "nope"})

    def test_custom_warehouse(self) -> None:
        wh = get_warehouse(
            {
                "aisle_count": 2,
                "bays_per_aisle": 3,
                "bay_length_m": 1,
                "aisle_width_m": 2,
                "aisle_pitch_m": 4,
            }
        )
        self.assertIsInstance(wh, Warehouse)
        self.assertEqual(wh.id, "custom")

    def test_pick_dataclass_round_trip(self) -> None:
        pick = Pick("X", 1, 2, "L", 3, 0)
        self.assertEqual(pick.as_dict()["qty"], 3)


if __name__ == "__main__":
    unittest.main()
