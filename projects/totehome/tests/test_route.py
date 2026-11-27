from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from totehome.model import Floor
from totehome.route import manhattan, plan, stacks_for, take_load, travel_sec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(name: str) -> Floor:
    payload = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return Floor.from_dict(payload)


def floor(**kwargs) -> Floor:
    payload = {
        "homes": [
            {
                "id": "IND-1",
                "kind": "induction",
                "x_m": 0,
                "y_m": 0,
                "accepts": ["std"],
                "drop_sec_per_stack": 10,
            }
        ],
        "carts": [
            {
                "id": "C1",
                "stack_cap": 4,
                "speed_m_per_min": 60,
                "load_sec_per_stack": 10,
                "shift_min": 30,
            }
        ],
        "stations": [
            {
                "id": "PACK-A",
                "kind": "pack",
                "x_m": 20,
                "y_m": 0,
                "threshold": 8,
                "cap": 24,
                "minutes_since_pickup": 10,
                "piles": [{"tote": "std", "count": 12}],
            }
        ],
    }
    payload.update(kwargs)
    return Floor.from_dict(payload)


class GeometryTests(unittest.TestCase):
    def test_manhattan_is_l1(self) -> None:
        self.assertEqual(manhattan((0, 0), (10, 4)), 14)

    def test_travel_rounds_up(self) -> None:
        # 10 m at 60 m/min = 10 s. 10 m at 31 m/min = ceil(19.35) = 20 s.
        self.assertEqual(travel_sec((0, 0), (10, 0), 60), 10)
        self.assertEqual(travel_sec((0, 0), (10, 0), 31), 20)
        self.assertEqual(travel_sec((0, 0), (0, 0), 60), 0)

    def test_partial_nest_still_uses_one_stack(self) -> None:
        self.assertEqual(stacks_for(12, 20), 1)
        self.assertEqual(stacks_for(20, 20), 1)
        self.assertEqual(stacks_for(21, 20), 2)
        self.assertEqual(take_load(25, 1, 20), (20, 1))
        self.assertEqual(take_load(12, 4, 20), (12, 1))


class RouteTests(unittest.TestCase):
    def test_quiet_aisle_clears_both_packs(self) -> None:
        result = plan(load("quiet-aisle.json"))
        self.assertTrue(result.all_fit)
        self.assertEqual(len(result.trips), 1)
        self.assertEqual(result.collected, 20)
        self.assertEqual(result.makespan_sec, 120)
        trip = result.trips[0]
        self.assertEqual([stop.station for stop in trip.stops], ["PACK-A", "PACK-B"])
        self.assertEqual(trip.home, "IND-1")
        self.assertEqual(trip.start_sec, 0)
        self.assertEqual(trip.finish_sec, 120)

    def test_overflow_station_is_first_stop(self) -> None:
        result = plan(load("overflow-pack.json"))
        self.assertTrue(result.all_fit)
        trip = result.trips[0]
        self.assertEqual(trip.stops[0].station, "PACK-HOT")
        self.assertEqual(trip.stops[0].totes, 22)
        self.assertEqual([stop.station for stop in trip.stops], ["PACK-HOT", "PACK-OK"])
        self.assertEqual(result.collected, 34)
        self.assertEqual(result.makespan_sec, 120)

    def test_mixed_types_do_not_share_a_trip(self) -> None:
        result = plan(load("mixed-types.json"))
        self.assertTrue(result.all_fit)
        self.assertEqual(len(result.trips), 2)
        types = [trip.tote for trip in result.trips]
        self.assertEqual(types, ["std", "cold"])
        self.assertEqual(result.trips[0].home, "IND-1")
        self.assertEqual(result.trips[1].home, "WASH-1")
        for trip in result.trips:
            self.assertEqual({stop.tote for stop in trip.stops}, {trip.tote})
        self.assertEqual(result.makespan_sec, 162)

    def test_short_shift_leaves_the_far_station(self) -> None:
        result = plan(load("shift-short.json"))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.collected, 10)
        self.assertEqual([stop.station for stop in result.trips[0].stops], ["NEAR"])
        leftover = {(item["station"], item["tote"]) for item in result.leftover}
        self.assertEqual(leftover, {("FAR", "std")})
        self.assertEqual(result.leftover[0]["reason"], "no cart free before shift end")

    def test_opportunistic_grabs_below_threshold_neighbour(self) -> None:
        result = plan(load("opportunistic.json"))
        self.assertTrue(result.all_fit)
        self.assertEqual(len(result.trips), 1)
        self.assertEqual([stop.station for stop in result.trips[0].stops], ["PACK-DUE", "PACK-LOW"])
        self.assertEqual(result.collected, 19)
        self.assertEqual(result.makespan_sec, 88)
        self.assertEqual(result.residual, [])

    def test_below_threshold_piles_are_not_seeded(self) -> None:
        result = plan(
            floor(
                stations=[
                    {
                        "id": "PACK-A",
                        "kind": "pack",
                        "x_m": 20,
                        "y_m": 0,
                        "threshold": 10,
                        "cap": 24,
                        "minutes_since_pickup": 40,
                        "piles": [{"tote": "std", "count": 3}],
                    }
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.trips, [])
        self.assertEqual(len(result.residual), 1)
        self.assertEqual(result.residual[0]["remaining"], 3)

    def test_two_carts_leave_in_parallel(self) -> None:
        result = plan(
            floor(
                carts=[
                    {
                        "id": "C1",
                        "stack_cap": 1,
                        "speed_m_per_min": 60,
                        "load_sec_per_stack": 10,
                        "shift_min": 30,
                    },
                    {
                        "id": "C2",
                        "stack_cap": 1,
                        "speed_m_per_min": 60,
                        "load_sec_per_stack": 10,
                        "shift_min": 30,
                    },
                ],
                stations=[
                    {
                        "id": "PACK-A",
                        "kind": "pack",
                        "x_m": 20,
                        "y_m": 0,
                        "threshold": 8,
                        "cap": 24,
                        "minutes_since_pickup": 10,
                        "piles": [{"tote": "std", "count": 12}],
                    },
                    {
                        "id": "PACK-B",
                        "kind": "pack",
                        "x_m": 0,
                        "y_m": 20,
                        "threshold": 8,
                        "cap": 24,
                        "minutes_since_pickup": 10,
                        "piles": [{"tote": "std", "count": 12}],
                    },
                ],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(len(result.trips), 2)
        starts = {trip.cart: trip.start_sec for trip in result.trips}
        self.assertEqual(starts["C1"], 0)
        self.assertEqual(starts["C2"], 0)
        stations = {trip.cart: trip.stops[0].station for trip in result.trips}
        self.assertEqual(stations["C1"], "PACK-A")
        self.assertEqual(stations["C2"], "PACK-B")

    def test_no_home_for_cold_is_leftover(self) -> None:
        result = plan(
            floor(
                stations=[
                    {
                        "id": "PACK-A",
                        "kind": "pack",
                        "x_m": 20,
                        "y_m": 0,
                        "threshold": 8,
                        "cap": 24,
                        "minutes_since_pickup": 10,
                        "piles": [{"tote": "cold", "count": 12}],
                    }
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.trips, [])
        self.assertEqual(result.leftover[0]["reason"], "no home that accepts 'cold'")

    def test_station_still_over_cap_after_one_trip(self) -> None:
        result = plan(
            floor(
                carts=[
                    {
                        "id": "C1",
                        "stack_cap": 1,
                        "speed_m_per_min": 60,
                        "load_sec_per_stack": 10,
                        "shift_min": 1,
                    }
                ],
                stations=[
                    {
                        "id": "PACK-A",
                        "kind": "pack",
                        "x_m": 10,
                        "y_m": 0,
                        "threshold": 8,
                        "cap": 20,
                        "minutes_since_pickup": 10,
                        "piles": [{"tote": "std", "count": 45}],
                    }
                ],
            )
        )
        # One stack = 20 totes. Travel 10 + load 10 + return 10 + drop 10 = 40s.
        # Shift is 60s so one trip fits, second does not (would start at 40, finish 80).
        self.assertFalse(result.all_fit)
        self.assertEqual(result.collected, 20)
        self.assertEqual(result.leftover[0]["remaining"], 25)
        self.assertEqual(result.leftover[0]["reason"], "station still over cap")
        self.assertEqual(result.overflow_stations, ["PACK-A"])

    def test_carts_start_at_induction(self) -> None:
        result = plan(load("quiet-aisle.json"))
        trip = result.trips[0]
        self.assertEqual((trip.start_x_m, trip.start_y_m), (0, 0))
        self.assertEqual(trip.stops[0].arrive_sec, 20)

    def test_duplicate_station_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            floor(
                stations=[
                    {
                        "id": "PACK-A",
                        "kind": "pack",
                        "x_m": 10,
                        "y_m": 0,
                        "threshold": 8,
                        "cap": 24,
                        "piles": [{"tote": "std", "count": 8}],
                    },
                    {
                        "id": "PACK-A",
                        "kind": "pack",
                        "x_m": 20,
                        "y_m": 0,
                        "threshold": 8,
                        "cap": 24,
                        "piles": [{"tote": "std", "count": 8}],
                    },
                ]
            )


if __name__ == "__main__":
    unittest.main()
