from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from taskweave.floors import FLOORS, manhattan, travel_min
from taskweave.model import Board
from taskweave.weave import weave

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def task(task_id: str, **kwargs) -> dict:
    row = {
        "id": task_id,
        "kind": "putaway",
        "from": "D1",
        "to": "A3-3",
        "pallets": 1,
        "weight_kg": 400,
        "height_mm": 1400,
        "temp": "dry",
        "priority": 2,
        "ready_min": 0,
    }
    row.update(kwargs)
    return row


def board(**kwargs) -> Board:
    payload = {
        "floor": {"preset": "grocery"},
        "strategy": "auto",
        "tasks": [task("PUT-1")],
    }
    payload.update(kwargs)
    return Board.from_dict(payload)


class TravelTests(unittest.TestCase):
    def test_already_there_is_free(self) -> None:
        loc = FLOORS["grocery"].location_map()["D1"]
        self.assertEqual(manhattan(loc, loc), 0)
        self.assertEqual(travel_min(loc, loc, 8), 0)

    def test_reach_travel_is_ceiling_of_cells(self) -> None:
        locs = FLOORS["grocery"].location_map()
        self.assertEqual(manhattan(locs["D1"], locs["A3-3"]), 8)
        self.assertEqual(travel_min(locs["D1"], locs["A3-3"], 8), 1)


class PlanTests(unittest.TestCase):
    def test_single_putaway_starts_on_the_home_truck(self) -> None:
        result = weave(board())
        self.assertTrue(result.all_fit)
        self.assertEqual(result.weaved_count, 1)
        placed = result.legs[0]
        self.assertEqual(placed.task_id, "PUT-1")
        self.assertEqual(placed.truck_id, "RT-1")
        self.assertEqual(placed.start_min, 0)
        self.assertEqual(placed.deadhead_min, 0)
        self.assertEqual(placed.loaded_min, 1)
        self.assertEqual(placed.end_min, 5)
        self.assertFalse(placed.dual)

    def test_same_truck_weaves_a_nearby_pick_as_dual_cycle(self) -> None:
        result = weave(
            board(
                tasks=[
                    task("PUT-11", priority=1, **{"from": "D1", "to": "A3-3"}),
                    task("PICK-11", kind="pick", priority=2, **{"from": "A3-4", "to": "S1"}),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.task_id: item for item in result.legs}
        self.assertEqual(by_id["PUT-11"].truck_id, "RT-1")
        self.assertEqual(by_id["PICK-11"].truck_id, "RT-1")
        self.assertFalse(by_id["PUT-11"].dual)
        self.assertTrue(by_id["PICK-11"].dual)
        self.assertEqual(by_id["PICK-11"].start_min, by_id["PUT-11"].end_min)
        self.assertEqual(result.dual_count, 1)

    def test_second_putaway_opens_a_second_truck(self) -> None:
        result = weave(
            board(
                tasks=[
                    task("PUT-11", priority=1, **{"from": "D1", "to": "A3-3"}),
                    task("PUT-21", priority=1, **{"from": "D2", "to": "A5-2"}),
                ]
            )
        )
        self.assertTrue(result.all_fit)
        by_id = {item.task_id: item for item in result.legs}
        self.assertEqual(by_id["PUT-11"].truck_id, "RT-1")
        self.assertEqual(by_id["PUT-21"].truck_id, "RT-2")
        self.assertEqual(by_id["PUT-11"].start_min, 0)
        self.assertEqual(by_id["PUT-21"].start_min, 0)

    def test_dual_prefers_the_far_pick_over_the_near_replen(self) -> None:
        payload = {
            "floor": {
                "preset": "grocery",
                "trucks": [{"id": "RT-1", "kind": "reach", "start": "D1", "temp": "mixed"}],
            },
            "strategy": "dual",
            "tasks": [
                task("PUT-11", priority=1, **{"from": "D1", "to": "A3-3"}),
                task("PICK-11", kind="pick", priority=2, **{"from": "A6-6", "to": "S1"}),
                task("REP-11", kind="replen", priority=2, **{"from": "R1", "to": "A3-4"}),
            ],
        }
        dual = weave(Board.from_dict(payload))
        nearest = weave(Board.from_dict({**payload, "strategy": "nearest"}))
        self.assertTrue(dual.all_fit)
        self.assertTrue(nearest.all_fit)
        dual_second = [item for item in dual.legs if item.task_id != "PUT-11"][0]
        nearest_second = [item for item in nearest.legs if item.task_id != "PUT-11"][0]
        self.assertEqual(dual_second.task_id, "PICK-11")
        self.assertTrue(dual_second.dual)
        self.assertEqual(nearest_second.task_id, "REP-11")
        self.assertFalse(nearest_second.dual)

    def test_jack_cannot_enter_an_aisle(self) -> None:
        result = weave(
            Board.from_dict(
                {
                    "floor": {"preset": "parcel"},
                    "tasks": [
                        task("PUT-40", **{"from": "P1", "to": "T1"}),
                        task("PUT-41", **{"from": "P1", "to": "A1-1"}),
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.legs[0].task_id, "PUT-40")
        self.assertEqual(result.leftover[0]["id"], "PUT-41")
        self.assertEqual(result.leftover[0]["reason"], "equipment")

    def test_chill_truck_leaves_a_freeze_task(self) -> None:
        result = weave(
            Board.from_dict(
                {
                    "floor": {
                        "preset": "produce",
                        "trucks": [{"id": "RT-C", "kind": "reach", "start": "C1", "temp": "chill"}],
                    },
                    "tasks": [
                        task("PUT-C", temp="chill", **{"from": "C1", "to": "A1-2"}),
                        task("PUT-F", temp="freeze", **{"from": "F3", "to": "A4-2"}),
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.legs[0].task_id, "PUT-C")
        self.assertEqual(result.leftover[0]["id"], "PUT-F")
        self.assertEqual(result.leftover[0]["reason"], "temp")

    def test_labor_cap_leaves_the_second_putaway(self) -> None:
        result = weave(
            board(
                labor_minutes=5,
                tasks=[
                    task("PUT-51", priority=1, **{"from": "D1", "to": "A3-3"}),
                    task("PUT-52", priority=2, **{"from": "D2", "to": "A5-2"}),
                ],
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.weaved_count, 1)
        self.assertEqual(result.legs[0].task_id, "PUT-51")
        self.assertEqual(result.leftover[0]["id"], "PUT-52")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")

    def test_too_late_when_ready_past_shift_end(self) -> None:
        result = weave(board(tasks=[task("LATE", ready_min=480)]))
        self.assertEqual(result.leftover[0]["reason"], "too-late")
        self.assertEqual(result.weaved_count, 0)

    def test_too_tall_for_the_mast(self) -> None:
        result = weave(
            Board.from_dict(
                {
                    "floor": {
                        "preset": "grocery",
                        "trucks": [{"id": "SD-1", "kind": "sitdown", "start": "D3", "temp": "dry"}],
                    },
                    "tasks": [task("HIGH", height_mm=4000, **{"from": "D3", "to": "A1-1"})],
                }
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "too-tall")

    def test_too_heavy_for_the_truck(self) -> None:
        result = weave(board(tasks=[task("HEAVY", weight_kg=9000)]))
        self.assertEqual(result.leftover[0]["reason"], "too-heavy")

    def test_cube_when_pallets_exceed_capacity(self) -> None:
        result = weave(board(tasks=[task("TRIPLE", pallets=3)]))
        self.assertEqual(result.leftover[0]["reason"], "cube")

    def test_shift_leftover_when_the_leg_runs_past_end(self) -> None:
        result = weave(
            board(
                floor={"preset": "grocery", "shift_end_min": 4},
                tasks=[task("SLOW", **{"from": "D1", "to": "A6-6"})],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "shift")

    def test_clear_board_example_weaves_two_dual_cycles(self) -> None:
        payload = json.loads((EXAMPLES / "clear-board.json").read_text(encoding="utf-8"))
        result = weave(Board.from_dict(payload))
        self.assertTrue(result.all_fit)
        by_id = {item.task_id: item for item in result.legs}
        self.assertEqual(by_id["PUT-11"].truck_id, by_id["PICK-11"].truck_id)
        self.assertEqual(by_id["PUT-21"].truck_id, by_id["PICK-21"].truck_id)
        self.assertTrue(by_id["PICK-11"].dual)
        self.assertTrue(by_id["PICK-21"].dual)
        self.assertEqual(result.dual_count, 2)

    def test_equipment_example_matches_readme(self) -> None:
        payload = json.loads((EXAMPLES / "equipment-block.json").read_text(encoding="utf-8"))
        result = weave(Board.from_dict(payload))
        self.assertEqual(result.leftover[0]["reason"], "equipment")
        self.assertEqual(result.legs[0].task_id, "PUT-40")

    def test_labor_example_matches_readme(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text(encoding="utf-8"))
        result = weave(Board.from_dict(payload))
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")
        self.assertEqual(result.legs[0].task_id, "PUT-51")

    def test_fifo_walks_ready_time_not_priority(self) -> None:
        result = weave(
            board(
                strategy="fifo",
                tasks=[
                    task("HOT", priority=1, ready_min=10, **{"from": "D2", "to": "A2-1"}),
                    task("OLD", priority=3, ready_min=0, **{"from": "D1", "to": "A1-1"}),
                ],
            )
        )
        self.assertEqual(result.legs[0].task_id, "OLD")
        self.assertEqual(result.legs[1].task_id, "HOT")
