from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recvbay.docks import duration_min
from recvbay.model import Board, LoadSpec
from recvbay.plan import PlanResult, plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(load_id: str, vendor: str = "NESTLE", **kwargs) -> dict:
    row = {
        "id": load_id,
        "vendor": vendor,
        "priority": 2,
        "temp": "dry",
        "pallets": 8,
        "unload": "live",
        "floor_loaded": False,
        "eta_min": 0,
        "appointment_min": 120,
    }
    row.update(kwargs)
    return row


def board(**kwargs) -> Board:
    payload = {
        "dock": {"preset": "grocery"},
        "strategy": "auto",
        "loads": [load("ASN-1", door=1)],
    }
    payload.update(kwargs)
    return Board.from_dict(payload)


class PlanTests(unittest.TestCase):
    def test_single_load_sits_at_the_booked_door(self) -> None:
        result = plan(board())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.docked_count, 1)
        placed = result.slots[0]
        self.assertEqual(placed.load_id, "ASN-1")
        self.assertEqual(placed.door, "D1")
        self.assertEqual(placed.start_min, 0)
        self.assertEqual(placed.end_min, 64)

    def test_same_door_sequences_after_the_first_unload(self) -> None:
        result = plan(
            board(
                loads=[
                    load("ASN-11", door=1, priority=1, pallets=8, eta_min=0),
                    load("ASN-12", door=1, priority=2, pallets=6, eta_min=60, appointment_min=90),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.load_id: item for item in result.slots}
        self.assertEqual(by_id["ASN-11"].door, "D1")
        self.assertEqual(by_id["ASN-12"].door, "D1")
        self.assertEqual(by_id["ASN-11"].end_min, 64)
        self.assertEqual(by_id["ASN-12"].start_min, 64)
        self.assertEqual(by_id["ASN-12"].end_min, 112)

    def test_second_vendor_opens_a_new_door(self) -> None:
        result = plan(
            board(
                loads=[
                    load("ASN-11", "NESTLE", door=1, priority=1),
                    load("ASN-21", "PEPSICO", door=2, priority=2),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.load_id: item for item in result.slots}
        self.assertEqual(by_id["ASN-11"].door, "D1")
        self.assertEqual(by_id["ASN-21"].door, "D2")

    def test_vendor_mix_leftover_when_the_only_door_is_claimed(self) -> None:
        result = plan(
            Board.from_dict(
                {
                    "dock": {
                        "preset": "parcel",
                        "doors": [
                            {
                                "id": "P1",
                                "number": 1,
                                "temp": "mixed",
                                "has_leveler": True,
                                "has_reefer": False,
                                "staging_pallets": 8,
                                "height_mm": 4500,
                            }
                        ],
                    },
                    "mix_vendors": False,
                    "loads": [
                        load("ASN-11", "NESTLE", door=1, priority=1, pallets=2),
                        load("ASN-21", "PEPSICO", door=1, priority=2, pallets=2),
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.slots[0].load_id, "ASN-11")
        self.assertEqual(result.leftover[0]["id"], "ASN-21")
        self.assertEqual(result.leftover[0]["reason"], "vendor-mix")

    def test_mix_vendors_shares_the_door(self) -> None:
        result = plan(
            Board.from_dict(
                {
                    "dock": {
                        "doors": [
                            {
                                "id": "P1",
                                "number": 1,
                                "temp": "dry",
                                "has_leveler": True,
                                "has_reefer": False,
                                "staging_pallets": 8,
                                "height_mm": 4500,
                            }
                        ],
                        "minutes_per_pallet": 4,
                        "max_labor_min": 80,
                        "shift_end_min": 240,
                        "max_wait_min": 60,
                    },
                    "mix_vendors": True,
                    "loads": [
                        load("ASN-11", "NESTLE", door=1, priority=1, pallets=2, appointment_min=90),
                        load("ASN-21", "PEPSICO", door=1, priority=2, pallets=2, eta_min=8, appointment_min=90),
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual({item.door for item in result.slots}, {"P1"})

    def test_door_mismatch_is_left_behind(self) -> None:
        result = plan(
            Board.from_dict(
                {
                    "dock": {
                        "doors": [
                            {
                                "id": "D1",
                                "number": 1,
                                "temp": "dry",
                                "has_leveler": True,
                                "has_reefer": False,
                                "staging_pallets": 24,
                                "height_mm": 4500,
                            }
                        ]
                    },
                    "mix_doors": False,
                    "loads": [load("LATE", door=9)],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "door")

    def test_floor_block_example_leaves_floor_loaded(self) -> None:
        result = plan(Board.from_dict(json.loads((EXAMPLES / "floor-block.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.docked_count, 1)
        self.assertEqual(result.slots[0].load_id, "ASN-40")
        self.assertEqual(result.leftover[0]["id"], "ASN-41")
        self.assertEqual(result.leftover[0]["reason"], "equipment")

    def test_dwell_block_example_leaves_the_short_appointment(self) -> None:
        result = plan(Board.from_dict(json.loads((EXAMPLES / "dwell-block.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.slots[0].load_id, "ASN-61")
        self.assertEqual(result.leftover[0]["id"], "ASN-60")
        self.assertEqual(result.leftover[0]["reason"], "dwell")

    def test_labor_cap_blocks_the_second_load(self) -> None:
        result = plan(Board.from_dict(json.loads((EXAMPLES / "labor-capped.json").read_text())))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.docked_count, 1)
        self.assertEqual(result.slots[0].load_id, "ASN-51")
        self.assertEqual(result.leftover[0]["id"], "ASN-52")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")
        self.assertEqual(result.labor_used_min, 64)

    def test_live_wait_leftover_when_the_door_is_still_busy(self) -> None:
        result = plan(
            board(
                loads=[
                    load("ASN-11", door=1, priority=1, pallets=8, eta_min=0),
                    load("ASN-12", door=1, priority=2, pallets=6, eta_min=0, appointment_min=180),
                ]
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["id"], "ASN-12")
        self.assertEqual(result.leftover[0]["reason"], "wait")

    def test_drop_can_wait_for_the_same_door(self) -> None:
        result = plan(
            board(
                loads=[
                    load("ASN-11", door=1, priority=1, pallets=8, eta_min=0),
                    load(
                        "ASN-12",
                        door=1,
                        priority=2,
                        pallets=6,
                        eta_min=0,
                        unload="drop",
                        appointment_min=None,
                    ),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.load_id: item for item in result.slots}
        self.assertEqual(by_id["ASN-12"].start_min, 64)
        self.assertEqual(by_id["ASN-12"].unload, "drop")

    def test_chill_stays_off_a_dry_door(self) -> None:
        result = plan(
            Board.from_dict(
                {
                    "dock": {"preset": "dc"},
                    "loads": [load("COLD", temp="chill", door=11, pallets=4)],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "temp")

    def test_too_late_after_shift_end(self) -> None:
        result = plan(board(loads=[load("LATE", door=1, eta_min=480)]))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "too-late")

    def test_too_tall_for_every_door(self) -> None:
        result = plan(
            Board.from_dict(
                {
                    "dock": {
                        "doors": [
                            {
                                "id": "D1",
                                "number": 1,
                                "temp": "dry",
                                "has_leveler": True,
                                "has_reefer": False,
                                "staging_pallets": 24,
                                "height_mm": 3000,
                            }
                        ]
                    },
                    "loads": [load("TALL", door=1, trailer_height_mm=4000)],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "too-tall")

    def test_staging_leftover_when_the_pad_is_too_small(self) -> None:
        result = plan(board(loads=[load("HUGE", door=1, pallets=40)]))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "staging")

    def test_door_busy_when_unload_runs_past_shift_end(self) -> None:
        result = plan(
            board(
                dock={"preset": "grocery", "shift_end_min": 50},
                loads=[load("LONG", door=1, pallets=8, appointment_min=200)],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "door-busy")

    def test_floor_loaded_uses_one_and_a_half_labor(self) -> None:
        self.assertEqual(duration_min(8, 8, False), 64)
        self.assertEqual(duration_min(8, 8, True), 96)
        result = plan(
            board(
                loads=[load("FLOOR", door=1, pallets=8, floor_loaded=True, appointment_min=200)],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.slots[0].labor_min, 96)
        self.assertEqual(result.slots[0].end_min, 96)

    def test_chill_live_needs_a_reefer_plug(self) -> None:
        result = plan(
            Board.from_dict(
                {
                    "dock": {
                        "doors": [
                            {
                                "id": "D1",
                                "number": 1,
                                "temp": "chill",
                                "has_leveler": True,
                                "has_reefer": False,
                                "staging_pallets": 16,
                                "height_mm": 4500,
                            }
                        ]
                    },
                    "loads": [load("ICE", temp="chill", door=1, pallets=2)],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["reason"], "equipment")

    def test_clear_dock_example_keeps_vendors_on_their_doors(self) -> None:
        result = plan(Board.from_dict(json.loads((EXAMPLES / "clear-dock.json").read_text())))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.docked_count, 4)
        self._assert_legal(result)
        by_id = {item.load_id: item for item in result.slots}
        self.assertEqual(by_id["ASN-11"].door, "D1")
        self.assertEqual(by_id["ASN-12"].door, "D1")
        self.assertEqual(by_id["ASN-12"].start_min, 64)
        self.assertEqual(by_id["ASN-21"].door, "D2")
        self.assertEqual(by_id["ASN-31"].door, "D5")
        self.assertEqual(result.labor_used_min, 208)

    def test_cluster_groups_by_vendor(self) -> None:
        result = plan(
            board(
                strategy="cluster",
                loads=[
                    load("ASN-21", "PEPSICO", door=2, priority=1),
                    load("ASN-11", "NESTLE", door=1, priority=2),
                ],
            )
        )
        self.assertEqual([item.load_id for item in result.slots], ["ASN-11", "ASN-21"])

    def test_compact_docks_the_shortest_first(self) -> None:
        result = plan(
            board(
                strategy="compact",
                mix_doors=True,
                loads=[
                    load("LONG", door=1, pallets=8, priority=1),
                    load("SHORT", door=1, pallets=2, priority=2),
                ],
            )
        )
        self.assertEqual([item.load_id for item in result.slots], ["SHORT", "LONG"])
        by_id = {item.load_id: item for item in result.slots}
        self.assertEqual(by_id["SHORT"].start_min, 0)
        self.assertEqual(by_id["LONG"].start_min, 16)

    def test_eta_walks_the_clock(self) -> None:
        result = plan(
            board(
                strategy="eta",
                loads=[
                    load("LATE", door=2, eta_min=30, priority=1, pallets=4),
                    load("EARLY", door=1, eta_min=0, priority=2, pallets=4),
                ],
            )
        )
        self.assertEqual([item.load_id for item in result.slots], ["EARLY", "LATE"])

    def test_mix_doors_can_leave_the_booked_bay(self) -> None:
        result = plan(
            Board.from_dict(
                {
                    "dock": {
                        "doors": [
                            {
                                "id": "D1",
                                "number": 1,
                                "temp": "dry",
                                "has_leveler": True,
                                "has_reefer": False,
                                "staging_pallets": 24,
                                "height_mm": 4500,
                            }
                        ]
                    },
                    "mix_doors": True,
                    "loads": [load("MOVED", door=9, pallets=4)],
                }
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.slots[0].door, "D1")

    def _assert_legal(self, result: PlanResult) -> None:
        lookup = result.dock.door_map()
        by_door: dict[str, list] = {}
        for item in result.slots:
            door = lookup[item.door]
            self.assertGreaterEqual(item.start_min, 0)
            self.assertLessEqual(item.end_min, result.dock.shift_end_min)
            self.assertEqual(item.door_number, door.number)
            if not result.mix_doors:
                pass
            by_door.setdefault(item.door, []).append(item)
        for door_id, seated in by_door.items():
            ordered = sorted(seated, key=lambda item: item.start_min)
            for left, right in zip(ordered, ordered[1:]):
                self.assertLessEqual(left.end_min, right.start_min, f"{door_id} overlap")
            if not result.mix_vendors:
                self.assertEqual(len({item.vendor for item in seated}), 1)
        self.assertLessEqual(result.labor_used_min, result.labor_cap_min)


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_load_id(self) -> None:
        with self.assertRaises(ValueError):
            Board.from_dict(
                {
                    "dock": {"preset": "grocery"},
                    "loads": [load("A"), load("A", vendor="PEPSICO")],
                }
            )

    def test_rejects_empty_board(self) -> None:
        with self.assertRaises(ValueError):
            Board.from_dict({"dock": {"preset": "grocery"}, "loads": []})

    def test_rejects_blank_vendor(self) -> None:
        with self.assertRaises(ValueError):
            LoadSpec(id="X", vendor="", pallets=1).validate()

    def test_rejects_unknown_unload(self) -> None:
        with self.assertRaises(ValueError):
            Board.from_dict(
                {
                    "dock": {"preset": "grocery"},
                    "loads": [load("A", unload="fork")],
                }
            )


if __name__ == "__main__":
    unittest.main()
