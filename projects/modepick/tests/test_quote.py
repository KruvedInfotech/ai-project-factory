from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modepick.geo import haversine_km
from modepick.model import Job, Piece
from modepick.quote import _billable_kg, quote


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def job(**kwargs) -> Job:
    payload = {
        "origin": "A",
        "destination": "B",
        "distance_km": 100,
        "pieces": [
            {
                "sku": "A",
                "length_cm": 30,
                "width_cm": 20,
                "height_cm": 15,
                "weight_kg": 2,
                "quantity": 1,
            }
        ],
    }
    payload.update(kwargs)
    return Job.from_dict(payload)


class QuoteTests(unittest.TestCase):
    def test_small_example_picks_parcel(self) -> None:
        result = quote(Job.from_dict(json.loads((EXAMPLES / "small-parcel.json").read_text())))
        self.assertEqual(result.winner, "parcel")
        self.assertTrue(result.quotes[0].feasible)
        self.assertGreater(result.savings_usd or 0, 0)

    def test_mid_example_picks_ltl_and_rejects_parcel(self) -> None:
        result = quote(Job.from_dict(json.loads((EXAMPLES / "mid-ltl.json").read_text())))
        self.assertEqual(result.winner, "ltl")
        parcel = next(q for q in result.quotes if q.mode == "parcel")
        self.assertFalse(parcel.feasible)
        self.assertIn("30", parcel.reason or "")

    def test_truck_example_picks_ftl_and_rejects_ltl_cube(self) -> None:
        result = quote(Job.from_dict(json.loads((EXAMPLES / "full-truck.json").read_text())))
        self.assertEqual(result.winner, "ftl")
        ltl = next(q for q in result.quotes if q.mode == "ltl")
        self.assertFalse(ltl.feasible)
        self.assertIn("m³", ltl.reason or "")
        ftl = next(q for q in result.quotes if q.mode == "ftl")
        self.assertEqual(ftl.detail["truck"], "truck_14ft")

    def test_dim_weight_beats_actual_on_fluffy_piece(self) -> None:
        piece = Piece("FLUFF", 40, 40, 40, 0.4)
        billed = _billable_kg(piece, 5000)
        self.assertGreater(billed, piece.weight_kg)
        self.assertEqual(billed, 13.0)

    def test_oversize_side_blocks_parcel(self) -> None:
        result = quote(
            job(
                pieces=[
                    {
                        "sku": "POLE",
                        "length_cm": 160,
                        "width_cm": 10,
                        "height_cm": 10,
                        "weight_kg": 4,
                        "quantity": 1,
                    }
                ]
            )
        )
        parcel = next(q for q in result.quotes if q.mode == "parcel")
        self.assertFalse(parcel.feasible)
        self.assertIn("longest side", parcel.reason or "")

    def test_heavy_shipment_skips_small_truck(self) -> None:
        result = quote(
            job(
                distance_km=200,
                pieces=[
                    {
                        "sku": "STEEL",
                        "length_cm": 80,
                        "width_cm": 60,
                        "height_cm": 40,
                        "weight_kg": 400,
                        "quantity": 8,
                    }
                ],
            )
        )
        ftl = next(q for q in result.quotes if q.mode == "ftl")
        self.assertTrue(ftl.feasible)
        self.assertEqual(ftl.detail["truck"], "truck_14ft")
        skipped = {item["id"] for item in ftl.detail["skipped"]}
        self.assertIn("van_407", skipped)

    def test_density_maps_to_class_70(self) -> None:
        result = quote(
            job(
                pieces=[
                    {
                        "sku": "DENSE",
                        "length_cm": 40,
                        "width_cm": 40,
                        "height_cm": 40,
                        "weight_kg": 40,
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertGreaterEqual(result.stats.pcf, 30)
        self.assertEqual(result.stats.freight_class, 70.0)

    def test_ltl_applies_minimum_charge_on_tiny_weight(self) -> None:
        result = quote(job(distance_km=40))
        ltl = next(q for q in result.quotes if q.mode == "ltl")
        self.assertTrue(ltl.feasible)
        self.assertEqual(ltl.total_usd, 95.0)

    def test_ftl_uses_per_km_not_minimum_on_a_long_lane(self) -> None:
        result = quote(
            job(
                distance_km=400,
                pieces=[
                    {
                        "sku": "PALLET",
                        "length_cm": 120,
                        "width_cm": 80,
                        "height_cm": 100,
                        "weight_kg": 200,
                        "quantity": 6,
                    }
                ],
            )
        )
        ftl = next(q for q in result.quotes if q.mode == "ftl")
        self.assertTrue(ftl.feasible)
        self.assertGreater(ftl.total_usd or 0, 90)
        self.assertAlmostEqual(ftl.total_usd or 0, 400 * 1.15, places=2)

    def test_lat_lon_sets_distance(self) -> None:
        km = haversine_km(23.03, 72.58, 21.17, 72.83)
        result = quote(
            Job.from_dict(
                {
                    "origin": {"name": "Ahmedabad", "lat": 23.03, "lon": 72.58},
                    "destination": {"name": "Surat", "lat": 21.17, "lon": 72.83},
                    "pieces": [
                        {
                            "sku": "A",
                            "length_cm": 20,
                            "width_cm": 20,
                            "height_cm": 20,
                            "weight_kg": 1,
                            "quantity": 1,
                        }
                    ],
                }
            )
        )
        self.assertAlmostEqual(result.distance_km, km, places=4)
        self.assertEqual(result.origin, "Ahmedabad")

    def test_winner_is_cheapest_feasible(self) -> None:
        result = quote(Job.from_dict(json.loads((EXAMPLES / "small-parcel.json").read_text())))
        feasible = [q.total_usd for q in result.quotes if q.feasible and q.total_usd is not None]
        self.assertEqual(result.winner_usd, min(feasible))

    def test_nothing_fits_returns_no_winner(self) -> None:
        result = quote(
            job(
                pieces=[
                    {
                        "sku": "MACHINE",
                        "length_cm": 400,
                        "width_cm": 250,
                        "height_cm": 250,
                        "weight_kg": 13000,
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertIsNone(result.winner)
        self.assertFalse(any(q.feasible for q in result.quotes))


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_skus(self) -> None:
        with self.assertRaises(ValueError):
            job(
                pieces=[
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
                ]
            )

    def test_rejects_empty_shipment(self) -> None:
        with self.assertRaises(ValueError):
            Job.from_dict({"distance_km": 10, "pieces": []})

    def test_expand_respects_quantity(self) -> None:
        ship = job(
            pieces=[
                {
                    "sku": "A",
                    "length_cm": 10,
                    "width_cm": 10,
                    "height_cm": 10,
                    "weight_kg": 1,
                    "quantity": 5,
                }
            ]
        )
        self.assertEqual(len(ship.expand()), 5)

    def test_equator_degree_is_about_111_km(self) -> None:
        self.assertAlmostEqual(haversine_km(0, 0, 0, 1), 111.195, places=2)


if __name__ == "__main__":
    unittest.main()
