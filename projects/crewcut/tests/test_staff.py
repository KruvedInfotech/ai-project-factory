from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crewcut.model import Board
from crewcut.sites import hour_in_span, hour_range
from crewcut.staff import consecutive_before, staff

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def person(ident: str, **kwargs) -> dict:
    row = {
        "id": ident,
        "name": ident,
        "kind": "regular",
        "skills": ["pick"],
        "rate_per_hour": 18,
        "available_start": 8,
        "available_end": 14,
        "ot_cap_hours": 0,
        "temp": "dry",
    }
    row.update(kwargs)
    return row


def slot(hour: int, skill: str = "pick", heads: int = 1, **kwargs) -> dict:
    row = {"hour": hour, "skill": skill, "heads": heads, "temp": "dry", "priority": 2}
    row.update(kwargs)
    return row


def board(**kwargs) -> Board:
    payload = {
        "site": {"preset": "grocery"},
        "strategy": "auto",
        "demand": [slot(8)],
        "crew": [person("A-12", name="Rivera")],
    }
    payload.update(kwargs)
    return Board.from_dict(payload)


class HourSpanTests(unittest.TestCase):
    def test_day_shift_is_half_open(self) -> None:
        self.assertEqual(hour_range(6, 14), list(range(6, 14)))
        self.assertTrue(hour_in_span(6, 6, 14))
        self.assertTrue(hour_in_span(13, 6, 14))
        self.assertFalse(hour_in_span(14, 6, 14))

    def test_overnight_wraps_midnight(self) -> None:
        self.assertEqual(hour_range(22, 6), [22, 23, 0, 1, 2, 3, 4, 5])
        self.assertTrue(hour_in_span(23, 22, 6))
        self.assertTrue(hour_in_span(0, 22, 6))
        self.assertFalse(hour_in_span(6, 22, 6))
        self.assertFalse(hour_in_span(21, 22, 6))

    def test_consecutive_hours_wrap_midnight(self) -> None:
        self.assertEqual(consecutive_before({22, 23}, 0), 2)
        self.assertEqual(consecutive_before({8, 9, 10, 11}, 12), 4)
        self.assertEqual(consecutive_before({8, 9, 11}, 12), 1)


class PlanTests(unittest.TestCase):
    def test_single_picker_sits_the_opening_hour(self) -> None:
        result = staff(board())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.seated_count, 1)
        seat = result.seats[0]
        self.assertEqual(seat.associate_id, "A-12")
        self.assertEqual(seat.hour, 8)
        self.assertEqual(seat.skill, "pick")
        self.assertFalse(seat.ot)
        self.assertEqual(seat.cost, 18)

    def test_two_heads_open_a_second_picker(self) -> None:
        result = staff(
            board(
                demand=[slot(8, heads=2)],
                crew=[person("A-12", name="Rivera"), person("A-15", name="Chen")],
            )
        )
        self.assertTrue(result.all_fit)
        seated = sorted(seat.associate_id for seat in result.seats)
        self.assertEqual(seated, ["A-12", "A-15"])

    def test_continuity_keeps_the_same_picker_across_hours(self) -> None:
        result = staff(
            board(
                demand=[slot(8), slot(9)],
                crew=[person("A-12", name="Rivera"), person("A-15", name="Chen")],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual({seat.associate_id for seat in result.seats}, {"A-12"})
        self.assertEqual(sorted(seat.hour for seat in result.seats), [8, 9])

    def test_auto_uses_an_in_window_temp_instead_of_regular_ot(self) -> None:
        payload = {
            "site": {"preset": "grocery"},
            "strategy": "auto",
            "demand": [slot(8, priority=1), slot(9, priority=1), slot(10, priority=1), slot(11, priority=1)],
            "crew": [
                person("A-12", name="Rivera", available_start=8, available_end=11, ot_cap_hours=2),
                person("T-3", name="Temp-3", kind="temp", rate_per_hour=22, available_start=8, available_end=12),
            ],
        }
        auto = staff(Board.from_dict(payload))
        overtime = staff(Board.from_dict({**payload, "strategy": "overtime"}))
        self.assertTrue(auto.all_fit)
        self.assertTrue(overtime.all_fit)
        auto_11 = next(seat for seat in auto.seats if seat.hour == 11)
        ot_11 = next(seat for seat in overtime.seats if seat.hour == 11)
        self.assertEqual(auto_11.associate_id, "T-3")
        self.assertFalse(auto_11.ot)
        self.assertEqual(ot_11.associate_id, "A-12")
        self.assertTrue(ot_11.ot)
        self.assertEqual(ot_11.cost, 27)

    def test_temp_strategy_prefers_the_temp(self) -> None:
        result = staff(
            board(
                strategy="temp",
                demand=[slot(8)],
                crew=[
                    person("A-12", name="Rivera"),
                    person("T-3", name="Temp-3", kind="temp", rate_per_hour=22),
                ],
            )
        )
        self.assertEqual(result.seats[0].associate_id, "T-3")

    def test_regular_strategy_prefers_the_regular(self) -> None:
        result = staff(
            board(
                strategy="regular",
                demand=[slot(8)],
                crew=[
                    person("T-3", name="Temp-3", kind="temp", rate_per_hour=16),
                    person("A-12", name="Rivera"),
                ],
            )
        )
        self.assertEqual(result.seats[0].associate_id, "A-12")

    def test_freeze_demand_leaves_a_dry_picker(self) -> None:
        result = staff(
            board(
                demand=[slot(8, temp="freeze")],
                crew=[person("A-12", name="Rivera", temp="dry")],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "temp")
        self.assertEqual(result.seated_count, 0)

    def test_mixed_temp_can_sit_freeze(self) -> None:
        result = staff(
            board(
                demand=[slot(8, temp="freeze")],
                crew=[person("A-12", name="Rivera", temp="mixed")],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.seats[0].temp, "freeze")

    def test_reach_demand_leaves_a_jack_cert(self) -> None:
        result = staff(
            board(
                demand=[slot(8, skill="forklift", equipment="reach")],
                crew=[person("JK-1", name="Ibarra", skills=["forklift"], certs=["jack"])],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "cert")

    def test_pack_demand_leaves_a_picker(self) -> None:
        result = staff(board(demand=[slot(8, skill="pack")]))
        self.assertEqual(result.leftover[0]["reason"], "skill")

    def test_labor_cap_leaves_the_second_hour(self) -> None:
        result = staff(board(labor_dollars=18, demand=[slot(8, priority=1), slot(9, priority=2)]))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.seated_count, 1)
        self.assertEqual(result.seats[0].hour, 8)
        self.assertEqual(result.leftover[0]["hour"], 9)
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")

    def test_head_cap_blocks_a_second_punch(self) -> None:
        result = staff(
            board(
                head_cap=1,
                demand=[slot(8, heads=2)],
                crew=[person("A-12", name="Rivera"), person("A-15", name="Chen")],
            )
        )
        self.assertEqual(result.punched_count, 1)
        self.assertEqual(result.leftover[0]["reason"], "head-cap")
        self.assertEqual(result.leftover[0]["heads"], 1)

    def test_window_when_hour_is_outside_availability(self) -> None:
        result = staff(board(demand=[slot(5)]))
        self.assertEqual(result.leftover[0]["reason"], "window")

    def test_ot_cap_after_the_allowed_overtime_hours(self) -> None:
        result = staff(
            board(
                demand=[slot(8, priority=1), slot(9, priority=1), slot(10, priority=1), slot(11, priority=1)],
                crew=[person("A-12", name="Rivera", available_start=8, available_end=10, ot_cap_hours=1)],
            )
        )
        self.assertEqual(result.seated_count, 3)
        self.assertTrue(next(seat for seat in result.seats if seat.hour == 10).ot)
        self.assertEqual(result.leftover[0]["hour"], 11)
        self.assertEqual(result.leftover[0]["reason"], "ot-cap")

    def test_break_after_four_consecutive_hours(self) -> None:
        result = staff(
            board(
                demand=[slot(h, priority=1) for h in (8, 9, 10, 11, 12)],
                crew=[person("A-12", name="Rivera")],
            )
        )
        self.assertEqual(sorted(seat.hour for seat in result.seats), [8, 9, 10, 11])
        self.assertEqual(result.leftover[0]["hour"], 12)
        self.assertEqual(result.leftover[0]["reason"], "break")

    def test_break_clears_and_they_can_work_the_hour_after(self) -> None:
        result = staff(
            board(
                demand=[slot(h, priority=1) for h in (8, 9, 10, 11, 13)],
                crew=[person("A-12", name="Rivera")],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(sorted(seat.hour for seat in result.seats), [8, 9, 10, 11, 13])

    def test_overnight_picker_covers_hour_zero(self) -> None:
        result = staff(
            Board.from_dict(
                {
                    "site": {"preset": "produce"},
                    "demand": [slot(23, temp="chill", priority=1), slot(0, temp="chill", priority=1)],
                    "crew": [
                        person(
                            "C-1",
                            name="Ng",
                            available_start=22,
                            available_end=6,
                            temp="chill",
                            rate_per_hour=20,
                        )
                    ],
                }
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(sorted(seat.hour for seat in result.seats), [0, 23])

    def test_least_flexible_picker_is_used_first(self) -> None:
        result = staff(
            board(
                demand=[slot(8, skill="pick"), slot(8, skill="receive")],
                crew=[
                    person("A-21", name="Ortiz", skills=["receive", "pick"], rate_per_hour=19),
                    person("A-12", name="Rivera", skills=["pick"]),
                ],
            )
        )
        self.assertTrue(result.all_fit)
        pick = next(seat for seat in result.seats if seat.skill == "pick")
        recv = next(seat for seat in result.seats if seat.skill == "receive")
        self.assertEqual(pick.associate_id, "A-12")
        self.assertEqual(recv.associate_id, "A-21")

    def test_clear_board_example_covers_every_slot(self) -> None:
        payload = json.loads((EXAMPLES / "clear-board.json").read_text(encoding="utf-8"))
        result = staff(Board.from_dict(payload))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.seated_count, 11)
        self.assertEqual(result.punched_count, 4)
        by_id = {}
        for seat in result.seats:
            by_id.setdefault(seat.associate_id, []).append(seat.skill)
        self.assertEqual(set(by_id["A-12"]), {"pick"})
        self.assertEqual(set(by_id["A-15"]), {"pick"})
        self.assertEqual(set(by_id["A-18"]), {"pack"})
        self.assertEqual(set(by_id["A-21"]), {"receive"})

    def test_overtime_example_matches_readme(self) -> None:
        payload = json.loads((EXAMPLES / "overtime.json").read_text(encoding="utf-8"))
        auto = staff(Board.from_dict(payload))
        overtime = staff(Board.from_dict({**payload, "strategy": "overtime"}))
        self.assertEqual(next(seat for seat in auto.seats if seat.hour == 11).associate_id, "T-3")
        self.assertEqual(next(seat for seat in overtime.seats if seat.hour == 11).associate_id, "A-12")

    def test_skill_block_example_matches_readme(self) -> None:
        payload = json.loads((EXAMPLES / "skill-block.json").read_text(encoding="utf-8"))
        result = staff(Board.from_dict(payload))
        self.assertEqual(result.seated_count, 1)
        self.assertEqual(result.seats[0].associate_id, "C-1")
        reasons = {item["skill"]: item["reason"] for item in result.leftover}
        self.assertEqual(reasons["pick"], "temp")
        self.assertEqual(reasons["forklift"], "cert")

    def test_labor_example_matches_readme(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text(encoding="utf-8"))
        result = staff(Board.from_dict(payload))
        self.assertEqual(result.seats[0].hour, 8)
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")
        self.assertEqual(result.leftover[0]["hour"], 9)
