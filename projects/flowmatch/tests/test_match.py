from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flowmatch.match import match
from flowmatch.model import FlowPlan
from flowmatch.yards import get_yard


def receipt(
    rid: str,
    sku: str,
    pallets: int = 2,
    eta: str = "08:30",
    door: str = "D1",
    temp: str = "dry",
) -> dict:
    return {"id": rid, "sku": sku, "pallets": pallets, "eta": eta, "door": door, "temp": temp}


def order(
    oid: str,
    sku: str,
    pallets: int = 2,
    cutoff: str = "12:00",
    door: str = "D1",
    temp: str = "dry",
    priority: int = 2,
) -> dict:
    return {
        "id": oid,
        "sku": sku,
        "pallets": pallets,
        "cutoff": cutoff,
        "door": door,
        "temp": temp,
        "priority": priority,
    }


def plan(**kwargs) -> FlowPlan:
    payload = {
        "yard": {"preset": "mini_3"},
        "strategy": "auto",
        "receipts": [receipt("IN-1", "SKU-A")],
        "orders": [order("OUT-1", "SKU-A")],
    }
    payload.update(kwargs)
    return FlowPlan.from_dict(payload)


class MatchTests(unittest.TestCase):
    def test_same_door_auto_is_live(self) -> None:
        result = match(plan())
        self.assertTrue(result.all_clear)
        self.assertEqual(result.allocations[0].mode, "live")
        self.assertIsNone(result.allocations[0].lane_id)
        self.assertEqual(result.live_pallets, 2)
        self.assertEqual(result.matched_pallets, 2)

    def test_different_door_auto_is_stage(self) -> None:
        result = match(
            plan(
                receipts=[receipt("IN-1", "SKU-A", door="D1")],
                orders=[order("OUT-1", "SKU-A", door="D2")],
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.allocations[0].mode, "stage")
        self.assertEqual(result.allocations[0].lane_id, "L2")
        self.assertEqual(result.lane_fill["L2"], 2)

    def test_live_strategy_unloads_across_doors(self) -> None:
        result = match(
            plan(
                strategy="live",
                receipts=[receipt("IN-1", "SKU-A", door="D1")],
                orders=[order("OUT-1", "SKU-A", door="D2")],
            )
        )
        self.assertEqual(result.allocations[0].mode, "live")
        self.assertEqual(result.stage_pallets, 0)

    def test_lane_strategy_stages_even_same_door(self) -> None:
        result = match(
            plan(
                strategy="lane",
                receipts=[receipt("IN-1", "SKU-A", door="D1")],
                orders=[order("OUT-1", "SKU-A", door="D1")],
            )
        )
        self.assertEqual(result.allocations[0].mode, "stage")
        self.assertEqual(result.allocations[0].lane_id, "L1")

    def test_temp_mismatch_is_leftover(self) -> None:
        result = match(
            plan(
                receipts=[receipt("IN-DRY", "SKU-A", temp="dry")],
                orders=[order("OUT-COLD", "SKU-A", door="C1", temp="reefer")],
            )
        )
        self.assertFalse(result.all_clear)
        self.assertEqual(result.leftover_out[0]["reason"], "temp")
        self.assertEqual(result.leftover_in[0]["reason"], "no-demand")

    def test_late_inbound_is_leftover(self) -> None:
        result = match(
            plan(
                receipts=[receipt("IN-LATE", "SKU-B", eta="15:30", door="C1", temp="reefer")],
                orders=[order("OUT-EARLY", "SKU-B", cutoff="12:00", door="C1", temp="reefer")],
            )
        )
        self.assertEqual(result.leftover_out[0]["reason"], "late")
        self.assertEqual(result.leftover_in[0]["reason"], "late")

    def test_short_sku_is_leftover(self) -> None:
        result = match(
            plan(
                receipts=[receipt("IN-1", "SKU-A")],
                orders=[order("OUT-1", "SKU-Z")],
            )
        )
        self.assertEqual(result.leftover_out[0]["reason"], "short")
        self.assertEqual(result.leftover_in[0]["reason"], "no-demand")

    def test_no_lane_when_dry_lanes_are_full(self) -> None:
        result = match(
            plan(
                strategy="lane",
                yard={"preset": "mini_3", "max_matches": 8, "max_labor_min": 80},
                receipts=[
                    receipt("IN-1", "SKU-A", pallets=2, door="D1"),
                    receipt("IN-2", "SKU-B", pallets=2, door="D1"),
                    receipt("IN-3", "SKU-C", pallets=2, door="D1"),
                ],
                orders=[
                    order("OUT-1", "SKU-A", pallets=2, door="D1"),
                    order("OUT-2", "SKU-B", pallets=2, door="D2"),
                    order("OUT-3", "SKU-C", pallets=2, door="D1"),
                ],
            )
        )
        self.assertTrue(any(item["reason"] == "no-lane" for item in result.leftover_out))
        self.assertEqual(sum(result.lane_fill[key] for key in ("L1", "L2")), 4)

    def test_fifo_uses_earlier_receipt_first(self) -> None:
        result = match(
            plan(
                receipts=[
                    receipt("IN-LATE", "SKU-A", eta="09:30"),
                    receipt("IN-EARLY", "SKU-A", eta="08:10"),
                ],
                orders=[order("OUT-1", "SKU-A", pallets=2)],
            )
        )
        self.assertEqual(result.allocations[0].receipt_id, "IN-EARLY")
        self.assertEqual(result.leftover_in[0]["id"], "IN-LATE")

    def test_partial_split_across_orders(self) -> None:
        result = match(
            plan(
                receipts=[receipt("IN-1", "SKU-A", pallets=5)],
                orders=[
                    order("OUT-A", "SKU-A", pallets=3, priority=1),
                    order("OUT-B", "SKU-A", pallets=2, cutoff="13:00"),
                ],
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(len(result.allocations), 2)
        self.assertEqual(result.matched_pallets, 5)

    def test_labor_cap_marks_leftover(self) -> None:
        result = match(
            plan(
                yard={
                    "preset": "mini_3",
                    "max_labor_min": 14,
                    "minutes_per_match": 6,
                    "lane_change_min": 3,
                },
                strategy="lane",
                receipts=[
                    receipt("IN-A", "SKU-A", door="D1"),
                    receipt("IN-B", "SKU-B", door="D2"),
                    receipt("IN-C", "SKU-C", door="D1"),
                ],
                orders=[
                    order("OUT-A", "SKU-A", door="D2", priority=1),
                    order("OUT-B", "SKU-B", door="D1", cutoff="12:30"),
                    order("OUT-C", "SKU-C", door="D2", cutoff="13:00"),
                ],
            )
        )
        self.assertGreaterEqual(len(result.allocations), 1)
        self.assertTrue(any(item["reason"] == "capped" for item in result.leftover_out))
        self.assertLessEqual(result.labor_min, 14)
        self.assertFalse(result.all_clear)

    def test_match_cap_stops_after_one(self) -> None:
        result = match(
            plan(
                yard={"preset": "mini_3", "max_matches": 1, "max_labor_min": 80},
                receipts=[receipt("IN-A", "SKU-A"), receipt("IN-B", "SKU-B")],
                orders=[order("OUT-A", "SKU-A", priority=1), order("OUT-B", "SKU-B")],
            )
        )
        self.assertEqual(len(result.allocations), 1)
        self.assertTrue(any(item["reason"] == "capped" for item in result.leftover_out))

    def test_custom_yard(self) -> None:
        result = match(
            FlowPlan.from_dict(
                {
                    "yard": {
                        "name": "Tiny",
                        "open": "07:00",
                        "close": "15:00",
                        "live_min": 20,
                        "unload_min": 10,
                        "load_min": 10,
                        "stage_min": 8,
                        "minutes_per_match": 5,
                        "lane_change_min": 2,
                        "max_matches": 4,
                        "max_labor_min": 30,
                        "lanes": [{"id": "X1", "temp": "dry", "max_pallets": 4, "door": "X", "row": 1}],
                    },
                    "receipts": [receipt("IN-1", "USB", door="X")],
                    "orders": [order("OUT-1", "USB", door="X")],
                }
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.yard.id, "custom")
        self.assertEqual(result.yard.name, "Tiny")

    def test_duplicate_receipt_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan(receipts=[receipt("IN-1", "A"), receipt("IN-1", "B")])

    def test_duplicate_order_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan(orders=[order("OUT-1", "A"), order("OUT-1", "B")])

    def test_unknown_preset_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            get_yard({"preset": "nope"})

    def test_example_grocery_clears(self) -> None:
        path = Path(__file__).resolve().parents[1] / "examples" / "grocery-same-day.json"
        result = match(FlowPlan.from_dict(json.loads(path.read_text())))
        self.assertTrue(result.all_clear)
        self.assertGreater(result.live_pallets, 0)
        self.assertGreater(result.stage_pallets, 0)
        milk_live = next(
            item
            for item in result.allocations
            if item.order_id == "OUT-A1" and item.sku == "MILK-1L"
        )
        self.assertEqual(milk_live.mode, "live")
        milk_stage = next(item for item in result.allocations if item.order_id == "OUT-A3")
        self.assertEqual(milk_stage.mode, "stage")

    def test_example_reefer_short(self) -> None:
        path = Path(__file__).resolve().parents[1] / "examples" / "reefer-short.json"
        result = match(FlowPlan.from_dict(json.loads(path.read_text())))
        reasons = {item["reason"] for item in result.leftover_out}
        self.assertIn("temp", reasons)
        self.assertIn("late", reasons)
        self.assertFalse(result.all_clear)

    def test_cutoff_prefers_priority_one(self) -> None:
        result = match(
            plan(
                strategy="cutoff",
                yard={"preset": "mini_3", "max_matches": 1, "max_labor_min": 80},
                receipts=[receipt("IN-A", "SKU-A"), receipt("IN-B", "SKU-B")],
                orders=[
                    order("OUT-LATE", "SKU-B", cutoff="15:00"),
                    order("OUT-HOT", "SKU-A", cutoff="14:00", priority=1),
                ],
            )
        )
        self.assertEqual(result.allocations[0].order_id, "OUT-HOT")


class ModelTests(unittest.TestCase):
    def test_eta_before_open_is_available_at_open(self) -> None:
        result = match(
            plan(
                receipts=[receipt("IN-NIGHT", "SKU-A", eta="03:00")],
                orders=[order("OUT-1", "SKU-A", cutoff="10:00")],
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.allocations[0].ready, "08:30")
