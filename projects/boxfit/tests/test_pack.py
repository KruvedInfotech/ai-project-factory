from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxfit.model import PackJob
from boxfit.pack import pack


def job(**kwargs) -> PackJob:
    payload = {
        "catalog": {
            "cartons": [
                {
                    "id": "small",
                    "name": "Small",
                    "length_mm": 200,
                    "width_mm": 200,
                    "height_mm": 100,
                    "max_weight_kg": 5,
                },
                {
                    "id": "large",
                    "name": "Large",
                    "length_mm": 400,
                    "width_mm": 200,
                    "height_mm": 100,
                    "max_weight_kg": 8,
                },
            ]
        },
        "labor_minutes": 60,
        "minutes_per_piece": 1,
        "minutes_per_carton": 2,
        "allow_rotation": True,
        "this_side_up": True,
        "items": [
            {
                "order_id": "O-1",
                "sku": "A",
                "length_mm": 180,
                "width_mm": 90,
                "height_mm": 40,
                "weight_kg": 1,
                "quantity": 1,
            }
        ],
    }
    payload.update(kwargs)
    return PackJob.from_dict(payload)


class PackTests(unittest.TestCase):
    def test_single_item_opens_smallest_carton(self) -> None:
        result = pack(job())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.carton_count, 1)
        self.assertEqual(result.cartons[0].shipper.id, "small")
        placed = result.cartons[0].placements[0]
        self.assertEqual((placed.x, placed.y, placed.z), (0, 0, 0))

    def test_two_items_share_a_carton_when_they_fit(self) -> None:
        result = pack(
            job(
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "LEFT",
                        "length_mm": 180,
                        "width_mm": 90,
                        "height_mm": 40,
                        "weight_kg": 1,
                        "quantity": 1,
                    },
                    {
                        "order_id": "O-1",
                        "sku": "RIGHT",
                        "length_mm": 180,
                        "width_mm": 90,
                        "height_mm": 40,
                        "weight_kg": 1,
                        "quantity": 1,
                    },
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.carton_count, 1)
        self.assertEqual(result.packed_count, 2)
        origins = {(p.x, p.y, p.z) for p in result.cartons[0].placements}
        self.assertEqual(len(origins), 2)

    def test_two_orders_never_share_a_carton(self) -> None:
        result = pack(
            job(
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "A",
                        "length_mm": 80,
                        "width_mm": 80,
                        "height_mm": 40,
                        "weight_kg": 0.5,
                        "quantity": 1,
                    },
                    {
                        "order_id": "O-2",
                        "sku": "B",
                        "length_mm": 80,
                        "width_mm": 80,
                        "height_mm": 40,
                        "weight_kg": 0.5,
                        "quantity": 1,
                    },
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.carton_count, 2)
        orders = {carton.order_id for carton in result.cartons}
        self.assertEqual(orders, {"O-1", "O-2"})

    def test_mixed_temps_do_not_share_a_carton(self) -> None:
        result = pack(
            job(
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "DRY",
                        "length_mm": 80,
                        "width_mm": 80,
                        "height_mm": 40,
                        "weight_kg": 0.4,
                        "quantity": 1,
                        "temp": "dry",
                    },
                    {
                        "order_id": "O-1",
                        "sku": "COLD",
                        "length_mm": 80,
                        "width_mm": 80,
                        "height_mm": 40,
                        "weight_kg": 0.4,
                        "quantity": 1,
                        "temp": "chill",
                    },
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.carton_count, 2)
        temps = {carton.temp for carton in result.cartons}
        self.assertEqual(temps, {"dry", "chill"})

    def test_too_big_item_is_leftover(self) -> None:
        result = pack(
            job(
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "HUGE",
                        "length_mm": 900,
                        "width_mm": 900,
                        "height_mm": 900,
                        "weight_kg": 1,
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.carton_count, 0)
        self.assertEqual(result.leftover[0]["reason"], "too-big")

    def test_too_heavy_item_is_leftover(self) -> None:
        result = pack(
            job(
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "LEAD",
                        "length_mm": 80,
                        "width_mm": 80,
                        "height_mm": 40,
                        "weight_kg": 20,
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "too-heavy")

    def test_labor_cap_stops_a_second_carton(self) -> None:
        result = pack(
            job(
                labor_minutes=3,
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "A",
                        "length_mm": 180,
                        "width_mm": 180,
                        "height_mm": 80,
                        "weight_kg": 1,
                        "quantity": 2,
                    }
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.packed_count, 1)
        self.assertEqual(result.leftover_count, 1)
        self.assertEqual(result.leftover[0]["reason"], "labor cap")

    def test_this_side_up_does_not_tumble(self) -> None:
        result = pack(
            job(
                this_side_up=True,
                allow_rotation=True,
                catalog={
                    "cartons": [
                        {
                            "id": "flat",
                            "length_mm": 120,
                            "width_mm": 80,
                            "height_mm": 75,
                            "max_weight_kg": 5,
                        }
                    ]
                },
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "TALL",
                        "length_mm": 70,
                        "width_mm": 70,
                        "height_mm": 90,
                        "weight_kg": 0.5,
                        "quantity": 1,
                    }
                ],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "too-big")

    def test_full_tumble_can_lay_a_tall_piece_down(self) -> None:
        result = pack(
            job(
                this_side_up=False,
                allow_rotation=True,
                catalog={
                    "cartons": [
                        {
                            "id": "flat",
                            "length_mm": 120,
                            "width_mm": 80,
                            "height_mm": 75,
                            "max_weight_kg": 5,
                        }
                    ]
                },
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "TALL",
                        "length_mm": 70,
                        "width_mm": 70,
                        "height_mm": 90,
                        "weight_kg": 0.5,
                        "quantity": 1,
                    }
                ],
            )
        )
        self.assertTrue(result.all_fit)
        placed = result.cartons[0].placements[0]
        self.assertEqual(placed.height_mm, 70)
        self.assertLessEqual(placed.height_mm, 75)

    def test_mixed_order_example_packs_everything(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mixed-order.json"
        result = pack(PackJob.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_fit)
        self.assertGreaterEqual(result.carton_count, 1)
        self.assertEqual(result.packed_count, 8)

    def test_split_orders_example_keeps_orders_apart(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "split-orders.json"
        result = pack(PackJob.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_fit)
        orders = {carton.order_id for carton in result.cartons}
        self.assertEqual(orders, {"O-100", "O-200"})
        for carton in result.cartons:
            skus = {p.sku for p in carton.placements}
            self.assertEqual(len(skus), 1)

    def test_payload_weight_opens_a_second_carton(self) -> None:
        result = pack(
            job(
                catalog={
                    "cartons": [
                        {
                            "id": "tiny",
                            "length_mm": 400,
                            "width_mm": 200,
                            "height_mm": 100,
                            "max_weight_kg": 1.5,
                        }
                    ]
                },
                items=[
                    {
                        "order_id": "O-1",
                        "sku": "A",
                        "length_mm": 180,
                        "width_mm": 90,
                        "height_mm": 40,
                        "weight_kg": 1,
                        "quantity": 2,
                    }
                ],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.carton_count, 2)
        self.assertEqual(result.packed_count, 2)
