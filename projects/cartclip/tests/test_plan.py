from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cartclip.model import Wave
from cartclip.plan import plan_wave

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def wave(**kwargs) -> Wave:
    payload = {
        "warehouse": {"preset": "small_dc"},
        "cart": {"preset": "ecom_8tote"},
        "strategy": "auto",
        "orders": [
            {
                "id": "ORD-1",
                "priority": 2,
                "temp": "dry",
                "lines": [
                    {
                        "sku": "A",
                        "aisle": "A",
                        "bay": 1,
                        "quantity": 1,
                        "length_mm": 100,
                        "width_mm": 80,
                        "height_mm": 40,
                        "weight_kg": 0.5,
                    }
                ],
            }
        ],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


def line(sku: str, aisle: str, bay: int, **kwargs) -> dict:
    row = {
        "sku": sku,
        "aisle": aisle,
        "bay": bay,
        "quantity": 1,
        "length_mm": 100,
        "width_mm": 80,
        "height_mm": 40,
        "weight_kg": 0.5,
    }
    row.update(kwargs)
    return row


def order(oid: str, lines: list[dict], **kwargs) -> dict:
    row = {"id": oid, "priority": 2, "temp": "dry", "lines": lines}
    row.update(kwargs)
    return row


class PlanTests(unittest.TestCase):
    def test_single_order_sits_in_first_tote(self) -> None:
        result = plan_wave(wave())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.cart_count, 1)
        self.assertEqual(result.placements[0].cart_id, "C1")
        self.assertEqual(result.placements[0].slot, 1)
        self.assertEqual(result.placements[0].order_id, "ORD-1")

    def test_shared_aisle_orders_top_off_same_cart(self) -> None:
        result = plan_wave(
            wave(
                orders=[
                    order("ORD-A", [line("X", "A", 2)]),
                    order("ORD-B", [line("Y", "A", 6)]),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.cart_count, 1)
        self.assertEqual({item.order_id for item in result.placements}, {"ORD-A", "ORD-B"})

    def test_aisle_strategy_keeps_far_aisles_on_separate_carts(self) -> None:
        result = plan_wave(
            Wave.from_dict(json.loads((EXAMPLES / "aisle-cluster.json").read_text()))
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.cart_count, 2)
        by_order = {item.order_id: item.cart_id for item in result.placements}
        self.assertEqual(by_order["ORD-A1"], by_order["ORD-A2"])
        self.assertNotEqual(by_order["ORD-A1"], by_order["ORD-D1"])

    def test_auto_allows_adjacent_aisles_on_one_cart(self) -> None:
        result = plan_wave(
            wave(
                orders=[
                    order("ORD-A", [line("X", "A", 1)]),
                    order("ORD-B", [line("Y", "B", 1)]),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.cart_count, 1)
        self.assertEqual(result.carts[0]["span"], 1)

    def test_aisle_span_blocks_a_far_mix(self) -> None:
        result = plan_wave(
            wave(
                cart={"preset": "ecom_8tote", "max_aisle_span": 1},
                orders=[
                    order("ORD-A", [line("X", "A", 1)]),
                    order("ORD-D", [line("Y", "D", 1)]),
                ],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.cart_count, 2)

    def test_payload_cap_leaves_anvil_behind(self) -> None:
        result = plan_wave(Wave.from_dict(json.loads((EXAMPLES / "too-heavy.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.clipped_count, 1)
        self.assertEqual(result.leftover[0]["id"], "ORD-ANVIL")
        self.assertEqual(result.leftover[0]["reason"], "too-heavy")

    def test_cube_cap_leaves_oversize_order(self) -> None:
        result = plan_wave(
            wave(
                cart={"preset": "ecom_8tote", "max_volume_l": 1},
                orders=[
                    order(
                        "ORD-BULK",
                        [line("SOFA", "A", 1, length_mm=800, width_mm=800, height_mm=800)],
                    )
                ],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "too-cube")

    def test_temp_split_keeps_chill_off_a_dry_cart(self) -> None:
        result = plan_wave(
            wave(
                orders=[
                    order("ORD-DRY", [line("X", "A", 1)], temp="dry"),
                    order("ORD-CHILL", [line("Y", "A", 2)], temp="chill"),
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["id"], "ORD-CHILL")
        self.assertEqual(result.leftover[0]["reason"], "temp")

    def test_labor_cap_blocks_the_second_order(self) -> None:
        result = plan_wave(Wave.from_dict(json.loads((EXAMPLES / "labor-capped.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.clipped_count, 1)
        self.assertEqual(result.placements[0].order_id, "ORD-HOT")
        self.assertEqual(result.leftover[0]["id"], "ORD-NEXT")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")
        self.assertEqual(result.labor_used_min, 9)

    def test_full_totes_open_a_second_cart(self) -> None:
        result = plan_wave(
            wave(
                cart={"preset": "ecom_8tote", "tote_slots": 1},
                orders=[
                    order("ORD-1", [line("X", "A", 1)]),
                    order("ORD-2", [line("Y", "A", 2)]),
                ],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.cart_count, 2)

    def test_mixed_wave_example_clips_everything(self) -> None:
        result = plan_wave(Wave.from_dict(json.loads((EXAMPLES / "mixed-wave.json").read_text())))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.clipped_count, 4)
        self.assertEqual(result.cart_count, 1)
        self.assertGreater(result.labor_used_min, 0)
        self.assertEqual(result.aisle_map[0]["aisle"], "A")
        self.assertGreater(result.aisle_map[0]["picks"], 0)

    def test_prefers_the_cart_that_already_visits_the_aisle(self) -> None:
        result = plan_wave(
            wave(
                cart={"preset": "ecom_8tote", "tote_slots": 2, "max_aisle_span": 3},
                orders=[
                    order("ORD-A", [line("X", "A", 1)]),
                    order("ORD-C", [line("Y", "C", 1)]),
                    order("ORD-A2", [line("Z", "A", 8)]),
                ],
            )
        )
        self.assertTrue(result.all_fit)
        by_order = {item.order_id: item.cart_id for item in result.placements}
        self.assertEqual(by_order["ORD-A"], by_order["ORD-A2"])
        self.assertNotEqual(by_order["ORD-A"], by_order["ORD-C"])


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_order_ids(self) -> None:
        with self.assertRaises(ValueError):
            wave(orders=[order("ORD-1", [line("X", "A", 1)]), order("ORD-1", [line("Y", "A", 2)])])

    def test_rejects_empty_wave(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict(
                {"warehouse": {"preset": "small_dc"}, "cart": {"preset": "ecom_8tote"}, "orders": []}
            )

    def test_rejects_location_off_the_floor(self) -> None:
        with self.assertRaises(ValueError):
            wave(orders=[order("ORD-1", [line("X", "Z", 1)])])


if __name__ == "__main__":
    unittest.main()
