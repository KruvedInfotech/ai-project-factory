from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aislelock.lock import LockResult, lock
from aislelock.model import CartSpec, Wave, parse_walk

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def cart(cart_id: str, walk: str, **kwargs) -> dict:
    row = {
        "id": cart_id,
        "priority": 2,
        "temp": "dry",
        "bulky": False,
        "ready_min": 0,
        "walk": walk,
    }
    row.update(kwargs)
    return row


def wave(**kwargs) -> Wave:
    payload = {
        "floor": {"preset": "grocery"},
        "strategy": "auto",
        "carts": [cart("CART-1", "A:1")],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


class LockTests(unittest.TestCase):
    def test_single_cart_locks_at_origin(self) -> None:
        result = lock(wave())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.locked_count, 1)
        booked = result.locks[0]
        self.assertEqual(booked.cart_id, "CART-1")
        self.assertEqual(booked.start_min, 0)
        self.assertEqual(booked.visits[0].aisle, "A")
        self.assertEqual(booked.visits[0].start_min, 0)
        self.assertEqual(booked.visits[0].end_min, 5)

    def test_two_carts_overlap_on_a_wide_aisle(self) -> None:
        result = lock(
            wave(
                carts=[
                    cart("LEFT", "A:0"),
                    cart("RIGHT", "A:0"),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        starts = sorted(item.start_min for item in result.locks)
        self.assertEqual(starts, [0, 0])
        used = [item for item in result.occupancy if item.aisle == "A"]
        self.assertEqual(len(used), 2)

    def test_third_cart_waits_when_grocery_aisle_is_full(self) -> None:
        result = lock(
            wave(
                carts=[
                    cart("ONE", "A:0", priority=1),
                    cart("TWO", "A:0", priority=1),
                    cart("THREE", "A:0", priority=2),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.cart_id: item for item in result.locks}
        self.assertEqual(by_id["ONE"].start_min, 0)
        self.assertEqual(by_id["TWO"].start_min, 0)
        self.assertEqual(by_id["THREE"].start_min, 4)

    def test_second_cart_waits_on_vna_then_leftover_if_cutoff_is_tight(self) -> None:
        waiting = lock(
            Wave.from_dict(
                {
                    "floor": {"preset": "vna"},
                    "carts": [
                        cart("FIRST", "A:0", priority=1),
                        cart("SECOND", "A:0", priority=2, cutoff_min=80),
                    ],
                }
            )
        )
        self.assertTrue(waiting.all_fit)
        by_id = {item.cart_id: item for item in waiting.locks}
        self.assertEqual(by_id["FIRST"].start_min, 0)
        self.assertEqual(by_id["FIRST"].end_min, 10)
        self.assertEqual(by_id["SECOND"].start_min, 10)

        blocked = lock(Wave.from_dict(json.loads((EXAMPLES / "narrow-busy.json").read_text())))
        self.assertFalse(blocked.all_fit)
        self.assertEqual(blocked.locks[0].cart_id, "CART-01")
        self.assertEqual(blocked.locks[0].end_min, 11)
        self.assertEqual(blocked.leftover[0]["id"], "CART-02")
        self.assertEqual(blocked.leftover[0]["reason"], "aisle-busy")

    def test_bulky_cart_takes_the_whole_aisle(self) -> None:
        result = lock(
            Wave.from_dict(
                {
                    "floor": {"preset": "ecom"},
                    "exclusive_bulky": True,
                    "carts": [
                        cart("SOFA", "A:0", bulky=True, priority=1),
                        cart("TOTE", "A:0", priority=2),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.cart_id: item for item in result.locks}
        self.assertEqual(by_id["SOFA"].start_min, 0)
        self.assertEqual(by_id["SOFA"].visits[0].slots, 3)
        self.assertEqual(by_id["TOTE"].start_min, 3)

    def test_bulky_shares_when_exclusive_is_off(self) -> None:
        result = lock(
            Wave.from_dict(
                {
                    "floor": {"preset": "ecom"},
                    "exclusive_bulky": False,
                    "carts": [
                        cart("SOFA", "A:0", bulky=True, priority=1),
                        cart("TOTE", "A:0", priority=2),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        starts = sorted(item.start_min for item in result.locks)
        self.assertEqual(starts, [0, 0])

    def test_hop_minutes_sit_between_aisles(self) -> None:
        result = lock(
            Wave.from_dict(
                {
                    "floor": {
                        "aisles": [
                            {"id": "A", "capacity": 1, "minutes": 5, "temp": "dry"},
                            {"id": "C", "capacity": 1, "minutes": 5, "temp": "dry"},
                        ],
                        "minutes_per_cart": 0,
                        "minutes_per_pick": 0,
                        "minutes_per_hop": 3,
                        "horizon_min": 40,
                    },
                    "carts": [cart("HOP", "A:0 C:0")],
                }
            )
        )
        self.assertTrue(result.all_fit)
        visits = result.locks[0].visits
        self.assertEqual(visits[0].end_min, 5)
        self.assertEqual(visits[1].start_min, 8)
        self.assertEqual(visits[1].end_min, 13)

    def test_temp_split_keeps_dry_off_a_chill_floor(self) -> None:
        result = lock(Wave.from_dict(json.loads((EXAMPLES / "temp-block.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.locks[0].cart_id, "CART-40")
        self.assertEqual(result.leftover[0]["id"], "CART-41")
        self.assertEqual(result.leftover[0]["reason"], "temp")

    def test_unknown_aisle_is_left_behind(self) -> None:
        result = lock(wave(carts=[cart("LOST", "Z:1")]))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.locks, [])
        self.assertEqual(result.leftover[0]["reason"], "unknown-aisle")

    def test_labor_cap_blocks_the_second_cart(self) -> None:
        result = lock(Wave.from_dict(json.loads((EXAMPLES / "labor-capped.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.locked_count, 1)
        self.assertEqual(result.locks[0].cart_id, "CART-31")
        self.assertEqual(result.leftover[0]["id"], "CART-32")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")
        self.assertEqual(result.labor_used_min, 12)

    def test_cutoff_leftover_when_the_walk_is_already_too_long(self) -> None:
        result = lock(
            wave(
                carts=[cart("LATE", "A:3 B:2", cutoff_min=5)],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "cutoff")

    def test_cart_cap_blocks_a_third_lock(self) -> None:
        result = lock(
            wave(
                floor={"preset": "grocery", "max_carts": 1},
                carts=[cart("A1", "A:0"), cart("B1", "B:0")],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.locked_count, 1)
        self.assertEqual(result.leftover[0]["reason"], "cart-cap")

    def test_clear_wave_example_stays_inside_capacity(self) -> None:
        result = lock(Wave.from_dict(json.loads((EXAMPLES / "clear-wave.json").read_text())))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.locked_count, 4)
        self._assert_legal(result)
        by_id = {item.cart_id: item for item in result.locks}
        self.assertEqual(by_id["CART-11"].start_min, 0)
        self.assertEqual(by_id["CART-12"].start_min, 0)
        self.assertEqual(by_id["CART-11"].visits[0].end_min, 7)
        self.assertEqual(by_id["CART-11"].visits[1].start_min, 8)

    def test_cluster_groups_by_first_aisle(self) -> None:
        result = lock(
            wave(
                strategy="cluster",
                carts=[
                    cart("B-FIRST", "B:0", priority=1),
                    cart("A-FIRST", "A:0", priority=2),
                ],
            )
        )
        self.assertEqual([item.cart_id for item in result.locks], ["A-FIRST", "B-FIRST"])

    def _assert_legal(self, result: LockResult) -> None:
        lookup = result.floor.aisle_map()
        for aisle_id, aisle in lookup.items():
            visits = [item for item in result.occupancy if item.aisle == aisle_id]
            for item in visits:
                self.assertGreaterEqual(item.start_min, 0)
                self.assertLessEqual(item.end_min, result.floor.horizon_min)
                self.assertLessEqual(item.slots, aisle.capacity)
            times = sorted({item.start_min for item in visits} | {item.end_min for item in visits})
            for time in times:
                used = sum(
                    item.slots
                    for item in visits
                    if item.start_min <= time < item.end_min
                )
                self.assertLessEqual(used, aisle.capacity, f"{aisle_id} over capacity at {time}")


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_cart_id(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict(
                {
                    "floor": {"preset": "grocery"},
                    "carts": [cart("A", "A:1"), cart("A", "B:1")],
                }
            )

    def test_rejects_empty_wave(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict({"floor": {"preset": "grocery"}, "carts": []})

    def test_rejects_empty_walk(self) -> None:
        with self.assertRaises(ValueError):
            CartSpec(id="X", walk=()).validate()

    def test_parse_walk_string(self) -> None:
        steps = parse_walk("A:3, B:2", "CART")
        self.assertEqual([step.aisle for step in steps], ["A", "B"])
        self.assertEqual([step.picks for step in steps], [3, 2])


if __name__ == "__main__":
    unittest.main()
