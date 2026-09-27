from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dockbook.book import book
from dockbook.model import DayPlan, Trailer
from dockbook.yards import get_yard


def plan(**kwargs) -> DayPlan:
    payload = {
        "yard": {"preset": "mini_2"},
        "strategy": "earliest",
        "trailers": [
            {
                "id": "T1",
                "carrier": "Local",
                "direction": "inbound",
                "length_m": 10,
                "duration_min": 60,
                "window_start": "08:00",
                "window_end": "12:00",
            }
        ],
    }
    payload.update(kwargs)
    return DayPlan.from_dict(payload)


class BookTests(unittest.TestCase):
    def test_single_trailer_takes_first_door_at_window_open(self) -> None:
        result = book(plan())
        self.assertTrue(result.all_booked)
        self.assertEqual(len(result.bookings), 1)
        item = result.bookings[0]
        self.assertEqual(item.door_id, "A")
        self.assertEqual(item.start_min, 8 * 60)
        self.assertEqual(item.end_min, 9 * 60)

    def test_second_trailer_uses_other_door_when_first_is_busy(self) -> None:
        result = book(
            plan(
                trailers=[
                    {
                        "id": "A1",
                        "carrier": "Local",
                        "direction": "inbound",
                        "length_m": 10,
                        "duration_min": 120,
                        "window_start": "08:00",
                        "window_end": "12:00",
                    },
                    {
                        "id": "B1",
                        "carrier": "Local",
                        "direction": "outbound",
                        "length_m": 10,
                        "duration_min": 60,
                        "window_start": "08:00",
                        "window_end": "12:00",
                    },
                ]
            )
        )
        doors = {item.trailer.id: item.door_id for item in result.bookings}
        self.assertEqual(doors["A1"], "A")
        self.assertEqual(doors["B1"], "B")

    def test_turnaround_blocks_immediate_reuse(self) -> None:
        result = book(
            DayPlan.from_dict(
                {
                    "yard": {"preset": "mini_2", "turnaround_min": 30},
                    "strategy": "preferred",
                    "trailers": [
                        {
                            "id": "FIRST",
                            "carrier": "Local",
                            "direction": "inbound",
                            "length_m": 10,
                            "duration_min": 60,
                            "window_start": "08:00",
                            "window_end": "12:00",
                            "prefer_door": "A",
                            "priority": 1,
                        },
                        {
                            "id": "SECOND",
                            "carrier": "Local",
                            "direction": "inbound",
                            "length_m": 10,
                            "duration_min": 60,
                            "window_start": "09:00",
                            "window_end": "12:00",
                            "prefer_door": "A",
                        },
                    ],
                }
            )
        )
        second = next(item for item in result.bookings if item.trailer.id == "SECOND")
        self.assertEqual(second.door_id, "A")
        self.assertEqual(second.start_min, 9 * 60 + 30)

    def test_reefer_cannot_use_dry_only_door(self) -> None:
        result = book(
            plan(
                trailers=[
                    {
                        "id": "RF",
                        "carrier": "Frost",
                        "direction": "inbound",
                        "reefer": True,
                        "length_m": 10,
                        "duration_min": 60,
                        "window_start": "08:00",
                        "window_end": "12:00",
                    }
                ]
            )
        )
        self.assertTrue(result.all_booked)
        self.assertEqual(result.bookings[0].door_id, "A")

    def test_dry_trailer_left_when_only_reefer_doors_exist(self) -> None:
        result = book(
            DayPlan.from_dict(
                {
                    "yard": {"preset": "cold_3"},
                    "trailers": [
                        {
                            "id": "DRY",
                            "carrier": "Coastal",
                            "direction": "inbound",
                            "length_m": 12,
                            "duration_min": 60,
                            "window_start": "08:00",
                            "window_end": "12:00",
                        }
                    ],
                }
            )
        )
        self.assertFalse(result.all_booked)
        self.assertEqual(result.leftover[0]["id"], "DRY")
        self.assertIn("no door accepts", result.leftover[0]["reason"])

    def test_overlong_trailer_is_leftover(self) -> None:
        result = book(
            plan(
                trailers=[
                    {
                        "id": "MEGA",
                        "carrier": "Mega",
                        "direction": "inbound",
                        "length_m": 18,
                        "duration_min": 45,
                        "window_start": "09:00",
                        "window_end": "12:00",
                    }
                ]
            )
        )
        self.assertEqual(result.leftover[0]["id"], "MEGA")
        self.assertIn("longer than every door", result.leftover[0]["reason"])

    def test_window_past_close_is_leftover(self) -> None:
        result = book(
            plan(
                trailers=[
                    {
                        "id": "LATE",
                        "carrier": "NightOwl",
                        "direction": "inbound",
                        "length_m": 10,
                        "duration_min": 90,
                        "window_start": "15:00",
                        "window_end": "18:00",
                    }
                ]
            )
        )
        self.assertEqual(result.leftover[0]["id"], "LATE")
        self.assertIn("no free slot", result.leftover[0]["reason"])

    def test_priority_books_tight_window_first(self) -> None:
        result = book(
            plan(
                trailers=[
                    {
                        "id": "LOOSE",
                        "carrier": "A",
                        "direction": "inbound",
                        "length_m": 10,
                        "duration_min": 120,
                        "window_start": "08:00",
                        "window_end": "16:00",
                        "priority": 3,
                    },
                    {
                        "id": "TIGHT",
                        "carrier": "B",
                        "direction": "inbound",
                        "length_m": 10,
                        "duration_min": 120,
                        "window_start": "08:00",
                        "window_end": "10:00",
                        "priority": 1,
                    },
                ]
            )
        )
        self.assertTrue(result.all_booked)
        first = min(result.bookings, key=lambda item: (item.start_min, item.door_id))
        tight = next(item for item in result.bookings if item.trailer.id == "TIGHT")
        self.assertEqual(tight.start_min, 8 * 60)
        self.assertEqual(first.trailer.id, "TIGHT")

    def test_preferred_strategy_refuses_other_doors(self) -> None:
        result = book(
            DayPlan.from_dict(
                {
                    "yard": {"preset": "mini_2"},
                    "strategy": "preferred",
                    "trailers": [
                        {
                            "id": "WANT-B",
                            "carrier": "Local",
                            "direction": "inbound",
                            "reefer": True,
                            "length_m": 10,
                            "duration_min": 60,
                            "window_start": "08:00",
                            "window_end": "12:00",
                            "prefer_door": "B",
                        }
                    ],
                }
            )
        )
        self.assertFalse(result.all_booked)
        self.assertEqual(result.leftover[0]["id"], "WANT-B")

    def test_spread_splits_two_equal_jobs(self) -> None:
        result = book(
            plan(
                strategy="spread",
                trailers=[
                    {
                        "id": "S1",
                        "carrier": "A",
                        "direction": "inbound",
                        "length_m": 10,
                        "duration_min": 60,
                        "window_start": "08:00",
                        "window_end": "12:00",
                    },
                    {
                        "id": "S2",
                        "carrier": "B",
                        "direction": "outbound",
                        "length_m": 10,
                        "duration_min": 60,
                        "window_start": "08:00",
                        "window_end": "12:00",
                    },
                ],
            )
        )
        doors = {item.door_id for item in result.bookings}
        self.assertEqual(doors, {"A", "B"})

    def test_bookings_do_not_overlap_on_a_door(self) -> None:
        result = book(
            DayPlan.from_dict(
                {
                    "yard": {"preset": "fmcg_4"},
                    "trailers": [
                        {
                            "id": f"IN-{n}",
                            "carrier": "BlueLine",
                            "direction": "inbound",
                            "length_m": 12,
                            "duration_min": 60,
                            "window_start": "06:00",
                            "window_end": "14:00",
                        }
                        for n in range(6)
                    ],
                }
            )
        )
        by_door: dict[str, list] = {}
        for item in result.bookings:
            by_door.setdefault(item.door_id, []).append(item)
        for rows in by_door.values():
            rows.sort(key=lambda item: item.start_min)
            for prev, nxt in zip(rows, rows[1:]):
                self.assertLessEqual(prev.end_min, nxt.start_min)

    def test_morning_inbound_example_all_fits(self) -> None:
        payload = (
            Path(__file__).resolve().parents[1] / "examples" / "morning-inbound.json"
        )
        result = book(DayPlan.from_dict(__import__("json").loads(payload.read_text())))
        self.assertTrue(result.all_booked)
        self.assertEqual(len(result.bookings), 7)
        rf = next(item for item in result.bookings if item.trailer.id == "RF-12")
        self.assertEqual(rf.door_id, "D4")

    def test_custom_yard_from_dict(self) -> None:
        yard = get_yard(
            {
                "name": "One door",
                "open": "09:00",
                "close": "11:00",
                "turnaround_min": 0,
                "doors": [
                    {
                        "id": "Z",
                        "directions": ["inbound"],
                        "temps": ["dry"],
                        "max_length_m": 12,
                    }
                ],
            }
        )
        result = book(
            DayPlan(
                yard=yard,
                trailers=[
                    Trailer(
                        id="OK",
                        carrier="X",
                        direction="inbound",
                        reefer=False,
                        length_m=10,
                        duration_min=30,
                        window_start="09:00",
                        window_end="11:00",
                    )
                ],
            )
        )
        self.assertTrue(result.all_booked)
        self.assertEqual(result.bookings[0].door_id, "Z")
