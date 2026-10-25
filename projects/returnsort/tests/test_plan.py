from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from returnsort.model import ReturnBatch, ReturnUnit
from returnsort.plan import plan


def batch(**kwargs) -> ReturnBatch:
    payload = {
        "floor": {"preset": "dc_returns"},
        "labor_minutes": 90,
        "units": [
            {
                "ticket": "R-1",
                "sku": "TEE-BLK-M",
                "reason": "unwanted",
                "grade": "sellable",
                "velocity": "A",
                "quantity": 1,
            }
        ],
    }
    payload.update(kwargs)
    return ReturnBatch.from_dict(payload)


class GradeTests(unittest.TestCase):
    def test_sellable_unwanted_is_restock(self) -> None:
        unit = ReturnUnit("R-1", "A", "unwanted", "sellable")
        self.assertEqual(unit.disposition, "restock")

    def test_opened_sellable_returns_to_restock(self) -> None:
        unit = ReturnUnit("R-1", "A", "opened", "sellable")
        self.assertEqual(unit.disposition, "restock")

    def test_defective_is_refurb(self) -> None:
        unit = ReturnUnit("R-1", "A", "defective", "repairable")
        self.assertEqual(unit.disposition, "refurb")

    def test_crushed_is_scrap(self) -> None:
        unit = ReturnUnit("R-1", "A", "crushed", "damaged")
        self.assertEqual(unit.disposition, "scrap")

    def test_vendor_is_rma(self) -> None:
        unit = ReturnUnit("R-1", "A", "vendor", "vendor")
        self.assertEqual(unit.disposition, "rma")

    def test_recall_is_hold(self) -> None:
        unit = ReturnUnit("R-1", "A", "recall", "suspect")
        self.assertEqual(unit.disposition, "hold")


class PlanTests(unittest.TestCase):
    def test_a_velocity_prefers_pick_face(self) -> None:
        result = plan(
            batch(
                units=[
                    {
                        "ticket": "R-A",
                        "sku": "FAST",
                        "reason": "unwanted",
                        "grade": "sellable",
                        "velocity": "A",
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertTrue(result.all_parked)
        self.assertEqual(result.assignments[0].lane_id, "FACE-A")

    def test_c_velocity_prefers_reserve(self) -> None:
        result = plan(
            batch(
                units=[
                    {
                        "ticket": "R-C",
                        "sku": "SLOW",
                        "reason": "unwanted",
                        "grade": "sellable",
                        "velocity": "C",
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertEqual(result.assignments[0].lane_id, "RESERVE")

    def test_same_sku_keeps_restock_together(self) -> None:
        result = plan(
            batch(
                units=[
                    {
                        "ticket": "R-1",
                        "sku": "MUG-RED",
                        "reason": "unwanted",
                        "grade": "sellable",
                        "velocity": "A",
                        "quantity": 2,
                    },
                    {
                        "ticket": "R-2",
                        "sku": "MUG-RED",
                        "reason": "wrong-item",
                        "grade": "sellable",
                        "velocity": "A",
                        "quantity": 1,
                    },
                ]
            )
        )
        lanes = {item.lane_id for item in result.assignments}
        self.assertEqual(lanes, {"FACE-A"})

    def test_chill_unit_uses_chill_lane(self) -> None:
        result = plan(
            batch(
                units=[
                    {
                        "ticket": "R-YOG",
                        "sku": "YOG-CHILL",
                        "reason": "unwanted",
                        "grade": "sellable",
                        "temp": "chill",
                        "velocity": "A",
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertEqual(result.assignments[0].lane_id, "CHILL-1")

    def test_freeze_unit_is_left_on_dry_floor(self) -> None:
        result = plan(
            batch(
                units=[
                    {
                        "ticket": "R-ICE",
                        "sku": "ICE-PACK",
                        "reason": "unwanted",
                        "grade": "sellable",
                        "temp": "freeze",
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertFalse(result.all_parked)
        self.assertEqual(result.leftover[0]["reason"], "no matching lane")

    def test_labor_cap_blocks_later_units(self) -> None:
        result = plan(
            batch(
                labor_minutes=4,
                units=[
                    {
                        "ticket": "R-1",
                        "sku": "TEE",
                        "reason": "unwanted",
                        "grade": "sellable",
                        "velocity": "A",
                        "quantity": 1,
                    },
                    {
                        "ticket": "R-2",
                        "sku": "HOOD",
                        "reason": "defective",
                        "grade": "repairable",
                        "quantity": 1,
                    },
                ],
            )
        )
        self.assertEqual(result.assigned_count, 1)
        self.assertEqual(result.leftover[0]["ticket"], "R-2")
        self.assertEqual(result.leftover[0]["reason"], "labor cap")

    def test_lane_capacity_leaves_overflow(self) -> None:
        result = plan(
            ReturnBatch.from_dict(
                {
                    "floor": {
                        "name": "Tiny hold",
                        "lanes": [
                            {
                                "id": "HOLD",
                                "dispositions": ["hold"],
                                "temp": "dry",
                                "slots": 1,
                                "zone": "quarantine",
                                "col": 0,
                                "row": 0,
                            }
                        ],
                    },
                    "labor_minutes": 20,
                    "units": [
                        {
                            "ticket": "R-H",
                            "sku": "KIT",
                            "reason": "recall",
                            "grade": "suspect",
                            "quantity": 2,
                        }
                    ],
                }
            )
        )
        self.assertEqual(result.assigned_count, 1)
        self.assertEqual(result.leftover[0]["reason"], "lanes full")

    def test_rma_prefers_door_adjacent_lane(self) -> None:
        result = plan(
            batch(
                units=[
                    {
                        "ticket": "R-V",
                        "sku": "BOOT-10",
                        "reason": "rma",
                        "grade": "vendor",
                        "quantity": 1,
                    }
                ]
            )
        )
        self.assertEqual(result.assignments[0].lane_id, "RMA")

    def test_mixed_example_parks_everything(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mixed-returns.json"
        result = plan(ReturnBatch.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_parked)
        self.assertEqual(result.assigned_count, 16)
        self._assert_legal(result)

    def test_quality_example_splits_hold_and_rma(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "quality-holds.json"
        result = plan(ReturnBatch.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_parked)
        by_lane: dict[str, list[str]] = {}
        for item in result.assignments:
            by_lane.setdefault(item.lane_id, []).append(item.ticket)
        self.assertIn("R-2001", by_lane["HOLD"])
        self.assertIn("R-2003", by_lane["RMA"])
        self.assertIn("R-2005", by_lane["CHILL-1"])

    def _assert_legal(self, result) -> None:
        used: dict[str, int] = {}
        for item in result.assignments:
            lane = result.floor.lane(item.lane_id)
            self.assertIn(item.disposition, lane.dispositions)
            self.assertEqual(item.temp, lane.temp)
            used[item.lane_id] = used.get(item.lane_id, 0) + 1
            self.assertLess(item.slot, lane.slots)
        for lane_id, count in used.items():
            self.assertLessEqual(count, result.floor.lane(lane_id).slots)
        self.assertLessEqual(result.labor_used, result.labor_cap)


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_tickets(self) -> None:
        with self.assertRaises(ValueError):
            ReturnBatch.from_dict(
                {
                    "floor": {"preset": "dc_returns"},
                    "units": [
                        {"ticket": "R-1", "sku": "A", "reason": "unwanted", "grade": "sellable"},
                        {"ticket": "R-1", "sku": "B", "reason": "unwanted", "grade": "sellable"},
                    ],
                }
            )

    def test_rejects_empty_batch(self) -> None:
        with self.assertRaises(ValueError):
            ReturnBatch.from_dict({"floor": {"preset": "dc_returns"}, "units": []})

    def test_expand_respects_quantity(self) -> None:
        ship = batch(
            units=[
                {
                    "ticket": "R-1",
                    "sku": "A",
                    "reason": "unwanted",
                    "grade": "sellable",
                    "quantity": 4,
                }
            ]
        )
        self.assertEqual(len(ship.expand()), 4)


if __name__ == "__main__":
    unittest.main()
