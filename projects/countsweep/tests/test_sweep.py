from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from countsweep.model import Wave
from countsweep.sweep import sweep

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def loc(**kwargs) -> dict:
    row = {
        "id": "P-A-01-1",
        "sku": "RICE",
        "book_qty": 10,
        "abc": "A",
        "aisle": 1,
        "bay": 1,
        "level": 1,
        "last_counted": "2026-10-01",
    }
    row.update(kwargs)
    return row


def wave(**kwargs) -> Wave:
    payload = {
        "policy": {"preset": "grocery_dc"},
        "strategy": "overdue",
        "as_of": "2026-10-15",
        "locations": [loc()],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


class SweepTests(unittest.TestCase):
    def test_overdue_a_face_is_scheduled(self) -> None:
        result = sweep(wave())
        self.assertTrue(result.all_clear)
        self.assertEqual(result.counts[0].location_id, "P-A-01-1")
        self.assertEqual(result.counts[0].overdue_days, 7)

    def test_recent_c_face_is_not_due(self) -> None:
        result = sweep(
            wave(
                locations=[
                    loc(
                        id="P-C-05-1",
                        sku="TAPE",
                        abc="C",
                        aisle=5,
                        last_counted="2026-08-01",
                    )
                ]
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.due_count, 0)
        self.assertEqual(result.scheduled_count, 0)
        self.assertEqual(result.locations[0]["status"], "ok")

    def test_never_counted_is_due_first(self) -> None:
        result = sweep(
            wave(
                locations=[
                    loc(id="P-A-01-1", last_counted="2026-10-01"),
                    loc(id="P-A-02-1", sku="SUGAR", aisle=2, last_counted=""),
                ]
            )
        )
        self.assertEqual([item.location_id for item in result.counts], ["P-A-02-1", "P-A-01-1"])
        self.assertIsNone(result.counts[0].days_since)

    def test_high_shrink_uses_the_shorter_cycle(self) -> None:
        result = sweep(
            wave(
                locations=[
                    loc(
                        id="P-B-03-1",
                        sku="SOAP",
                        abc="B",
                        aisle=3,
                        last_counted="2026-10-05",
                        high_shrink=True,
                    )
                ]
            )
        )
        self.assertEqual(result.scheduled_count, 1)
        self.assertTrue(result.counts[0].high_shrink)
        self.assertEqual(result.counts[0].overdue_days, 3)

    def test_due_wave_example_orders_never_then_soap_then_rice(self) -> None:
        payload = json.loads((EXAMPLES / "due-wave.json").read_text())
        result = sweep(Wave.from_dict(payload))
        self.assertTrue(result.all_clear)
        self.assertEqual(
            [item.location_id for item in result.counts],
            ["P-A-02-1", "P-B-03-1", "P-A-01-1"],
        )
        self.assertEqual(result.labor_used_min, 11)
        self.assertEqual(result.due_count, 3)
        current = {row["id"] for row in result.locations if row["status"] == "ok"}
        self.assertEqual(current, {"P-A-01-2", "P-C-05-1", "P-B-03-2"})

    def test_labor_cap_stops_later_faces(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text())
        result = sweep(Wave.from_dict(payload))
        self.assertEqual(result.scheduled_count, 2)
        self.assertEqual(result.labor_used_min, 8)
        self.assertEqual([item.location_id for item in result.counts], ["P-A-01-1", "P-A-02-1"])
        self.assertEqual({item["reason"] for item in result.leftover}, {"labor-cap"})
        self.assertEqual(len(result.leftover), 2)

    def test_skip_empty_leaves_zero_faces(self) -> None:
        payload = json.loads((EXAMPLES / "skip-empty.json").read_text())
        result = sweep(Wave.from_dict(payload))
        self.assertEqual(result.scheduled_count, 1)
        self.assertEqual(result.counts[0].location_id, "P-A-01-2")
        self.assertEqual(result.leftover[0]["id"], "P-A-01-1")
        self.assertEqual(result.leftover[0]["reason"], "skip-empty")
        self.assertEqual(result.locations[2]["status"], "ok")

    def test_pharma_counts_empty_faces(self) -> None:
        result = sweep(
            wave(
                policy={"preset": "pharma_vault"},
                locations=[
                    loc(id="V-A-01-1", sku="", book_qty=0, last_counted="2026-10-01"),
                ],
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.counts[0].location_id, "V-A-01-1")
        self.assertTrue(result.counts[0].freeze)

    def test_blocked_due_face_is_leftover(self) -> None:
        result = sweep(
            wave(
                locations=[
                    loc(id="P-A-01-1", blocked=True),
                    loc(id="P-A-01-2", sku="OIL", bay=2),
                ]
            )
        )
        self.assertEqual(result.counts[0].location_id, "P-A-01-2")
        self.assertEqual(result.leftover[0]["id"], "P-A-01-1")
        self.assertEqual(result.leftover[0]["reason"], "blocked")
        self.assertEqual(result.locations[0]["status"], "blocked")

    def test_abc_strategy_walks_a_before_a_more_overdue_b(self) -> None:
        result = sweep(
            wave(
                strategy="abc",
                locations=[
                    loc(
                        id="P-B-03-1",
                        sku="SOAP",
                        abc="B",
                        aisle=3,
                        last_counted="2026-01-01",
                    ),
                    loc(id="P-A-01-1", last_counted="2026-10-01"),
                ],
            )
        )
        self.assertEqual([item.location_id for item in result.counts], ["P-A-01-1", "P-B-03-1"])

    def test_aisle_strategy_is_serpentine(self) -> None:
        result = sweep(
            wave(
                strategy="aisle",
                locations=[
                    loc(id="A1-B3", aisle=1, bay=3, last_counted=""),
                    loc(id="A1-B1", aisle=1, bay=1, last_counted=""),
                    loc(id="A2-B1", aisle=2, bay=1, last_counted=""),
                    loc(id="A2-B5", aisle=2, bay=5, last_counted=""),
                ],
            )
        )
        self.assertEqual(
            [item.location_id for item in result.counts],
            ["A1-B1", "A1-B3", "A2-B5", "A2-B1"],
        )

    def test_shrink_strategy_leads_with_high_shrink(self) -> None:
        result = sweep(
            wave(
                strategy="shrink",
                locations=[
                    loc(id="P-A-01-1", last_counted=""),
                    loc(id="P-A-02-1", sku="CANDY", aisle=2, last_counted="", high_shrink=True),
                ],
            )
        )
        self.assertEqual(result.counts[0].location_id, "P-A-02-1")

    def test_variance_flag_and_matching_book(self) -> None:
        payload = json.loads((EXAMPLES / "variance-flag.json").read_text())
        result = sweep(Wave.from_dict(payload))
        self.assertTrue(result.all_clear)
        by_id = {item.location_id: item for item in result.counts}
        self.assertTrue(by_id["V-A-01-1"].flag)
        self.assertEqual(by_id["V-A-01-1"].variance, -6)
        self.assertFalse(by_id["V-A-01-2"].flag)
        self.assertTrue(by_id["V-A-01-1"].freeze)
        self.assertEqual(result.flag_count, 1)
        self.assertEqual(result.scheduled_count, 2)

    def test_travel_adds_aisle_change(self) -> None:
        result = sweep(
            wave(
                locations=[
                    loc(id="P-A-01-1", aisle=1, last_counted=""),
                    loc(id="P-A-04-1", sku="OIL", aisle=4, last_counted=""),
                ]
            )
        )
        self.assertEqual(result.counts[0].minutes, 3)
        self.assertEqual(result.counts[1].minutes, 5)
        self.assertEqual(result.labor_used_min, 8)

    def test_duplicate_location_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            wave(locations=[loc(), loc()])

    def test_missing_as_of_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Wave.from_dict(
                {
                    "policy": {"preset": "grocery_dc"},
                    "locations": [loc()],
                }
            )
