from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wallsort.model import Batch
from wallsort.sort import sort_wall

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def line(**kwargs) -> dict:
    row = {
        "sku": "TEE",
        "length_mm": 250,
        "width_mm": 180,
        "height_mm": 60,
        "weight_kg": 0.4,
        "temp": "ambient",
    }
    row.update(kwargs)
    return row


def order(**kwargs) -> dict:
    row = {"id": "ORD-1", "carrier": "UPS", "priority": 2, "lines": [line()]}
    row.update(kwargs)
    return row


def batch(**kwargs) -> Batch:
    payload = {
        "wall": {"preset": "mini_2x3"},
        "strategy": "auto",
        "orders": [order()],
    }
    payload.update(kwargs)
    return Batch.from_dict(payload)


def cubby_of(result, order_id: str) -> tuple[int, int]:
    placed = {item.order_id: item for item in result.placements}
    item = placed[order_id]
    return item.row, item.col


class SortTests(unittest.TestCase):
    def test_single_order_sits_in_the_waist(self) -> None:
        result = sort_wall(batch())
        self.assertTrue(result.all_fit)
        placed = result.placements[0]
        self.assertEqual((placed.row, placed.col), (1, 2))
        self.assertEqual(placed.zone, "waist")
        self.assertEqual(placed.cubby, "R1C2")

    def test_batch_wave_puts_hot_orders_on_the_waist_row(self) -> None:
        payload = json.loads((EXAMPLES / "batch-wave.json").read_text())
        result = sort_wall(Batch.from_dict(payload))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.packed_count, 10)
        self.assertEqual(result.packed_orders, 8)
        self.assertEqual(result.labor_used_min, 10)
        self.assertEqual(cubby_of(result, "ORD-102"), (2, 2))
        self.assertEqual(cubby_of(result, "ORD-101"), (2, 3))
        self.assertEqual(cubby_of(result, "ORD-108"), (2, 4))
        self.assertEqual(cubby_of(result, "ORD-105"), (2, 1))
        self.assertEqual(cubby_of(result, "ORD-104"), (1, 3))
        self.assertEqual(cubby_of(result, "ORD-103"), (1, 2))
        self.assertEqual(cubby_of(result, "ORD-106"), (3, 2))
        self.assertEqual(cubby_of(result, "ORD-107"), (3, 3))
        waist = {item.order_id for item in result.placements if item.zone == "waist"}
        self.assertEqual(waist, {"ORD-101", "ORD-102", "ORD-105", "ORD-108"})

    def test_auto_keeps_same_carrier_adjacent(self) -> None:
        payload = json.loads((EXAMPLES / "batch-wave.json").read_text())
        result = sort_wall(Batch.from_dict(payload))
        ups = {
            (item.row, item.col)
            for item in result.placements
            if item.order_id in {"ORD-101", "ORD-103", "ORD-104", "ORD-108"}
        }
        self.assertEqual(ups, {(2, 3), (2, 4), (1, 2), (1, 3)})

    def test_labor_cap_leaves_the_smallest_order(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text())
        result = sort_wall(Batch.from_dict(payload))
        self.assertEqual(result.packed_count, 3)
        self.assertEqual(result.labor_used_min, 3)
        packed = {item.order_id for item in result.placements}
        self.assertEqual(packed, {"ORD-BIG", "ORD-MID"})
        self.assertEqual(result.leftover[0]["order_id"], "ORD-SMALL")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")

    def test_poster_is_too_big_and_dumbbell_is_too_heavy(self) -> None:
        payload = json.loads((EXAMPLES / "too-big.json").read_text())
        result = sort_wall(Batch.from_dict(payload))
        self.assertEqual(result.packed_orders, 1)
        by_order = {item["order_id"]: item["reason"] for item in result.leftover}
        self.assertEqual(by_order["ORD-POLE"], "too-big")
        self.assertEqual(by_order["ORD-HEAVY"], "too-heavy")

    def test_chill_unit_is_leftover_on_an_ambient_wall(self) -> None:
        payload = json.loads((EXAMPLES / "temp-mismatch.json").read_text())
        result = sort_wall(Batch.from_dict(payload))
        self.assertEqual(result.packed_orders, 3)
        self.assertEqual(result.leftover[0]["order_id"], "ORD-COLD")
        self.assertEqual(result.leftover[0]["reason"], "temp")
        packed = {item.order_id for item in result.placements}
        self.assertEqual(packed, {"ORD-DRY1", "ORD-DRY2", "ORD-DRY3"})

    def test_mixed_wall_takes_chill(self) -> None:
        result = sort_wall(
            batch(orders=[order(id="COLD", lines=[line(sku="GEL", temp="chill")])])
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.placements[0].temp, "chill")

    def test_volume_overflow_is_too_big(self) -> None:
        fat = line(sku="PILLOW", length_mm=350, width_mm=280, height_mm=300, quantity=3)
        result = sort_wall(batch(orders=[order(id="FAT", lines=[fat])]))
        self.assertEqual(result.leftover[0]["reason"], "too-big")
        self.assertEqual(result.packed_count, 0)

    def test_full_wall_leaves_no_cubby(self) -> None:
        orders = [
            order(id=f"ORD-{i}", carrier="UPS", lines=[line(sku=f"SKU-{i}")])
            for i in range(7)
        ]
        result = sort_wall(batch(orders=orders))
        self.assertEqual(result.packed_orders, 6)
        self.assertEqual(result.leftover[0]["order_id"], "ORD-6")
        self.assertEqual(result.leftover[0]["reason"], "no-cubby")

    def test_compact_keeps_small_orders_and_leaves_the_large_one(self) -> None:
        small = [
            order(id=f"S{i}", carrier="UPS", lines=[line(sku=f"SOCK-{i}")])
            for i in range(6)
        ]
        large = order(
            id="LARGE",
            carrier="FEDEX",
            lines=[line(sku="HOOD", length_mm=300, width_mm=250, height_mm=80, quantity=2)],
        )
        compact = sort_wall(batch(strategy="compact", orders=small + [large]))
        auto = sort_wall(batch(strategy="auto", orders=small + [large]))
        self.assertEqual(compact.packed_orders, 6)
        self.assertEqual(compact.leftover[0]["order_id"], "LARGE")
        self.assertEqual(compact.leftover[0]["reason"], "no-cubby")
        self.assertEqual(auto.packed_orders, 6)
        self.assertIn("LARGE", {item.order_id for item in auto.placements})
        leftover_auto = {item["order_id"] for item in auto.leftover}
        self.assertEqual(leftover_auto, {"S5"})

    def test_carrier_strategy_fills_raster_blocks(self) -> None:
        orders = [
            order(id="U1", carrier="UPS", lines=[line(sku="A")]),
            order(id="F1", carrier="FEDEX", lines=[line(sku="B")]),
            order(id="U2", carrier="UPS", lines=[line(sku="C")]),
        ]
        result = sort_wall(batch(strategy="carrier", orders=orders))
        self.assertEqual(cubby_of(result, "F1"), (1, 1))
        self.assertEqual(cubby_of(result, "U1"), (1, 2))
        self.assertEqual(cubby_of(result, "U2"), (1, 3))

    def test_priority_uses_golden_cells_first(self) -> None:
        orders = [
            order(id="COLD", carrier="UPS", priority=3, lines=[line(sku="BOOK")]),
            order(id="HOT", carrier="FEDEX", priority=1, lines=[line(sku="TEE")]),
        ]
        result = sort_wall(batch(strategy="priority", orders=orders))
        self.assertEqual(cubby_of(result, "HOT"), (1, 2))
        self.assertEqual(cubby_of(result, "COLD"), (1, 1))

    def test_quantity_expands_unique_ids(self) -> None:
        result = sort_wall(
            batch(orders=[order(lines=[line(sku="TEE", quantity=2)])])
        )
        ids = [item.piece_id for item in result.placements]
        self.assertEqual(ids, ["ORD-1-L1-1", "ORD-1-L1-2"])

    def test_one_order_never_shares_a_cubby(self) -> None:
        result = sort_wall(
            batch(
                orders=[
                    order(id="A", lines=[line(sku="TEE", quantity=2)]),
                    order(id="B", lines=[line(sku="CAP")]),
                ]
            )
        )
        cells = {(item.row, item.col, item.order_id) for item in result.placements}
        self.assertEqual(len({(row, col) for row, col, _ in cells}), 2)

    def test_duplicate_order_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            batch(orders=[order(id="SAME"), order(id="SAME", lines=[line(sku="CAP")])])

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            batch(strategy="zigzag")


if __name__ == "__main__":
    unittest.main()
