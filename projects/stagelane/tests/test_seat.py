from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stagelane.model import PalletSpec, Wave
from stagelane.seat import SeatResult, seat

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def pallet(pallet_id: str, carrier: str = "UPS", **kwargs) -> dict:
    row = {
        "id": pallet_id,
        "carrier": carrier,
        "priority": 2,
        "temp": "dry",
        "length_mm": 1200,
        "width_mm": 1000,
        "height_mm": 1400,
        "weight_kg": 400,
    }
    row.update(kwargs)
    return row


def wave(**kwargs) -> Wave:
    payload = {
        "yard": {"preset": "grocery"},
        "strategy": "auto",
        "pallets": [pallet("PAL-1", door=1)],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


class SeatTests(unittest.TestCase):
    def test_single_pallet_sits_at_the_door(self) -> None:
        result = seat(wave())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.seated_count, 1)
        placed = result.seats[0]
        self.assertEqual(placed.pallet_id, "PAL-1")
        self.assertEqual(placed.lane, "L1")
        self.assertEqual(placed.x_mm, 0)
        self.assertEqual(placed.stack_level, 0)

    def test_same_carrier_tops_off_the_open_lane(self) -> None:
        result = seat(
            wave(
                pallets=[
                    pallet("A", door=1, priority=1),
                    pallet("B", door=1, priority=2),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.pallet_id: item for item in result.seats}
        self.assertEqual(by_id["A"].lane, "L1")
        self.assertEqual(by_id["B"].lane, "L1")
        self.assertEqual(by_id["A"].x_mm, 0)
        self.assertEqual(by_id["B"].x_mm, 1200)

    def test_second_carrier_opens_a_new_lane(self) -> None:
        result = seat(
            wave(
                mix_carriers=False,
                pallets=[
                    pallet("UPS-1", "UPS", door=1, priority=1),
                    pallet("FDX-1", "FDX", door=2, priority=2),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.pallet_id: item for item in result.seats}
        self.assertEqual(by_id["UPS-1"].lane, "L1")
        self.assertEqual(by_id["FDX-1"].lane, "L2")

    def test_carrier_mix_leftover_when_the_only_lane_is_claimed(self) -> None:
        result = seat(
            Wave.from_dict(
                {
                    "yard": {
                        "preset": "parcel",
                        "lanes": [
                            {
                                "id": "P1",
                                "temp": "mixed",
                                "length_mm": 3600,
                                "width_mm": 1200,
                                "max_weight_kg": 2000,
                                "max_height_mm": 1800,
                                "door": 1,
                            }
                        ],
                    },
                    "mix_carriers": False,
                    "pallets": [
                        pallet("UPS-1", "UPS", door=1, priority=1),
                        pallet("FDX-1", "FDX", door=1, priority=2),
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.seats[0].pallet_id, "UPS-1")
        self.assertEqual(result.leftover[0]["id"], "FDX-1")
        self.assertEqual(result.leftover[0]["reason"], "carrier-mix")

    def test_mix_carriers_shares_the_lane(self) -> None:
        result = seat(
            Wave.from_dict(
                {
                    "yard": {
                        "lanes": [
                            {
                                "id": "P1",
                                "temp": "dry",
                                "length_mm": 3600,
                                "width_mm": 1200,
                                "max_weight_kg": 2000,
                                "max_height_mm": 1800,
                                "door": 1,
                            }
                        ]
                    },
                    "mix_carriers": True,
                    "pallets": [
                        pallet("UPS-1", "UPS", door=1, priority=1),
                        pallet("FDX-1", "FDX", door=1, priority=2),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual({item.lane for item in result.seats}, {"P1"})

    def test_door_mismatch_is_left_behind(self) -> None:
        result = seat(
            Wave.from_dict(
                {
                    "yard": {
                        "lanes": [
                            {
                                "id": "L1",
                                "temp": "dry",
                                "length_mm": 9600,
                                "width_mm": 1200,
                                "max_weight_kg": 8000,
                                "max_height_mm": 1800,
                                "door": 1,
                            }
                        ]
                    },
                    "mix_doors": False,
                    "pallets": [pallet("LATE", door=9)],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "door")

    def test_lane_full_example_leaves_the_third_cage(self) -> None:
        result = seat(Wave.from_dict(json.loads((EXAMPLES / "lane-full.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.seated_count, 2)
        self.assertEqual(result.seats[0].pallet_id, "CAG-01")
        self.assertEqual(result.seats[1].x_mm, 1200)
        self.assertEqual(result.leftover[0]["id"], "CAG-03")
        self.assertEqual(result.leftover[0]["reason"], "lane-full")

    def test_temp_split_keeps_dry_off_a_chill_dock(self) -> None:
        result = seat(Wave.from_dict(json.loads((EXAMPLES / "temp-block.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.seats[0].pallet_id, "PAL-40")
        self.assertEqual(result.leftover[0]["id"], "PAL-41")
        self.assertEqual(result.leftover[0]["reason"], "temp")

    def test_labor_cap_blocks_the_second_pallet(self) -> None:
        result = seat(Wave.from_dict(json.loads((EXAMPLES / "labor-capped.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.seated_count, 1)
        self.assertEqual(result.seats[0].pallet_id, "PAL-31")
        self.assertEqual(result.leftover[0]["id"], "PAL-32")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")
        self.assertEqual(result.labor_used_min, 6)

    def test_cutoff_leftover_when_ready_is_already_late(self) -> None:
        result = seat(
            wave(
                pallets=[pallet("LATE", door=1, ready_min=80, depart_min=60)],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "cutoff")

    def test_too_heavy_for_every_lane(self) -> None:
        result = seat(wave(pallets=[pallet("HEAVY", door=1, weight_kg=20000)]))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "too-heavy")

    def test_too_long_for_every_lane(self) -> None:
        result = seat(wave(pallets=[pallet("LONG", door=1, length_mm=20000)]))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "too-long")

    def test_pallet_cap_blocks_a_second_seat(self) -> None:
        result = seat(
            wave(
                yard={"preset": "grocery", "max_pallets": 1},
                pallets=[pallet("A", door=1), pallet("B", door=2, carrier="FDX")],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.seated_count, 1)
        self.assertEqual(result.leftover[0]["reason"], "pallet-cap")

    def test_dwell_blocks_freeze_on_a_mixed_lane(self) -> None:
        result = seat(
            Wave.from_dict(
                {
                    "yard": {
                        "preset": "parcel",
                        "max_dwell_min": 20,
                        "lanes": [
                            {
                                "id": "P1",
                                "temp": "mixed",
                                "length_mm": 3600,
                                "width_mm": 1200,
                                "max_weight_kg": 2000,
                                "max_height_mm": 1800,
                                "door": 1,
                            }
                        ],
                    },
                    "pallets": [
                        pallet(
                            "ICE",
                            temp="freeze",
                            door=1,
                            ready_min=0,
                            depart_min=90,
                        )
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "dwell")

    def test_stack_sits_on_the_same_x(self) -> None:
        result = seat(
            wave(
                allow_stack=True,
                pallets=[
                    pallet("BASE", door=1, priority=1, height_mm=700),
                    pallet("TOP", door=1, priority=2, height_mm=700),
                ],
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.pallet_id: item for item in result.seats}
        self.assertEqual(by_id["BASE"].x_mm, 0)
        self.assertEqual(by_id["TOP"].x_mm, 0)
        self.assertEqual(by_id["TOP"].stack_level, 1)
        self.assertEqual(by_id["TOP"].lane, by_id["BASE"].lane)

    def test_clear_yard_example_keeps_carriers_on_their_doors(self) -> None:
        result = seat(Wave.from_dict(json.loads((EXAMPLES / "clear-yard.json").read_text())))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.seated_count, 4)
        self._assert_legal(result)
        by_id = {item.pallet_id: item for item in result.seats}
        self.assertEqual(by_id["PAL-11"].lane, "L1")
        self.assertEqual(by_id["PAL-12"].lane, "L1")
        self.assertEqual(by_id["PAL-12"].x_mm, 1200)
        self.assertEqual(by_id["PAL-21"].lane, "L2")
        self.assertEqual(by_id["PAL-22"].lane, "L2")

    def test_cluster_groups_by_carrier(self) -> None:
        result = seat(
            wave(
                strategy="cluster",
                pallets=[
                    pallet("FDX-1", "FDX", door=2, priority=1),
                    pallet("UPS-1", "UPS", door=1, priority=2),
                ],
            )
        )
        self.assertEqual([item.pallet_id for item in result.seats], ["FDX-1", "UPS-1"])

    def test_compact_seats_the_shortest_first(self) -> None:
        result = seat(
            wave(
                strategy="compact",
                pallets=[
                    pallet("LONG", door=1, length_mm=1800, priority=1),
                    pallet("SHORT", door=1, length_mm=800, priority=2),
                ],
            )
        )
        self.assertEqual([item.pallet_id for item in result.seats], ["SHORT", "LONG"])
        by_id = {item.pallet_id: item for item in result.seats}
        self.assertEqual(by_id["SHORT"].x_mm, 0)
        self.assertEqual(by_id["LONG"].x_mm, 800)

    def _assert_legal(self, result: SeatResult) -> None:
        lookup = result.yard.lane_map()
        by_lane: dict[str, list] = {}
        for item in result.seats:
            lane = lookup[item.lane]
            self.assertGreaterEqual(item.x_mm, 0)
            self.assertLessEqual(item.x2_mm, lane.length_mm)
            self.assertLessEqual(item.height_mm, lane.max_height_mm)
            by_lane.setdefault(item.lane, []).append(item)
        for lane_id, seated in by_lane.items():
            if not result.mix_carriers:
                self.assertEqual(len({item.carrier for item in seated}), 1)
            if not result.mix_doors:
                doors = {item.door for item in seated if item.door is not None}
                self.assertLessEqual(len(doors), 1)
            floor = sorted((item for item in seated if item.stack_level == 0), key=lambda item: item.x_mm)
            for left, right in zip(floor, floor[1:]):
                self.assertLessEqual(left.x2_mm, right.x_mm, f"{lane_id} overlap")
            weight = sum(item.weight_kg for item in seated)
            self.assertLessEqual(weight, lookup[lane_id].max_weight_kg)


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_pallet_id(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict(
                {
                    "yard": {"preset": "grocery"},
                    "pallets": [pallet("A"), pallet("A", carrier="FDX")],
                }
            )

    def test_rejects_empty_wave(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict({"yard": {"preset": "grocery"}, "pallets": []})

    def test_rejects_blank_carrier(self) -> None:
        with self.assertRaises(ValueError):
            PalletSpec(
                id="X",
                carrier="",
                length_mm=1200,
                width_mm=1000,
                height_mm=1400,
                weight_kg=10,
            ).validate()


if __name__ == "__main__":
    unittest.main()
