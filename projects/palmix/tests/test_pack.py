from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from palmix.model import Build, CaseSpec
from palmix.pack import PackResult, _overlaps, pack

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def case(sku: str, store: str, **kwargs) -> dict:
    row = {
        "sku": sku,
        "store": store,
        "family": kwargs.pop("family", "grocery"),
        "temp": "dry",
        "length_mm": 400,
        "width_mm": 300,
        "height_mm": 200,
        "weight_kg": 6,
        "quantity": 1,
        "crushable": False,
    }
    row.update(kwargs)
    return row


def build(**kwargs) -> Build:
    payload = {
        "deck": {"preset": "gma_48"},
        "strategy": "auto",
        "store_lock": True,
        "cases": [case("A", "12")],
    }
    payload.update(kwargs)
    return Build.from_dict(payload)


class PackTests(unittest.TestCase):
    def test_single_case_sits_on_origin(self) -> None:
        result = pack(build())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.pallet_count, 1)
        placed = result.placements[0]
        self.assertEqual(placed.pallet_id, "P1")
        self.assertEqual((placed.x, placed.y, placed.z), (0, 0, 0))

    def test_two_cases_sit_side_by_side(self) -> None:
        result = pack(
            Build.from_dict(
                {
                    "deck": {
                        "length_mm": 800,
                        "width_mm": 400,
                        "height_mm": 400,
                        "max_weight_kg": 100,
                    },
                    "allow_rotation": False,
                    "cases": [
                        case("LEFT", "12", length_mm=400, width_mm=400, height_mm=200),
                        case("RIGHT", "12", length_mm=400, width_mm=400, height_mm=200),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.pallet_count, 1)
        xs = sorted(item.x for item in result.placements)
        self.assertEqual(xs, [0, 400])

    def test_second_case_stacks_when_floor_is_full(self) -> None:
        result = pack(
            Build.from_dict(
                {
                    "deck": {
                        "length_mm": 400,
                        "width_mm": 400,
                        "height_mm": 800,
                        "max_weight_kg": 100,
                    },
                    "allow_rotation": False,
                    "cases": [
                        case("BOTTOM", "12", length_mm=400, width_mm=400, height_mm=300),
                        case("TOP", "12", length_mm=400, width_mm=400, height_mm=300),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        zs = sorted(item.z for item in result.placements)
        self.assertEqual(zs, [0, 300])

    def test_store_lock_opens_a_second_pallet(self) -> None:
        result = pack(Build.from_dict(json.loads((EXAMPLES / "store-lock.json").read_text())))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.pallet_count, 2)
        by_store = {row["store"]: row["id"] for row in result.pallets}
        self.assertEqual(set(by_store), {"04", "21"})
        self.assertNotEqual(by_store["04"], by_store["21"])

    def test_store_mix_allowed_when_lock_is_off(self) -> None:
        result = pack(
            build(
                store_lock=False,
                cases=[case("A", "12"), case("B", "21")],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.pallet_count, 1)

    def test_crushable_stays_on_top_of_heavy(self) -> None:
        result = pack(
            Build.from_dict(
                {
                    "deck": {
                        "length_mm": 400,
                        "width_mm": 400,
                        "height_mm": 700,
                        "max_weight_kg": 80,
                    },
                    "cases": [
                        case("CHIPS", "12", family="snack", crushable=True, weight_kg=2, height_mm=200),
                        case("WATER", "12", family="bev", weight_kg=12, height_mm=300),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        by_sku = {item.sku: item for item in result.placements}
        self.assertEqual(by_sku["WATER"].z, 0)
        self.assertEqual(by_sku["CHIPS"].z, 300)

    def test_stacking_on_crushable_is_left_behind(self) -> None:
        result = pack(
            Build.from_dict(
                {
                    "deck": {
                        "length_mm": 400,
                        "width_mm": 400,
                        "height_mm": 500,
                        "max_weight_kg": 80,
                        "max_pallets": 1,
                    },
                    "cases": [
                        case("CHIPS", "12", family="snack", crushable=True, quantity=2, height_mm=200),
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.packed_count, 1)
        self.assertEqual(result.leftover[0]["reason"], "crush")

    def test_payload_cap_leaves_anvil_behind(self) -> None:
        result = pack(Build.from_dict(json.loads((EXAMPLES / "too-heavy.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["sku"], "ANVIL")
        self.assertEqual(result.leftover[0]["reason"], "too-heavy")
        self.assertEqual(result.packed_count, 2)

    def test_temp_split_keeps_chill_off_a_dry_deck(self) -> None:
        result = pack(
            build(
                cases=[
                    case("DRY", "12", temp="dry"),
                    case("MILK", "12", temp="chill"),
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["sku"], "MILK")
        self.assertEqual(result.leftover[0]["reason"], "temp")

    def test_labor_cap_blocks_the_second_store(self) -> None:
        result = pack(Build.from_dict(json.loads((EXAMPLES / "labor-capped.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.packed_count, 1)
        self.assertEqual(result.placements[0].sku, "RICE-20")
        self.assertEqual(result.leftover[0]["sku"], "BEANS-12")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")
        self.assertEqual(result.labor_used_min, 9)

    def test_floor_rotation_makes_a_fit(self) -> None:
        payload = {
            "deck": {
                "length_mm": 400,
                "width_mm": 600,
                "height_mm": 300,
                "max_weight_kg": 40,
            },
            "cases": [
                case("TURN", "12", length_mm=600, width_mm=400, height_mm=200, this_side_up=True)
            ],
        }
        stuck = pack(Build.from_dict({**payload, "allow_rotation": False}))
        fitted = pack(Build.from_dict({**payload, "allow_rotation": True}))
        self.assertFalse(stuck.all_fit)
        self.assertTrue(fitted.all_fit)
        self.assertEqual(fitted.placements[0].length_mm, 400)
        self.assertEqual(fitted.placements[0].width_mm, 600)

    def test_oversize_case_is_left_behind(self) -> None:
        result = pack(
            build(
                cases=[
                    case("CRATE", "12", length_mm=3000, width_mm=2000, height_mm=2000),
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.placements, [])
        self.assertEqual(result.leftover[0]["reason"], "too-big")

    def test_mixed_stores_example_stays_inside_and_does_not_overlap(self) -> None:
        result = pack(Build.from_dict(json.loads((EXAMPLES / "mixed-stores.json").read_text())))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.packed_count, 24)
        self.assertEqual(result.pallet_count, 2)
        self._assert_legal(result)

    def test_family_prefers_the_fuller_same_store_pallet(self) -> None:
        result = pack(
            Build.from_dict(
                {
                    "deck": {"preset": "gma_48", "max_pallets": 4},
                    "store_lock": True,
                    "cases": [
                        case("PASTA", "12", family="grocery", quantity=2),
                        case("SOAP", "12", family="hpc", quantity=1),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.pallet_count, 1)

    def _assert_legal(self, result: PackResult) -> None:
        box = result.deck
        for item in result.placements:
            self.assertGreaterEqual(item.x, 0)
            self.assertGreaterEqual(item.y, 0)
            self.assertGreaterEqual(item.z, 0)
            self.assertLessEqual(item.x2, box.length_mm)
            self.assertLessEqual(item.y2, box.width_mm)
            self.assertLessEqual(item.z2, box.height_mm)
        for i, left in enumerate(result.placements):
            for right in result.placements[i + 1 :]:
                if left.pallet_id != right.pallet_id:
                    continue
                self.assertFalse(_overlaps(left, right), f"{left} overlaps {right}")


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_sku_store(self) -> None:
        with self.assertRaises(ValueError):
            Build.from_dict(
                {
                    "deck": {"preset": "eur"},
                    "cases": [case("A", "12"), case("A", "12", length_mm=200)],
                }
            )

    def test_same_sku_two_stores_is_ok(self) -> None:
        wave = Build.from_dict(
            {
                "deck": {"preset": "eur"},
                "cases": [case("A", "12"), case("A", "21")],
            }
        )
        self.assertEqual(len(wave.cases), 2)

    def test_rejects_empty_build(self) -> None:
        with self.assertRaises(ValueError):
            Build.from_dict({"deck": {"preset": "gma_48"}, "cases": []})

    def test_expand_respects_quantity(self) -> None:
        spec = CaseSpec("A", "12", "grocery", "dry", 1, 1, 1, 1, quantity=4)
        wave = build(cases=[spec.as_dict()])
        self.assertEqual(len(wave.expand()), 4)


if __name__ == "__main__":
    unittest.main()
