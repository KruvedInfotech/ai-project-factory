from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yardpark.model import YardPlan
from yardpark.park import park
from yardpark.yards import get_yard


def trailer(
    tid: str,
    kind: str = "inbound",
    temp: str = "dry",
    length_ft: int = 53,
    eta: str = "08:30",
    door: str = "D1",
    dwell_h: float = 0,
    priority: int = 2,
    appointment: str = "",
    needs_power: bool = False,
) -> dict:
    return {
        "id": tid,
        "kind": kind,
        "temp": temp,
        "length_ft": length_ft,
        "eta": eta,
        "door": door,
        "dwell_h": dwell_h,
        "priority": priority,
        "appointment": appointment,
        "needs_power": needs_power,
    }


def plan(**kwargs) -> YardPlan:
    payload = {
        "yard": {"preset": "mini_6"},
        "strategy": "auto",
        "trailers": [trailer("IN-1", appointment="10:00")],
    }
    payload.update(kwargs)
    return YardPlan.from_dict(payload)


class ParkTests(unittest.TestCase):
    def test_single_trailer_takes_door_adjacent_spot(self) -> None:
        result = park(plan())
        self.assertTrue(result.all_clear)
        self.assertEqual(result.parked[0].spot_id, "Y1-1")
        self.assertEqual(result.parked[0].spot_door, "D1")

    def test_door_strategy_keeps_each_trailer_on_its_door(self) -> None:
        result = park(
            plan(
                strategy="door",
                trailers=[
                    trailer("IN-101", door="D1", appointment="09:00", priority=1),
                    trailer("OUT-220", kind="outbound", door="D2", eta="08:00", dwell_h=3, appointment="10:30", priority=1),
                ],
            )
        )
        by_id = {item.trailer_id: item for item in result.parked}
        self.assertEqual(by_id["IN-101"].spot_id, "Y1-1")
        self.assertEqual(by_id["OUT-220"].spot_id, "Y2-1")
        self.assertEqual(len(result.pulls), 2)

    def test_reefer_uses_reefer_spot_and_skips_dry(self) -> None:
        result = park(plan(trailers=[trailer("RF-1", temp="reefer", door="D3")]))
        self.assertEqual(result.parked[0].spot_id, "Y3-1")
        self.assertEqual(result.parked[0].spot_kind, "reefer")

    def test_third_reefer_is_leftover_when_spots_are_full(self) -> None:
        result = park(
            plan(
                trailers=[
                    trailer("RF-1", temp="reefer", door="D3", eta="08:10", priority=1),
                    trailer("RF-2", temp="reefer", door="D3", eta="08:20", priority=1),
                    trailer("RF-3", temp="reefer", door="D3", eta="08:30", priority=2),
                ]
            )
        )
        self.assertFalse(result.all_clear)
        self.assertEqual(result.parked_count, 2)
        self.assertEqual(result.leftover[0]["id"], "RF-3")
        self.assertEqual(result.leftover[0]["reason"], "no-spot")

    def test_dry_prefers_dry_over_reefer_or_power(self) -> None:
        result = park(plan(trailers=[trailer("DRY-1", door="")]))
        self.assertEqual(result.parked[0].spot_kind, "dry")

    def test_needs_power_rejects_dry_only_yard(self) -> None:
        result = park(
            YardPlan.from_dict(
                {
                    "yard": {
                        "name": "Dry lot",
                        "open": "08:00",
                        "close": "16:00",
                        "minutes_per_move": 8,
                        "row_change_min": 0,
                        "pull_lead_min": 20,
                        "max_moves": 4,
                        "max_labor_min": 40,
                        "spots": [
                            {
                                "id": "S1",
                                "row": "A",
                                "bay": 1,
                                "kind": "dry",
                                "door": "D1",
                                "walk_min": 4,
                            }
                        ],
                    },
                    "trailers": [trailer("HOT-1", needs_power=True)],
                }
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "no-power")

    def test_pup_spot_rejects_fifty_three(self) -> None:
        result = park(
            YardPlan.from_dict(
                {
                    "yard": {"preset": "metro_10"},
                    "trailers": [
                        trailer("VAN-1", length_ft=53, door="D1", eta="08:10", priority=1),
                        trailer("VAN-2", length_ft=53, door="D1", eta="08:20", priority=1),
                        trailer("VAN-3", length_ft=53, door="D1", eta="08:30", priority=1),
                        trailer("PUP-1", length_ft=28, door="D1", eta="08:40", priority=2),
                    ],
                }
            )
        )
        spots = {item.trailer_id: item.spot_id for item in result.parked}
        self.assertEqual(spots["PUP-1"], "A4")
        self.assertNotIn("A4", {item.spot_id for item in result.parked if item.length_ft > 28})

    def test_closed_arrival_is_leftover(self) -> None:
        result = park(plan(trailers=[trailer("LATE-1", eta="16:00")]))
        self.assertEqual(result.leftover[0]["reason"], "closed")
        self.assertEqual(result.parked_count, 0)

    def test_empty_trailer_parks_but_is_not_pulled(self) -> None:
        result = park(
            plan(
                trailers=[
                    trailer("MT-1", kind="empty", door="", appointment=""),
                    trailer("OUT-1", kind="outbound", appointment="10:00", priority=1),
                ]
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual([item.trailer_id for item in result.pulls], ["OUT-1"])
        held = {item["id"]: item["reason"] for item in result.held}
        self.assertEqual(held["MT-1"], "idle")

    def test_labor_cap_holds_later_pulls(self) -> None:
        result = park(
            plan(
                yard={"preset": "mini_6", "max_labor_min": 14},
                trailers=[
                    trailer("OUT-A", kind="outbound", door="D1", appointment="09:00", priority=1),
                    trailer("OUT-B", kind="outbound", door="D1", appointment="10:00", priority=1),
                    trailer("OUT-C", kind="outbound", door="D2", appointment="11:00", priority=2),
                    trailer("OUT-D", kind="outbound", door="D2", appointment="12:00", priority=2),
                ],
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.pull_count, 1)
        self.assertEqual(result.pulls[0].trailer_id, "OUT-A")
        self.assertGreaterEqual(sum(1 for item in result.held if item["reason"] == "capped"), 1)
        self.assertLessEqual(result.labor_min, 14)

    def test_late_pull_misses_a_tight_appointment(self) -> None:
        result = park(
            plan(
                trailers=[
                    trailer("OUT-1", kind="outbound", door="D1", eta="08:00", appointment="08:10", priority=1),
                ]
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.pull_count, 0)
        self.assertEqual(result.held[0]["reason"], "late")

    def test_dwell_strategy_parks_longest_sit_first(self) -> None:
        result = park(
            plan(
                strategy="dwell",
                trailers=[
                    trailer("NEW-1", door="D1", dwell_h=0, eta="08:10"),
                    trailer("OLD-1", door="D2", dwell_h=12, eta="08:10"),
                ],
            )
        )
        by_id = {item.trailer_id: item for item in result.parked}
        self.assertEqual(by_id["OLD-1"].spot_id, "Y2-1")
        self.assertEqual(by_id["NEW-1"].spot_id, "Y1-1")

    def test_pull_strategy_parks_outbound_before_inbound(self) -> None:
        result = park(
            plan(
                strategy="pull",
                trailers=[
                    trailer("IN-1", door="D1", appointment="12:00"),
                    trailer("OUT-1", kind="outbound", door="D1", appointment="11:00"),
                ],
            )
        )
        by_id = {item.trailer_id: item for item in result.parked}
        self.assertEqual(by_id["OUT-1"].spot_id, "Y1-1")
        self.assertEqual(by_id["IN-1"].spot_id, "Y1-2")

    def test_row_change_adds_labor(self) -> None:
        result = park(
            plan(
                trailers=[
                    trailer("OUT-A", kind="outbound", door="D1", appointment="09:00", priority=1),
                    trailer("OUT-B", kind="outbound", door="D2", appointment="10:00", priority=1),
                ]
            )
        )
        self.assertEqual(result.pull_count, 2)
        self.assertGreater(result.pulls[1].labor_min, result.pulls[0].labor_min)

    def test_inbound_wave_example_is_clear(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "inbound-wave.json"
        result = park(YardPlan.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_clear)
        self.assertEqual(result.parked_count, 7)
        self.assertEqual(result.pull_count, 6)
        spots = {item.trailer_id: item.spot_id for item in result.parked}
        self.assertEqual(spots["OUT-510"], "A1")
        self.assertEqual(spots["IN-403"], "D4")

    def test_get_yard_override_labor(self) -> None:
        yard = get_yard({"preset": "mini_6", "max_labor_min": 14})
        self.assertEqual(yard.max_labor_min, 14)
        self.assertEqual(len(yard.spots), 6)

    def test_duplicate_trailer_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan(trailers=[trailer("IN-1"), trailer("IN-1")])


if __name__ == "__main__":
    unittest.main()
