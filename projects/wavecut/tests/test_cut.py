from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wavecut.cut import cut
from wavecut.model import Order, WavePlan
from wavecut.shifts import get_shift


def plan(**kwargs) -> WavePlan:
    payload = {
        "shift": {"preset": "mini_3"},
        "strategy": "auto",
        "orders": [
            {
                "id": "A1",
                "channel": "store",
                "zone": "ambient",
                "lines": 2,
                "units": 8,
                "cube_m3": 0.3,
                "pick_min": 15,
                "cutoff": "10:00",
            }
        ],
    }
    payload.update(kwargs)
    return WavePlan.from_dict(payload)


class CutTests(unittest.TestCase):
    def test_single_order_takes_first_wave(self) -> None:
        result = cut(plan())
        self.assertTrue(result.all_cut)
        self.assertEqual(len(result.assignments), 1)
        item = result.assignments[0]
        self.assertEqual(item.wave.id, "W1")
        self.assertEqual(item.wave.start_min, 8 * 60)
        self.assertEqual(item.order.id, "A1")

    def test_order_that_misses_first_wave_start_plus_pick(self) -> None:
        result = cut(
            plan(
                orders=[
                    {
                        "id": "LATE",
                        "channel": "ecom",
                        "zone": "ambient",
                        "lines": 2,
                        "units": 2,
                        "cube_m3": 0.2,
                        "pick_min": 20,
                        "cutoff": "08:10",
                    }
                ]
            )
        )
        self.assertFalse(result.all_cut)
        self.assertEqual(result.leftover[0]["id"], "LATE")
        self.assertIn("misses every cutoff window", result.leftover[0]["reason"])

    def test_over_cube_is_leftover(self) -> None:
        result = cut(
            plan(
                orders=[
                    {
                        "id": "HUGE",
                        "channel": "wholesale",
                        "zone": "bulk",
                        "lines": 4,
                        "units": 20,
                        "cube_m3": 3.5,
                        "pick_min": 20,
                        "cutoff": "12:00",
                    }
                ]
            )
        )
        self.assertEqual(result.leftover[0]["id"], "HUGE")
        self.assertIn("over cube", result.leftover[0]["reason"])

    def test_over_lines_is_leftover(self) -> None:
        result = cut(
            plan(
                orders=[
                    {
                        "id": "FAT",
                        "channel": "store",
                        "zone": "ambient",
                        "lines": 40,
                        "units": 40,
                        "cube_m3": 0.4,
                        "pick_min": 20,
                        "cutoff": "12:00",
                    }
                ]
            )
        )
        self.assertIn("over lines", result.leftover[0]["reason"])

    def test_capacity_spills_to_next_wave(self) -> None:
        result = cut(
            plan(
                orders=[
                    {
                        "id": f"O{n}",
                        "channel": "store",
                        "zone": "ambient",
                        "lines": 4,
                        "units": 8,
                        "cube_m3": 0.4,
                        "pick_min": 18,
                        "cutoff": "12:00",
                    }
                    for n in range(4)
                ]
            )
        )
        self.assertTrue(result.all_cut)
        by_wave: dict[str, list[str]] = {}
        for item in result.assignments:
            by_wave.setdefault(item.wave.id, []).append(item.order.id)
        self.assertEqual(len(by_wave["W1"]), 3)
        self.assertEqual(len(by_wave["W2"]), 1)

    def test_priority_and_cutoff_order_first_wave(self) -> None:
        result = cut(
            plan(
                strategy="cutoff",
                orders=[
                    {
                        "id": "LOOSE",
                        "channel": "store",
                        "zone": "ambient",
                        "lines": 2,
                        "units": 4,
                        "cube_m3": 0.3,
                        "pick_min": 50,
                        "cutoff": "12:00",
                        "priority": 3,
                    },
                    {
                        "id": "TIGHT",
                        "channel": "ecom",
                        "zone": "ambient",
                        "lines": 2,
                        "units": 4,
                        "cube_m3": 0.3,
                        "pick_min": 50,
                        "cutoff": "09:30",
                        "priority": 1,
                    },
                ],
            )
        )
        self.assertTrue(result.all_cut)
        first = min(result.assignments, key=lambda item: (item.wave.start_min, item.order.id))
        tight = next(item for item in result.assignments if item.order.id == "TIGHT")
        self.assertEqual(tight.wave.id, "W1")
        self.assertEqual(first.order.id, "TIGHT")
        loose = next(item for item in result.assignments if item.order.id == "LOOSE")
        self.assertEqual(loose.wave.id, "W2")

    def test_zone_pure_keeps_zones_apart(self) -> None:
        result = cut(
            WavePlan.from_dict(
                {
                    "shift": {"preset": "wholesale_pm"},
                    "strategy": "zone",
                    "orders": [
                        {
                            "id": "AMB",
                            "channel": "wholesale",
                            "zone": "ambient",
                            "lines": 6,
                            "units": 30,
                            "cube_m3": 1.0,
                            "pick_min": 20,
                            "cutoff": "16:00",
                        },
                        {
                            "id": "CHILL",
                            "channel": "wholesale",
                            "zone": "chill",
                            "lines": 6,
                            "units": 30,
                            "cube_m3": 1.0,
                            "pick_min": 20,
                            "cutoff": "16:00",
                            "priority": 1,
                        },
                    ],
                }
            )
        )
        self.assertTrue(result.all_cut)
        waves = {item.order.id: item.wave for item in result.assignments}
        self.assertNotEqual(waves["AMB"].id, waves["CHILL"].id)
        self.assertEqual(waves["AMB"].zone, "ambient")
        self.assertEqual(waves["CHILL"].zone, "chill")

    def test_auto_prefers_existing_zone_wave(self) -> None:
        result = cut(
            plan(
                strategy="auto",
                orders=[
                    {
                        "id": "AMB-1",
                        "channel": "store",
                        "zone": "ambient",
                        "lines": 2,
                        "units": 4,
                        "cube_m3": 0.2,
                        "pick_min": 10,
                        "cutoff": "11:00",
                        "priority": 1,
                    },
                    {
                        "id": "CHILL-1",
                        "channel": "store",
                        "zone": "chill",
                        "lines": 2,
                        "units": 4,
                        "cube_m3": 0.2,
                        "pick_min": 10,
                        "cutoff": "11:00",
                        "priority": 1,
                    },
                    {
                        "id": "AMB-2",
                        "channel": "store",
                        "zone": "ambient",
                        "lines": 2,
                        "units": 4,
                        "cube_m3": 0.2,
                        "pick_min": 10,
                        "cutoff": "11:30",
                    },
                ],
            )
        )
        amb2 = next(item for item in result.assignments if item.order.id == "AMB-2")
        amb1 = next(item for item in result.assignments if item.order.id == "AMB-1")
        self.assertEqual(amb2.wave.id, amb1.wave.id)

    def test_wave_caps_are_not_exceeded(self) -> None:
        result = cut(
            WavePlan.from_dict(
                {
                    "shift": {"preset": "grocery_am"},
                    "orders": [
                        {
                            "id": f"SO-{n}",
                            "channel": "store",
                            "zone": "ambient",
                            "lines": 6,
                            "units": 20,
                            "cube_m3": 0.4,
                            "pick_min": 20,
                            "cutoff": "12:00",
                        }
                        for n in range(8)
                    ],
                }
            )
        )
        self.assertTrue(result.all_cut)
        shift = result.shift
        for wave in result.used_waves:
            self.assertLessEqual(len(wave.orders), shift.max_orders)
            self.assertLessEqual(wave.lines, shift.max_lines)
            self.assertLessEqual(wave.cube_m3, shift.max_cube_m3 + 1e-9)
            self.assertLessEqual(wave.pick_min, shift.max_pick_min)
            for order in wave.orders:
                self.assertLessEqual(wave.start_min + order.pick_min, order.cutoff_min)

    def test_morning_stores_example_all_fits(self) -> None:
        payload = Path(__file__).resolve().parents[1] / "examples" / "morning-stores.json"
        result = cut(WavePlan.from_dict(json.loads(payload.read_text())))
        self.assertTrue(result.all_cut)
        self.assertEqual(result.assigned_count, 8)
        self.assertGreaterEqual(len(result.used_waves), 2)

    def test_zone_batch_example_separates_zones(self) -> None:
        payload = Path(__file__).resolve().parents[1] / "examples" / "zone-batch.json"
        result = cut(WavePlan.from_dict(json.loads(payload.read_text())))
        self.assertTrue(result.all_cut)
        zones = {wave.zone for wave in result.used_waves}
        self.assertEqual(zones, {"ambient", "chill"})
        for wave in result.used_waves:
            self.assertNotEqual(wave.zone, "mixed")

    def test_missed_cutoff_example(self) -> None:
        payload = Path(__file__).resolve().parents[1] / "examples" / "missed-cutoff.json"
        result = cut(WavePlan.from_dict(json.loads(payload.read_text())))
        self.assertFalse(result.all_cut)
        leftover = {item["id"]: item["reason"] for item in result.leftover}
        self.assertIn("LATE", leftover)
        self.assertIn("HUGE", leftover)
        self.assertIn("misses every cutoff window", leftover["LATE"])
        self.assertIn("over cube", leftover["HUGE"])
        assigned = {item.order.id for item in result.assignments}
        self.assertEqual(assigned, {"KEEP-A", "KEEP-B"})

    def test_custom_shift_from_dict(self) -> None:
        shift = get_shift(
            {
                "name": "One wave",
                "open": "09:00",
                "close": "10:00",
                "wave_min": 60,
                "max_orders": 2,
                "max_lines": 10,
                "max_cube_m3": 1.0,
                "max_pick_min": 40,
            }
        )
        result = cut(
            WavePlan(
                shift=shift,
                orders=[
                    Order(
                        id="OK",
                        channel="other",
                        zone="ambient",
                        lines=2,
                        units=2,
                        cube_m3=0.2,
                        pick_min=10,
                        cutoff="10:00",
                    )
                ],
            )
        )
        self.assertTrue(result.all_cut)
        self.assertEqual(result.assignments[0].wave.id, "W1")

    def test_cube_strategy_places_largest_first(self) -> None:
        result = cut(
            plan(
                strategy="cube",
                orders=[
                    {
                        "id": "SMALL",
                        "channel": "store",
                        "zone": "ambient",
                        "lines": 2,
                        "units": 2,
                        "cube_m3": 0.2,
                        "pick_min": 40,
                        "cutoff": "12:00",
                    },
                    {
                        "id": "BIG",
                        "channel": "store",
                        "zone": "ambient",
                        "lines": 2,
                        "units": 2,
                        "cube_m3": 1.4,
                        "pick_min": 40,
                        "cutoff": "12:00",
                    },
                ],
            )
        )
        self.assertTrue(result.all_cut)
        big = next(item for item in result.assignments if item.order.id == "BIG")
        small = next(item for item in result.assignments if item.order.id == "SMALL")
        self.assertEqual(big.wave.id, "W1")
        self.assertEqual(small.wave.id, "W2")
