from __future__ import annotations

import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shipcut.cards import CARRIERS, zone_for
from shipcut.model import Job
from shipcut.plan import add_transit, next_pickup, plan


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> Job:
    payload = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return Job.from_dict(payload)


def by_id(result, carrier: str):
    return next(item for item in result.plans if item.carrier == carrier)


class ZoneTests(unittest.TestCase):
    def test_distance_maps_to_bands(self) -> None:
        self.assertEqual(zone_for(0).id, "Z1")
        self.assertEqual(zone_for(80).id, "Z1")
        self.assertEqual(zone_for(81).id, "Z2")
        self.assertEqual(zone_for(110).id, "Z2")
        self.assertEqual(zone_for(620).id, "Z4")
        self.assertEqual(zone_for(1000).id, "Z4")
        self.assertEqual(zone_for(1001).id, "Z5")


class TransitTests(unittest.TestCase):
    def test_same_day_stays_on_pickup_date(self) -> None:
        self.assertEqual(
            add_transit(date(2026, 11, 17), 0, skip_sunday=True, skip_saturday=True),
            date(2026, 11, 17),
        )

    def test_sunday_rolls_to_monday(self) -> None:
        # Friday + 2 calendar days = Sunday → Monday
        self.assertEqual(
            add_transit(date(2026, 11, 20), 2, skip_sunday=True, skip_saturday=False),
            date(2026, 11, 23),
        )

    def test_saturday_delivery_rolls_when_skipped(self) -> None:
        # Wednesday + 3 = Saturday → Monday
        self.assertEqual(
            add_transit(date(2026, 11, 18), 3, skip_sunday=True, skip_saturday=True),
            date(2026, 11, 23),
        )


class PickupTests(unittest.TestCase):
    def test_before_cutoff_is_same_day(self) -> None:
        pickup = next_pickup(datetime(2026, 11, 17, 10, 30), CARRIERS["metro_same"])
        self.assertEqual(pickup, datetime(2026, 11, 17, 12, 0))

    def test_after_cutoff_rolls_to_next_pickup_day(self) -> None:
        pickup = next_pickup(datetime(2026, 11, 17, 12, 1), CARRIERS["metro_same"])
        self.assertEqual(pickup, datetime(2026, 11, 18, 12, 0))

    def test_friday_after_economy_cutoff_skips_weekend(self) -> None:
        pickup = next_pickup(datetime(2026, 11, 20, 17, 10), CARRIERS["economy"])
        self.assertEqual(pickup, datetime(2026, 11, 23, 17, 0))

    def test_ready_at_cutoff_still_makes_it(self) -> None:
        pickup = next_pickup(datetime(2026, 11, 17, 12, 0), CARRIERS["metro_same"])
        self.assertEqual(pickup, datetime(2026, 11, 17, 12, 0))


class PlanTests(unittest.TestCase):
    def test_same_day_example_picks_metro(self) -> None:
        result = plan(load_example("same-day.json"))
        self.assertEqual(result.winner, "metro_same")
        self.assertEqual(result.soonest_cutoff_minutes, 90)
        metro = by_id(result, "metro_same")
        self.assertEqual(metro.status, "makes_sla")
        self.assertEqual(metro.delivery_on, "2026-11-17")
        self.assertEqual(metro.minutes_remaining, 90)
        air = by_id(result, "air_express")
        self.assertEqual(air.status, "late")
        self.assertEqual(air.delivery_on, "2026-11-18")

    def test_missed_cutoff_example_takes_night_run(self) -> None:
        result = plan(load_example("missed-cutoff.json"))
        self.assertEqual(result.zone, "Z2")
        self.assertEqual(result.winner, "night_run")
        night = by_id(result, "night_run")
        self.assertEqual(night.status, "makes_sla")
        self.assertEqual(night.delivery_on, "2026-11-18")
        self.assertEqual(night.minutes_remaining, 230)
        air = by_id(result, "air_express")
        self.assertEqual(air.status, "missed_cutoff")
        metro = by_id(result, "metro_same")
        self.assertEqual(metro.status, "missed_cutoff")
        ground = by_id(result, "ground_std")
        self.assertEqual(ground.status, "late")
        self.assertEqual(ground.minutes_remaining, 50)

    def test_weekend_roll_prefers_friday_night_run(self) -> None:
        result = plan(load_example("weekend-roll.json"))
        self.assertEqual(result.winner, "night_run")
        night = by_id(result, "night_run")
        self.assertEqual(night.delivery_on, "2026-11-23")
        self.assertEqual(night.pickup_at, "2026-11-20T21:00:00")
        air = by_id(result, "air_express")
        self.assertEqual(air.status, "makes_sla")
        self.assertTrue(air.missed_today)
        self.assertEqual(air.pickup_at, "2026-11-21T15:00:00")
        metro = by_id(result, "metro_same")
        self.assertEqual(metro.status, "zone_blocked")
        ground = by_id(result, "ground_std")
        self.assertEqual(ground.status, "late")

    def test_too_late_example_has_no_winner(self) -> None:
        result = plan(load_example("too-late.json"))
        self.assertIsNone(result.winner)
        self.assertEqual(result.makes_sla_count, 0)
        metro = by_id(result, "metro_same")
        self.assertEqual(metro.status, "oversize")
        air = by_id(result, "air_express")
        self.assertEqual(air.status, "late")

    def test_oversize_piece_is_a_no_go(self) -> None:
        job = Job.from_dict(
            {
                "ready_at": "2026-11-17T10:00:00",
                "promised_on": "2026-11-17",
                "zone": "Z1",
                "pieces": [
                    {
                        "sku": "LONG",
                        "length_cm": 90,
                        "width_cm": 20,
                        "height_cm": 20,
                        "weight_kg": 2,
                        "quantity": 1,
                    }
                ],
            }
        )
        result = plan(job)
        metro = by_id(result, "metro_same")
        self.assertEqual(metro.status, "oversize")
        self.assertIn("90", metro.reason or "")
        air = by_id(result, "air_express")
        self.assertNotEqual(air.status, "oversize")

    def test_heavy_piece_blocks_air(self) -> None:
        job = Job.from_dict(
            {
                "origin": "DC",
                "destination": "Hub",
                "ready_at": "2026-11-17T10:00:00",
                "promised_on": "2026-11-20",
                "zone": "Z1",
                "pieces": [
                    {
                        "sku": "HEAVY",
                        "length_cm": 40,
                        "width_cm": 40,
                        "height_cm": 40,
                        "weight_kg": 35,
                        "quantity": 1,
                    }
                ],
            }
        )
        result = plan(job)
        self.assertEqual(by_id(result, "air_express").status, "oversize")
        self.assertEqual(by_id(result, "night_run").status, "makes_sla")

    def test_winner_prefers_earlier_delivery_then_earlier_pickup(self) -> None:
        result = plan(load_example("same-day.json"))
        self.assertEqual(result.winner, "metro_same")
        self.assertEqual(by_id(result, "metro_same").delivery_on, "2026-11-17")


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_skus(self) -> None:
        with self.assertRaises(ValueError):
            Job.from_dict(
                {
                    "ready_at": "2026-11-17T10:00:00",
                    "promised_on": "2026-11-18",
                    "zone": "Z1",
                    "pieces": [
                        {
                            "sku": "A",
                            "length_cm": 10,
                            "width_cm": 10,
                            "height_cm": 10,
                            "weight_kg": 1,
                        },
                        {
                            "sku": "A",
                            "length_cm": 12,
                            "width_cm": 10,
                            "height_cm": 10,
                            "weight_kg": 1,
                        },
                    ],
                }
            )

    def test_rejects_empty_order(self) -> None:
        with self.assertRaises(ValueError):
            Job.from_dict(
                {
                    "ready_at": "2026-11-17T10:00:00",
                    "promised_on": "2026-11-18",
                    "zone": "Z1",
                    "pieces": [],
                }
            )

    def test_needs_zone_or_distance(self) -> None:
        with self.assertRaises(ValueError):
            Job.from_dict(
                {
                    "ready_at": "2026-11-17T10:00:00",
                    "promised_on": "2026-11-18",
                    "pieces": [
                        {
                            "sku": "A",
                            "length_cm": 10,
                            "width_cm": 10,
                            "height_cm": 10,
                            "weight_kg": 1,
                        }
                    ],
                }
            )

    def test_expand_respects_quantity(self) -> None:
        job = Job.from_dict(
            {
                "ready_at": "2026-11-17T10:00:00",
                "promised_on": "2026-11-18",
                "zone": "Z1",
                "pieces": [
                    {
                        "sku": "A",
                        "length_cm": 10,
                        "width_cm": 10,
                        "height_cm": 10,
                        "weight_kg": 1,
                        "quantity": 4,
                    }
                ],
            }
        )
        self.assertEqual(len(job.expand()), 4)
        self.assertEqual(job.expand()[0].quantity, 1)


if __name__ == "__main__":
    unittest.main()
