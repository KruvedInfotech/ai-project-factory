from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loadfit.model import BoxSpec, Shipment
from loadfit.pack import PackResult, _overlaps, pack


def shipment(**kwargs) -> Shipment:
    payload = {
        "container": {"preset": "truck_14ft"},
        "allow_rotation": True,
        "this_side_up": True,
        "boxes": [
            {
                "sku": "A",
                "length_mm": 1000,
                "width_mm": 1000,
                "height_mm": 500,
                "weight_kg": 10,
                "quantity": 2,
            }
        ],
    }
    payload.update(kwargs)
    return Shipment.from_dict(payload)


class PackTests(unittest.TestCase):
    def test_single_box_sits_on_origin(self) -> None:
        result = pack(
            shipment(
                boxes=[
                    {
                        "sku": "ONE",
                        "length_mm": 800,
                        "width_mm": 400,
                        "height_mm": 300,
                        "weight_kg": 5,
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(len(result.placements), 1)
        placed = result.placements[0]
        self.assertEqual((placed.x, placed.y, placed.z), (0, 0, 0))

    def test_two_boxes_sit_side_by_side(self) -> None:
        result = pack(
            Shipment.from_dict(
                {
                    "container": {
                        "length_mm": 2000,
                        "width_mm": 1000,
                        "height_mm": 500,
                        "max_weight_kg": 100,
                    },
                    "allow_rotation": False,
                    "this_side_up": True,
                    "boxes": [
                        {
                            "sku": "LEFT",
                            "length_mm": 1000,
                            "width_mm": 1000,
                            "height_mm": 500,
                            "weight_kg": 4,
                            "quantity": 1,
                        },
                        {
                            "sku": "RIGHT",
                            "length_mm": 1000,
                            "width_mm": 1000,
                            "height_mm": 500,
                            "weight_kg": 4,
                            "quantity": 1,
                        },
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        xs = sorted(p.x for p in result.placements)
        self.assertEqual(xs, [0, 1000])

    def test_second_box_stacks_when_floor_is_full(self) -> None:
        result = pack(
            Shipment.from_dict(
                {
                    "container": {
                        "length_mm": 1000,
                        "width_mm": 1000,
                        "height_mm": 1000,
                        "max_weight_kg": 100,
                    },
                    "allow_rotation": False,
                    "boxes": [
                        {
                            "sku": "BOTTOM",
                            "length_mm": 1000,
                            "width_mm": 1000,
                            "height_mm": 400,
                            "weight_kg": 3,
                            "quantity": 1,
                        },
                        {
                            "sku": "TOP",
                            "length_mm": 1000,
                            "width_mm": 1000,
                            "height_mm": 400,
                            "weight_kg": 3,
                            "quantity": 1,
                        },
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        zs = sorted(p.z for p in result.placements)
        self.assertEqual(zs, [0, 400])

    def test_oversize_carton_is_left_behind(self) -> None:
        result = pack(
            Shipment.from_dict(
                {
                    "container": {"preset": "pallet_eu"},
                    "boxes": [
                        {
                            "sku": "CRATE",
                            "length_mm": 3000,
                            "width_mm": 2000,
                            "height_mm": 2000,
                            "weight_kg": 50,
                            "quantity": 1,
                        }
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.placements, [])
        self.assertEqual(result.unpacked[0]["sku"], "CRATE")

    def test_payload_cap_blocks_later_cartons(self) -> None:
        result = pack(
            Shipment.from_dict(
                {
                    "container": {"preset": "van_407", "max_weight_kg": 10},
                    "boxes": [
                        {
                            "sku": "HEAVY",
                            "length_mm": 400,
                            "width_mm": 400,
                            "height_mm": 400,
                            "weight_kg": 6,
                            "quantity": 2,
                        }
                    ],
                }
            )
        )
        self.assertEqual(len(result.placements), 1)
        self.assertEqual(result.unpacked[0]["quantity"], 1)

    def test_floor_rotation_makes_a_fit(self) -> None:
        payload = {
            "container": {
                "length_mm": 100,
                "width_mm": 200,
                "height_mm": 50,
                "max_weight_kg": 20,
            },
            "this_side_up": True,
            "boxes": [
                {
                    "sku": "TURN",
                    "length_mm": 200,
                    "width_mm": 100,
                    "height_mm": 50,
                    "weight_kg": 1,
                    "quantity": 1,
                }
            ],
        }
        stuck = pack(Shipment.from_dict({**payload, "allow_rotation": False}))
        fitted = pack(Shipment.from_dict({**payload, "allow_rotation": True}))
        self.assertFalse(stuck.all_fit)
        self.assertTrue(fitted.all_fit)
        self.assertEqual(fitted.placements[0].length_mm, 100)
        self.assertEqual(fitted.placements[0].width_mm, 200)

    def test_mixed_example_stays_inside_and_does_not_overlap(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mixed-cartons.json"
        result = pack(Shipment.from_dict(__import__("json").loads(example.read_text())))
        self.assertGreater(len(result.placements), 0)
        self._assert_legal(result)

    def test_volume_and_weight_utilization_are_ratios(self) -> None:
        result = pack(
            shipment(
                boxes=[
                    {
                        "sku": "A",
                        "length_mm": 1000,
                        "width_mm": 1000,
                        "height_mm": 1000,
                        "weight_kg": 400,
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertGreater(result.volume_utilization, 0)
        self.assertLessEqual(result.volume_utilization, 1)
        self.assertGreater(result.weight_utilization, 0)
        self.assertLessEqual(result.weight_utilization, 1)

    def _assert_legal(self, result: PackResult) -> None:
        box = result.container
        for item in result.placements:
            self.assertGreaterEqual(item.x, 0)
            self.assertGreaterEqual(item.y, 0)
            self.assertGreaterEqual(item.z, 0)
            self.assertLessEqual(item.x2, box.length_mm)
            self.assertLessEqual(item.y2, box.width_mm)
            self.assertLessEqual(item.z2, box.height_mm)
        for i, a in enumerate(result.placements):
            for b in result.placements[i + 1 :]:
                self.assertFalse(_overlaps(a, b), f"{a} overlaps {b}")


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_skus(self) -> None:
        with self.assertRaises(ValueError):
            Shipment.from_dict(
                {
                    "container": {"preset": "van_407"},
                    "boxes": [
                        {
                            "sku": "A",
                            "length_mm": 100,
                            "width_mm": 100,
                            "height_mm": 100,
                            "weight_kg": 1,
                        },
                        {
                            "sku": "A",
                            "length_mm": 120,
                            "width_mm": 100,
                            "height_mm": 100,
                            "weight_kg": 1,
                        },
                    ],
                }
            )

    def test_rejects_empty_shipment(self) -> None:
        with self.assertRaises(ValueError):
            Shipment.from_dict({"container": {"preset": "van_407"}, "boxes": []})

    def test_expand_respects_quantity(self) -> None:
        spec = BoxSpec("A", 1, 1, 1, 1, quantity=4)
        ship = shipment(boxes=[spec.__dict__])
        self.assertEqual(len(ship.expand()), 4)


if __name__ == "__main__":
    unittest.main()
