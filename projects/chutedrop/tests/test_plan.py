from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chutedrop.model import Wave
from chutedrop.plan import plan_bank

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def carton(id: str, dest: str, **kwargs) -> dict:
    row = {
        "id": id,
        "dest": dest,
        "carrier": "OWN",
        "length_mm": 300,
        "width_mm": 200,
        "height_mm": 150,
        "weight_kg": 2.0,
        "temp": "ambient",
        "priority": 2,
    }
    row.update(kwargs)
    return row


def wave(**kwargs) -> Wave:
    payload = {
        "bank": {"preset": "mini_1x3"},
        "strategy": "auto",
        "cartons": [carton("C-1", "STORE-1")],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


def chute_of(result, carton_id: str) -> tuple[int, int]:
    placed = {item.carton_id: item for item in result.placements}
    item = placed[carton_id]
    return item.row, item.col


class PlanTests(unittest.TestCase):
    def test_single_carton_sits_on_induction_center(self) -> None:
        result = plan_bank(wave())
        self.assertTrue(result.all_fit)
        placed = result.placements[0]
        self.assertEqual((placed.row, placed.col), (1, 2))
        self.assertEqual(placed.zone, "induction")
        self.assertEqual(placed.chute, "R1C2")

    def test_store_wave_puts_hot_dests_on_induction(self) -> None:
        payload = json.loads((EXAMPLES / "store-wave.json").read_text())
        result = plan_bank(Wave.from_dict(payload))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.packed_cartons, 14)
        self.assertEqual(result.dest_count, 5)
        self.assertEqual(result.used_chutes, 5)
        self.assertEqual(result.labor_used_min, 14)
        self.assertEqual(chute_of(result, "C-121"), (1, 3))
        self.assertEqual(chute_of(result, "C-081"), (1, 2))
        self.assertEqual(chute_of(result, "C-211"), (1, 4))
        self.assertEqual(chute_of(result, "C-041"), (1, 1))
        self.assertEqual(chute_of(result, "C-331"), (1, 5))
        induction = {item.carton_id for item in result.placements if item.zone == "induction"}
        self.assertEqual(len(induction), 14)

    def test_auto_tops_off_the_same_dest(self) -> None:
        payload = json.loads((EXAMPLES / "store-wave.json").read_text())
        result = plan_bank(Wave.from_dict(payload))
        store12 = {
            (item.row, item.col)
            for item in result.placements
            if item.dest == "STORE-12"
        }
        self.assertEqual(store12, {(1, 3)})
        store08 = {
            (item.row, item.col)
            for item in result.placements
            if item.dest == "STORE-08"
        }
        self.assertEqual(store08, {(1, 2)})

    def test_labor_cap_leaves_the_last_cartons(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text())
        result = plan_bank(Wave.from_dict(payload))
        self.assertEqual(result.packed_cartons, 4)
        self.assertEqual(result.labor_used_min, 4)
        packed = {item.carton_id for item in result.placements}
        self.assertEqual(packed, {"C-1", "C-2", "C-3", "C-4"})
        self.assertEqual([item["id"] for item in result.leftover], ["C-5", "C-6"])
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")

    def test_chute_full_opens_a_second_mouth_then_stops(self) -> None:
        payload = json.loads((EXAMPLES / "chute-full.json").read_text())
        result = plan_bank(Wave.from_dict(payload))
        self.assertEqual(result.packed_cartons, 6)
        self.assertEqual(result.used_chutes, 3)
        self.assertEqual(chute_of(result, "C-1"), (1, 2))
        self.assertEqual(chute_of(result, "C-3"), (1, 1))
        self.assertEqual(chute_of(result, "C-5"), (1, 3))
        self.assertEqual(result.leftover[0]["id"], "C-7")
        self.assertEqual(result.leftover[0]["reason"], "chute-full")

    def test_pole_is_too_big_and_heavy_is_too_heavy(self) -> None:
        payload = json.loads((EXAMPLES / "too-big.json").read_text())
        result = plan_bank(Wave.from_dict(payload))
        self.assertEqual(result.packed_cartons, 1)
        self.assertEqual(result.placements[0].carton_id, "C-OK")
        by_id = {item["id"]: item["reason"] for item in result.leftover}
        self.assertEqual(by_id["C-POLE"], "too-big")
        self.assertEqual(by_id["C-HEAVY"], "too-heavy")

    def test_ambient_carton_is_leftover_on_a_chill_bank(self) -> None:
        payload = json.loads((EXAMPLES / "temp-mismatch.json").read_text())
        result = plan_bank(Wave.from_dict(payload))
        self.assertEqual(result.packed_cartons, 2)
        self.assertEqual(result.leftover[0]["id"], "C-DRY")
        self.assertEqual(result.leftover[0]["reason"], "temp")
        packed = {item.carton_id for item in result.placements}
        self.assertEqual(packed, {"C-COLD1", "C-COLD2"})
        self.assertEqual(chute_of(result, "C-COLD1"), (1, 2))

    def test_mixed_bank_takes_chill(self) -> None:
        result = plan_bank(
            wave(
                cartons=[
                    carton("COLD", "STORE-G", temp="chill"),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.placements[0].temp, "chill")

    def test_volume_overflow_is_too_big(self) -> None:
        fat = carton(
            "FAT",
            "STORE-1",
            length_mm=650,
            width_mm=390,
            height_mm=390,
        )
        result = plan_bank(wave(cartons=[fat]))
        self.assertEqual(result.leftover[0]["reason"], "too-big")
        self.assertEqual(result.packed_cartons, 0)

    def test_full_bank_leaves_no_chute_for_a_new_dest(self) -> None:
        cartons = [carton(f"C-{i}", f"STORE-{i}") for i in range(4)]
        result = plan_bank(wave(cartons=cartons))
        self.assertEqual(result.packed_cartons, 3)
        self.assertEqual(result.leftover[0]["id"], "C-3")
        self.assertEqual(result.leftover[0]["reason"], "no-chute")

    def test_compact_keeps_small_cartons_and_leaves_the_large_one(self) -> None:
        small = [carton(f"S{i}", f"STORE-{i}") for i in range(3)]
        large = carton(
            "LARGE",
            "STORE-X",
            length_mm=500,
            width_mm=350,
            height_mm=300,
            priority=1,
        )
        compact = plan_bank(wave(strategy="compact", cartons=small + [large]))
        auto = plan_bank(wave(strategy="auto", cartons=small + [large]))
        self.assertEqual(compact.packed_cartons, 3)
        self.assertEqual(compact.leftover[0]["id"], "LARGE")
        self.assertEqual(compact.leftover[0]["reason"], "no-chute")
        self.assertIn("LARGE", {item.carton_id for item in auto.placements})
        leftover_auto = {item["id"] for item in auto.leftover}
        self.assertEqual(leftover_auto, {"S2"})

    def test_dest_strategy_fills_raster_blocks(self) -> None:
        result = plan_bank(
            wave(
                strategy="dest",
                cartons=[
                    carton("B1", "STORE-B"),
                    carton("A1", "STORE-A"),
                    carton("A2", "STORE-A"),
                ],
            )
        )
        self.assertEqual(chute_of(result, "A1"), (1, 1))
        self.assertEqual(chute_of(result, "A2"), (1, 1))
        self.assertEqual(chute_of(result, "B1"), (1, 2))

    def test_carrier_keeps_same_carrier_adjacent(self) -> None:
        result = plan_bank(
            wave(
                strategy="carrier",
                bank={"preset": "bank_1x6"},
                cartons=[
                    carton("P1", "STORE-9", carrier="PARCEL"),
                    carton("O1", "STORE-1", carrier="OWN"),
                    carton("O2", "STORE-2", carrier="OWN"),
                    carton("P2", "STORE-8", carrier="PARCEL"),
                ],
            )
        )
        own = {
            (item.row, item.col)
            for item in result.placements
            if item.carrier == "OWN"
        }
        parcel = {
            (item.row, item.col)
            for item in result.placements
            if item.carrier == "PARCEL"
        }
        self.assertEqual(own, {(1, 1), (1, 2)})
        self.assertEqual(parcel, {(1, 3), (1, 4)})

    def test_dests_never_share_a_chute(self) -> None:
        result = plan_bank(
            wave(
                cartons=[
                    carton("A", "STORE-A"),
                    carton("B", "STORE-B"),
                ]
            )
        )
        cells = {(item.row, item.col, item.dest) for item in result.placements}
        self.assertEqual(len({(row, col) for row, col, _ in cells}), 2)

    def test_duplicate_carton_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wave(cartons=[carton("SAME", "STORE-1"), carton("SAME", "STORE-2")])

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wave(strategy="zigzag")


if __name__ == "__main__":
    unittest.main()
