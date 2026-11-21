from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from allocpush.model import Wave
from allocpush.push import plan, store_need


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def wave(**kwargs) -> Wave:
    payload = {
        "wave": "WAVE-T",
        "dc": "DC-North",
        "policy": "fair_share",
        "holdback_pct": 0,
        "break_case": False,
        "skus": [
            {
                "sku": "TEE-NAVY",
                "case_pack": 12,
                "inner_pack": 6,
                "dc_on_hand": 120,
            }
        ],
        "stores": [
            {
                "store_id": "ST-01",
                "name": "Downtown",
                "grade": "A",
                "books": [
                    {
                        "sku": "TEE-NAVY",
                        "on_hand": 0,
                        "forecast": 24,
                        "min_face": 12,
                        "max_cap": 96,
                    }
                ],
            }
        ],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


def line_map(result, sku: str) -> dict[str, dict]:
    for item in result.skus:
        if item.sku == sku:
            return {row.store_id: row for row in item.lines}
    raise KeyError(sku)


class PushTests(unittest.TestCase):
    def test_balanced_example_fills_every_store(self) -> None:
        result = plan(Wave.from_dict(json.loads((EXAMPLES / "balanced-push.json").read_text())))
        self.assertTrue(result.all_filled)
        self.assertEqual(result.push_units, 156)
        self.assertEqual(result.short_units, 0)
        tee = line_map(result, "TEE-NAVY")
        self.assertEqual(tee["ST-01"].push_packs, 6)
        self.assertEqual(tee["ST-04"].push_packs, 4)
        self.assertEqual(tee["ST-09"].push_packs, 1)
        hood = line_map(result, "HOOD-GRY")
        self.assertEqual(hood["ST-01"].push_units, 12)
        self.assertEqual(hood["ST-04"].push_units, 12)
        self.assertEqual(hood["ST-09"].push_units, 0)
        self.assertEqual(hood["ST-09"].need_units, 0)

    def test_short_stock_fair_share_uses_largest_remainder(self) -> None:
        result = plan(Wave.from_dict(json.loads((EXAMPLES / "short-stock.json").read_text())))
        self.assertFalse(result.all_filled)
        self.assertEqual(result.skus[0].push_packs, 10)
        self.assertEqual(result.skus[0].dc_remaining, 0)
        lines = line_map(result, "TEE-NAVY")
        # 10 cases, weights 24/10/4/15, Hamilton leftover to ST-04, ST-12, ST-09
        self.assertEqual(lines["ST-01"].push_packs, 4)
        self.assertEqual(lines["ST-04"].push_packs, 2)
        self.assertEqual(lines["ST-09"].push_packs, 1)
        self.assertEqual(lines["ST-12"].push_packs, 3)
        self.assertEqual(lines["ST-01"].short_units, 48)
        self.assertGreater(lines["ST-01"].push_units, lines["ST-09"].push_units)

    def test_grade_first_fills_a_stores_before_b(self) -> None:
        result = plan(Wave.from_dict(json.loads((EXAMPLES / "grade-first.json").read_text())))
        lines = line_map(result, "TEE-NAVY")
        self.assertEqual(lines["ST-01"].push_packs, 8)
        self.assertEqual(lines["ST-01"].short_units, 0)
        self.assertEqual(lines["ST-12"].push_packs, 2)
        self.assertEqual(lines["ST-04"].push_packs, 0)
        self.assertEqual(lines["ST-09"].push_packs, 0)

    def test_need_fill_feeds_the_hungriest_store(self) -> None:
        payload = json.loads((EXAMPLES / "short-stock.json").read_text())
        payload["policy"] = "need_fill"
        result = plan(Wave.from_dict(payload))
        lines = line_map(result, "TEE-NAVY")
        self.assertEqual(lines["ST-01"].push_packs, 8)
        self.assertEqual(lines["ST-12"].push_packs, 2)
        self.assertEqual(lines["ST-04"].push_packs, 0)
        self.assertEqual(lines["ST-09"].push_packs, 0)

    def test_holdback_stays_at_the_dc(self) -> None:
        result = plan(Wave.from_dict(json.loads((EXAMPLES / "holdback.json").read_text())))
        sku = result.skus[0]
        self.assertEqual(sku.holdback_units, 48)
        self.assertEqual(sku.available_packs, 8)
        self.assertTrue(result.all_filled)
        self.assertEqual(sku.push_units, 192)
        self.assertEqual(sku.dc_remaining, 48)
        lines = line_map(result, "SOCK-WHT")
        self.assertEqual(lines["ST-01"].push_packs, 4)
        self.assertEqual(lines["ST-04"].push_packs, 2)
        self.assertEqual(lines["ST-09"].push_packs, 2)

    def test_case_pack_rounds_need_up(self) -> None:
        result = plan(
            wave(
                skus=[{"sku": "TEE-NAVY", "case_pack": 12, "inner_pack": 6, "dc_on_hand": 48}],
                stores=[
                    {
                        "store_id": "ST-01",
                        "grade": "B",
                        "books": [
                            {
                                "sku": "TEE-NAVY",
                                "on_hand": 0,
                                "forecast": 13,
                                "min_face": 0,
                                "max_cap": 96,
                            }
                        ],
                    }
                ],
            )
        )
        line = result.skus[0].lines[0]
        self.assertEqual(line.need_units, 13)
        self.assertEqual(line.need_packs, 2)
        self.assertEqual(line.push_units, 24)
        self.assertEqual(line.short_units, 0)

    def test_capacity_blocks_an_extra_case(self) -> None:
        result = plan(
            wave(
                skus=[{"sku": "TEE-NAVY", "case_pack": 12, "inner_pack": 6, "dc_on_hand": 48}],
                stores=[
                    {
                        "store_id": "ST-01",
                        "grade": "B",
                        "books": [
                            {
                                "sku": "TEE-NAVY",
                                "on_hand": 0,
                                "forecast": 13,
                                "min_face": 0,
                                "max_cap": 13,
                            }
                        ],
                    }
                ],
            )
        )
        line = result.skus[0].lines[0]
        self.assertEqual(line.need_packs, 1)
        self.assertEqual(line.push_units, 12)
        self.assertEqual(line.short_units, 1)

    def test_min_face_lifts_target_above_forecast(self) -> None:
        result = plan(
            wave(
                stores=[
                    {
                        "store_id": "ST-01",
                        "grade": "A",
                        "books": [
                            {
                                "sku": "TEE-NAVY",
                                "on_hand": 0,
                                "forecast": 10,
                                "min_face": 24,
                                "max_cap": 100,
                            }
                        ],
                    }
                ]
            )
        )
        line = result.skus[0].lines[0]
        self.assertEqual(line.target, 24)
        self.assertEqual(line.need_packs, 2)

    def test_break_case_ships_inner_packs(self) -> None:
        full_case = plan(
            wave(
                break_case=False,
                skus=[{"sku": "TEE-NAVY", "case_pack": 12, "inner_pack": 4, "dc_on_hand": 12}],
                stores=[
                    {
                        "store_id": "ST-01",
                        "grade": "B",
                        "books": [
                            {
                                "sku": "TEE-NAVY",
                                "on_hand": 0,
                                "forecast": 8,
                                "min_face": 0,
                                "max_cap": 48,
                            }
                        ],
                    }
                ],
            )
        )
        inner = plan(
            wave(
                break_case=True,
                skus=[{"sku": "TEE-NAVY", "case_pack": 12, "inner_pack": 4, "dc_on_hand": 12}],
                stores=[
                    {
                        "store_id": "ST-01",
                        "grade": "B",
                        "books": [
                            {
                                "sku": "TEE-NAVY",
                                "on_hand": 0,
                                "forecast": 8,
                                "min_face": 0,
                                "max_cap": 48,
                            }
                        ],
                    }
                ],
            )
        )
        self.assertEqual(full_case.skus[0].lines[0].push_units, 12)
        self.assertEqual(inner.skus[0].pack, 4)
        self.assertEqual(inner.skus[0].lines[0].push_units, 8)
        self.assertEqual(inner.skus[0].dc_remaining, 4)

    def test_store_at_target_gets_nothing(self) -> None:
        result = plan(
            wave(
                stores=[
                    {
                        "store_id": "ST-01",
                        "grade": "A",
                        "books": [
                            {
                                "sku": "TEE-NAVY",
                                "on_hand": 48,
                                "forecast": 48,
                                "min_face": 12,
                                "max_cap": 96,
                            }
                        ],
                    }
                ]
            )
        )
        line = result.skus[0].lines[0]
        self.assertEqual(line.need_units, 0)
        self.assertEqual(line.push_units, 0)
        self.assertTrue(result.all_filled)

    def test_unknown_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wave(policy="random")

    def test_store_need_never_exceeds_capacity_packs(self) -> None:
        store = Wave.from_dict(
            {
                "wave": "W",
                "skus": [{"sku": "X", "case_pack": 10, "dc_on_hand": 100}],
                "stores": [
                    {
                        "store_id": "S1",
                        "grade": "B",
                        "books": [
                            {
                                "sku": "X",
                                "on_hand": 8,
                                "forecast": 100,
                                "min_face": 0,
                                "max_cap": 25,
                            }
                        ],
                    }
                ],
            }
        ).stores[0]
        need = store_need(store, store.books[0], pack=10)
        self.assertEqual(need.need_packs, 1)
        self.assertEqual(need.target, 25)
