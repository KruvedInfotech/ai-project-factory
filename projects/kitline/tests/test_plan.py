from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kitline.model import Wave
from kitline.plan import plan_line

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def bom(*pairs: tuple[str, int]) -> list[dict]:
    return [{"sku": sku, "quantity": qty} for sku, qty in pairs]


def kit(sku: str, **kwargs) -> dict:
    row = {
        "sku": sku,
        "length_mm": 250,
        "width_mm": 180,
        "height_mm": 70,
        "weight_kg": 0.5,
        "temp": "ambient",
        "bom": bom(("TEE", 1)),
    }
    row.update(kwargs)
    return row


def build(id: str, kit_sku: str, **kwargs) -> dict:
    row = {"id": id, "kit_sku": kit_sku, "quantity": 1, "priority": 2}
    row.update(kwargs)
    return row


def wave(**kwargs) -> Wave:
    payload = {
        "line": {"preset": "mini_1x3"},
        "strategy": "auto",
        "inventory": [{"sku": "TEE", "on_hand": 20}],
        "kits": [kit("STARTER")],
        "builds": [build("WO-1", "STARTER")],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


def bench_of(result, build_id: str) -> tuple[int, int]:
    placed = {item.build_id: item for item in result.placements}
    item = placed[build_id]
    return item.row, item.col


class PlanTests(unittest.TestCase):
    def test_single_build_sits_on_the_aisle(self) -> None:
        result = plan_line(wave())
        self.assertTrue(result.all_fit)
        placed = result.placements[0]
        self.assertEqual((placed.row, placed.col), (1, 2))
        self.assertEqual(placed.zone, "aisle")
        self.assertEqual(placed.bench, "R1C2")

    def test_gift_wave_puts_hot_kits_on_the_aisle_row(self) -> None:
        payload = json.loads((EXAMPLES / "gift-wave.json").read_text())
        result = plan_line(Wave.from_dict(payload))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.packed_kits, 27)
        self.assertEqual(result.packed_builds, 6)
        self.assertEqual(result.labor_used_min, 81)
        self.assertEqual(bench_of(result, "WO-101"), (2, 2))
        self.assertEqual(bench_of(result, "WO-102"), (2, 1))
        self.assertEqual(bench_of(result, "WO-103"), (2, 3))
        self.assertEqual(bench_of(result, "WO-105"), (1, 2))
        self.assertEqual(bench_of(result, "WO-104"), (1, 1))
        self.assertEqual(bench_of(result, "WO-106"), (1, 3))
        aisle = {item.build_id for item in result.placements if item.zone == "aisle"}
        self.assertEqual(aisle, {"WO-101", "WO-102", "WO-103"})

    def test_auto_keeps_same_kit_adjacent(self) -> None:
        payload = json.loads((EXAMPLES / "gift-wave.json").read_text())
        result = plan_line(Wave.from_dict(payload))
        gifts = {
            (item.row, item.col)
            for item in result.placements
            if item.kit_sku == "GIFT-SET"
        }
        self.assertEqual(gifts, {(2, 2), (2, 1)})
        starters = {
            (item.row, item.col)
            for item in result.placements
            if item.kit_sku == "STARTER"
        }
        self.assertEqual(starters, {(1, 2), (1, 3)})

    def test_labor_cap_leaves_the_smallest_build(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text())
        result = plan_line(Wave.from_dict(payload))
        self.assertEqual(result.packed_kits, 4)
        self.assertEqual(result.labor_used_min, 8)
        packed = {item.build_id for item in result.placements}
        self.assertEqual(packed, {"WO-BIG", "WO-MID"})
        self.assertEqual(result.leftover[0]["id"], "WO-SMALL")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")

    def test_short_parts_leave_the_second_gift_set(self) -> None:
        payload = json.loads((EXAMPLES / "short-parts.json").read_text())
        result = plan_line(Wave.from_dict(payload))
        packed = {item.build_id for item in result.placements}
        self.assertEqual(packed, {"WO-101", "WO-103"})
        short = result.leftover[0]
        self.assertEqual(short["id"], "WO-102")
        self.assertEqual(short["reason"], "short")
        self.assertEqual(short["missing_sku"], "TEE")
        self.assertEqual(short["need"], 4)
        self.assertEqual(short["on_hand"], 2)
        tee_left = {row["sku"]: row["on_hand"] for row in result.inventory_left}["TEE"]
        self.assertEqual(tee_left, 2)

    def test_poster_is_too_big_heavy_and_over_run(self) -> None:
        payload = json.loads((EXAMPLES / "too-big.json").read_text())
        result = plan_line(Wave.from_dict(payload))
        self.assertEqual(result.packed_builds, 1)
        self.assertEqual(result.placements[0].build_id, "WO-OK")
        by_id = {item["id"]: item["reason"] for item in result.leftover}
        self.assertEqual(by_id["WO-POLE"], "too-big")
        self.assertEqual(by_id["WO-HEAVY"], "too-heavy")
        self.assertEqual(by_id["WO-RUN"], "over-run")

    def test_chill_kit_is_leftover_on_an_ambient_line(self) -> None:
        payload = json.loads((EXAMPLES / "temp-mismatch.json").read_text())
        result = plan_line(Wave.from_dict(payload))
        self.assertEqual(result.packed_builds, 2)
        self.assertEqual(result.leftover[0]["id"], "WO-COLD")
        self.assertEqual(result.leftover[0]["reason"], "temp")
        packed = {item.build_id for item in result.placements}
        self.assertEqual(packed, {"WO-DRY1", "WO-DRY2"})

    def test_mixed_line_takes_chill(self) -> None:
        result = plan_line(
            wave(
                inventory=[
                    {"sku": "TEE", "on_hand": 4},
                    {"sku": "YOGURT", "on_hand": 8},
                ],
                kits=[
                    kit(
                        "MEAL-KIT",
                        temp="chill",
                        bom=bom(("YOGURT", 2)),
                    )
                ],
                builds=[build("COLD", "MEAL-KIT", quantity=2)],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.placements[0].temp, "chill")

    def test_volume_overflow_is_too_big(self) -> None:
        fat = kit(
            "PILLOW",
            length_mm=650,
            width_mm=480,
            height_mm=390,
            bom=bom(("TEE", 1)),
        )
        result = plan_line(wave(kits=[fat], builds=[build("FAT", "PILLOW")]))
        self.assertEqual(result.leftover[0]["reason"], "too-big")
        self.assertEqual(result.packed_builds, 0)

    def test_full_line_leaves_no_bench(self) -> None:
        builds = [build(f"WO-{i}", "STARTER") for i in range(4)]
        result = plan_line(wave(builds=builds))
        self.assertEqual(result.packed_builds, 3)
        self.assertEqual(result.leftover[0]["id"], "WO-3")
        self.assertEqual(result.leftover[0]["reason"], "no-bench")

    def test_compact_keeps_small_runs_and_leaves_the_large_one(self) -> None:
        small = [build(f"S{i}", "STARTER") for i in range(3)]
        large = build("LARGE", "STARTER", quantity=8)
        compact = plan_line(wave(strategy="compact", labor_minutes=40, builds=small + [large]))
        auto = plan_line(wave(strategy="auto", labor_minutes=40, builds=small + [large]))
        self.assertEqual(compact.packed_builds, 3)
        self.assertEqual(compact.leftover[0]["id"], "LARGE")
        self.assertEqual(compact.leftover[0]["reason"], "no-bench")
        self.assertEqual(auto.packed_builds, 3)
        self.assertIn("LARGE", {item.build_id for item in auto.placements})
        leftover_auto = {item["id"] for item in auto.leftover}
        self.assertEqual(leftover_auto, {"S2"})

    def test_family_strategy_fills_raster_blocks(self) -> None:
        result = plan_line(
            wave(
                strategy="family",
                kits=[kit("ALPHA"), kit("BETA", bom=bom(("TEE", 1)))],
                builds=[
                    build("B1", "BETA"),
                    build("A1", "ALPHA"),
                    build("A2", "ALPHA"),
                ],
            )
        )
        self.assertEqual(bench_of(result, "A1"), (1, 1))
        self.assertEqual(bench_of(result, "A2"), (1, 2))
        self.assertEqual(bench_of(result, "B1"), (1, 3))

    def test_priority_uses_golden_cells_first(self) -> None:
        result = plan_line(
            wave(
                strategy="priority",
                kits=[kit("BOOK"), kit("GIFT", bom=bom(("TEE", 1)))],
                builds=[
                    build("COLD", "BOOK", priority=3),
                    build("HOT", "GIFT", priority=1),
                ],
            )
        )
        self.assertEqual(bench_of(result, "HOT"), (1, 2))
        self.assertEqual(bench_of(result, "COLD"), (1, 1))

    def test_bom_explodes_component_quantities(self) -> None:
        result = plan_line(
            wave(
                inventory=[{"sku": "TEE", "on_hand": 10}, {"sku": "MUG", "on_hand": 10}],
                kits=[kit("GIFT-SET", bom=bom(("TEE", 2), ("MUG", 1)))],
                builds=[build("WO-1", "GIFT-SET", quantity=3)],
            )
        )
        used = {row["sku"]: row["quantity"] for row in result.placements[0].components}
        self.assertEqual(used, {"TEE": 6, "MUG": 3})
        left = {row["sku"]: row["on_hand"] for row in result.inventory_left}
        self.assertEqual(left["TEE"], 4)
        self.assertEqual(left["MUG"], 7)

    def test_one_build_never_shares_a_bench(self) -> None:
        result = plan_line(
            wave(
                builds=[
                    build("A", "STARTER", quantity=2),
                    build("B", "STARTER"),
                ]
            )
        )
        cells = {(item.row, item.col, item.build_id) for item in result.placements}
        self.assertEqual(len({(row, col) for row, col, _ in cells}), 2)

    def test_duplicate_build_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wave(builds=[build("SAME", "STARTER"), build("SAME", "STARTER")])

    def test_unknown_kit_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wave(builds=[build("WO-1", "MISSING")])

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wave(strategy="zigzag")


if __name__ == "__main__":
    unittest.main()
