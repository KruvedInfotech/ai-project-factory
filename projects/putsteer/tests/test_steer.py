from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from putsteer.model import Wave
from putsteer.steer import steer

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def wave(**kwargs) -> Wave:
    payload = {
        "policy": {"preset": "reserve_dc"},
        "strategy": "priority",
        "inbound": [
            {
                "id": "LPN-1",
                "sku": "RICE",
                "qty": 10,
                "pallets": 1,
                "height_mm": 1200,
                "weight_kg": 200,
                "temp": "dry",
                "velocity": "A",
                "priority": 1,
                "home_aisle": 1,
            }
        ],
        "locations": [
            {
                "id": "R-A-01-1",
                "zone": "A",
                "type": "reserve",
                "aisle": 1,
                "bay": 1,
                "level": 1,
                "temp": "dry",
                "max_pallets": 2,
                "max_height_mm": 1800,
                "max_weight_kg": 1000,
            }
        ],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


class SteerTests(unittest.TestCase):
    def test_empty_slot_takes_the_first_pallet(self) -> None:
        result = steer(wave())
        self.assertTrue(result.all_clear)
        self.assertEqual(result.puts[0].location_id, "R-A-01-1")
        self.assertFalse(result.puts[0].topoff)

    def test_topoff_prefers_same_sku_over_a_closer_empty(self) -> None:
        result = steer(
            wave(
                inbound=[
                    {
                        "id": "LPN-NEW",
                        "sku": "RICE",
                        "qty": 10,
                        "height_mm": 1200,
                        "weight_kg": 200,
                        "temp": "dry",
                        "velocity": "A",
                        "priority": 1,
                        "home_aisle": 1,
                    }
                ],
                locations=[
                    {
                        "id": "R-A-01-1",
                        "zone": "A",
                        "type": "reserve",
                        "aisle": 1,
                        "bay": 1,
                        "level": 1,
                        "temp": "dry",
                        "max_pallets": 1,
                        "max_height_mm": 1800,
                        "max_weight_kg": 1000,
                    },
                    {
                        "id": "R-A-04-1",
                        "zone": "A",
                        "type": "reserve",
                        "aisle": 4,
                        "bay": 1,
                        "level": 1,
                        "temp": "dry",
                        "max_pallets": 2,
                        "max_height_mm": 1800,
                        "max_weight_kg": 1000,
                        "occupied_pallets": 1,
                        "occupied_weight_kg": 180,
                        "sku": "RICE",
                    },
                ],
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.puts[0].location_id, "R-A-04-1")
        self.assertTrue(result.puts[0].topoff)

    def test_inbound_wave_example_tops_off_rice(self) -> None:
        payload = json.loads((EXAMPLES / "inbound-wave.json").read_text())
        result = steer(Wave.from_dict(payload))
        self.assertTrue(result.all_clear)
        by_lpn = {item.pallet_id: item for item in result.puts}
        self.assertEqual(by_lpn["LPN-1001"].location_id, "R-A-01-1")
        self.assertEqual(by_lpn["LPN-1002"].location_id, "R-A-01-1")
        self.assertTrue(by_lpn["LPN-1002"].topoff)
        self.assertEqual(by_lpn["LPN-1003"].location_id, "R-B-03-1")
        self.assertEqual(by_lpn["LPN-1004"].location_id, "R-C-05-1")
        self.assertEqual(result.labor_used_min, 26)

    def test_tall_pallet_is_left_for_height(self) -> None:
        payload = json.loads((EXAMPLES / "height-cap.json").read_text())
        result = steer(Wave.from_dict(payload))
        self.assertFalse(result.all_clear)
        self.assertEqual(result.puts[0].pallet_id, "LPN-2002")
        self.assertEqual(result.leftover[0]["id"], "LPN-2001")
        self.assertEqual(result.leftover[0]["reason"], "height")

    def test_frozen_pallet_skips_cool_and_dry(self) -> None:
        payload = json.loads((EXAMPLES / "cold-mismatch.json").read_text())
        result = steer(Wave.from_dict(payload))
        self.assertEqual(result.put_count, 1)
        self.assertEqual(result.puts[0].pallet_id, "LPN-3002")
        self.assertEqual(result.leftover[0]["id"], "LPN-3001")
        self.assertEqual(result.leftover[0]["reason"], "temp")

    def test_labor_cap_stops_later_pallets(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text())
        result = steer(Wave.from_dict(payload))
        self.assertEqual(result.put_count, 2)
        self.assertEqual(result.labor_used_min, 8)
        self.assertEqual({item["reason"] for item in result.leftover}, {"labor-cap"})
        self.assertEqual(len(result.leftover), 2)

    def test_mix_sku_is_blocked_unless_policy_allows(self) -> None:
        payload = {
            "policy": {"preset": "reserve_dc"},
            "inbound": [
                {
                    "id": "LPN-X",
                    "sku": "SOAP",
                    "qty": 8,
                    "height_mm": 1000,
                    "weight_kg": 90,
                    "temp": "dry",
                    "velocity": "C",
                    "priority": 1,
                }
            ],
            "locations": [
                {
                    "id": "R-C-01-1",
                    "zone": "C",
                    "type": "reserve",
                    "aisle": 1,
                    "bay": 1,
                    "level": 1,
                    "temp": "dry",
                    "max_pallets": 2,
                    "max_height_mm": 1600,
                    "max_weight_kg": 500,
                    "occupied_pallets": 1,
                    "occupied_weight_kg": 100,
                    "sku": "PAPER",
                }
            ],
        }
        blocked = steer(Wave.from_dict(payload))
        self.assertEqual(blocked.leftover[0]["reason"], "mix-sku")
        allowed = steer(Wave.from_dict({**payload, "policy": {"preset": "bulk_floor"}}))
        self.assertTrue(allowed.all_clear)
        self.assertEqual(allowed.puts[0].location_id, "R-C-01-1")

    def test_weight_cap_leaves_a_heavy_pallet(self) -> None:
        result = steer(
            wave(
                inbound=[
                    {
                        "id": "LPN-H",
                        "sku": "STEEL",
                        "qty": 4,
                        "height_mm": 800,
                        "weight_kg": 900,
                        "temp": "dry",
                        "velocity": "A",
                        "priority": 1,
                    }
                ],
                locations=[
                    {
                        "id": "R-A-01-1",
                        "zone": "A",
                        "type": "reserve",
                        "aisle": 1,
                        "bay": 1,
                        "level": 1,
                        "temp": "dry",
                        "max_pallets": 2,
                        "max_height_mm": 1800,
                        "max_weight_kg": 400,
                    }
                ],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "weight")

    def test_blocked_location_is_skipped(self) -> None:
        result = steer(
            wave(
                locations=[
                    {
                        "id": "R-A-01-1",
                        "zone": "A",
                        "type": "reserve",
                        "aisle": 1,
                        "bay": 1,
                        "level": 1,
                        "temp": "dry",
                        "max_pallets": 1,
                        "max_height_mm": 1800,
                        "max_weight_kg": 1000,
                        "blocked": True,
                    },
                    {
                        "id": "R-A-02-1",
                        "zone": "A",
                        "type": "reserve",
                        "aisle": 2,
                        "bay": 1,
                        "level": 1,
                        "temp": "dry",
                        "max_pallets": 1,
                        "max_height_mm": 1800,
                        "max_weight_kg": 1000,
                    },
                ]
            )
        )
        self.assertEqual(result.puts[0].location_id, "R-A-02-1")

    def test_pick_policy_skips_reserve_slots(self) -> None:
        result = steer(
            wave(
                policy={"preset": "pick_fc"},
                locations=[
                    {
                        "id": "R-A-01-1",
                        "zone": "A",
                        "type": "reserve",
                        "aisle": 1,
                        "bay": 1,
                        "level": 1,
                        "temp": "dry",
                        "max_pallets": 1,
                        "max_height_mm": 1800,
                        "max_weight_kg": 1000,
                    },
                    {
                        "id": "P-A-01-1",
                        "zone": "A",
                        "type": "pick",
                        "aisle": 1,
                        "bay": 2,
                        "level": 1,
                        "temp": "dry",
                        "max_pallets": 1,
                        "max_height_mm": 1800,
                        "max_weight_kg": 1000,
                    },
                ],
            )
        )
        self.assertEqual(result.puts[0].location_id, "P-A-01-1")

    def test_heavy_strategy_puts_the_heavier_lpn_first(self) -> None:
        payload = {
            "policy": {"preset": "reserve_dc", "aisle_change_min": 0},
            "strategy": "heavy",
            "labor_minutes": 4,
            "inbound": [
                {
                    "id": "LPN-LIGHT",
                    "sku": "PAPER",
                    "qty": 10,
                    "height_mm": 800,
                    "weight_kg": 80,
                    "temp": "dry",
                    "velocity": "C",
                    "priority": 1,
                    "home_aisle": 1,
                },
                {
                    "id": "LPN-HEAVY",
                    "sku": "RICE",
                    "qty": 10,
                    "height_mm": 800,
                    "weight_kg": 400,
                    "temp": "dry",
                    "velocity": "A",
                    "priority": 2,
                    "home_aisle": 1,
                },
            ],
            "locations": [
                {
                    "id": "R-A-01-1",
                    "zone": "A",
                    "type": "reserve",
                    "aisle": 1,
                    "bay": 1,
                    "level": 1,
                    "temp": "dry",
                    "max_pallets": 1,
                    "max_height_mm": 1800,
                    "max_weight_kg": 1000,
                },
                {
                    "id": "R-C-02-1",
                    "zone": "C",
                    "type": "reserve",
                    "aisle": 2,
                    "bay": 1,
                    "level": 1,
                    "temp": "dry",
                    "max_pallets": 1,
                    "max_height_mm": 1800,
                    "max_weight_kg": 1000,
                },
            ],
        }
        result = steer(Wave.from_dict(payload))
        self.assertEqual(result.puts[0].pallet_id, "LPN-HEAVY")
        self.assertEqual(result.leftover[0]["id"], "LPN-LIGHT")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_pallet_ids(self) -> None:
        with self.assertRaises(ValueError):
            wave(
                inbound=[
                    {
                        "id": "LPN-1",
                        "sku": "A",
                        "qty": 1,
                        "height_mm": 100,
                        "weight_kg": 10,
                    },
                    {
                        "id": "LPN-1",
                        "sku": "B",
                        "qty": 1,
                        "height_mm": 100,
                        "weight_kg": 10,
                    },
                ]
            )

    def test_rejects_empty_inbound(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict(
                {
                    "policy": {"preset": "reserve_dc"},
                    "inbound": [],
                    "locations": [
                        {
                            "id": "R-A-01-1",
                            "zone": "A",
                            "type": "reserve",
                            "aisle": 1,
                            "bay": 1,
                            "level": 1,
                            "temp": "dry",
                            "max_pallets": 1,
                            "max_height_mm": 1000,
                            "max_weight_kg": 100,
                        }
                    ],
                }
            )

    def test_rejects_unknown_temp(self) -> None:
        with self.assertRaises(ValueError):
            wave(
                inbound=[
                    {
                        "id": "LPN-1",
                        "sku": "A",
                        "qty": 1,
                        "height_mm": 100,
                        "weight_kg": 10,
                        "temp": "ambient",
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
