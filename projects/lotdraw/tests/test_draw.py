from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lotdraw.draw import draw
from lotdraw.model import Wave


def order(
    oid: str,
    sku: str = "MILK-1L",
    qty: int = 10,
    ship_by: str = "2026-10-10",
    priority: int = 2,
    min_remaining_days: int | None = None,
) -> dict:
    data = {
        "id": oid,
        "sku": sku,
        "qty": qty,
        "ship_by": ship_by,
        "priority": priority,
    }
    if min_remaining_days is not None:
        data["min_remaining_days"] = min_remaining_days
    return data


def lot(
    lid: str,
    sku: str = "MILK-1L",
    qty: int = 24,
    expiry: str = "2026-10-20",
    received: str = "2026-10-01",
    location: str = "A-1",
    hold: str = "",
) -> dict:
    return {
        "id": lid,
        "sku": sku,
        "qty": qty,
        "expiry": expiry,
        "received": received,
        "location": location,
        "hold": hold,
    }


def wave(**kwargs) -> Wave:
    payload = {
        "policy": {"preset": "grocery_dc"},
        "today": "2026-10-09",
        "strategy": "fefo",
        "orders": [order("SO-1")],
        "lots": [lot("L-1")],
    }
    payload.update(kwargs)
    return Wave.from_dict(payload)


class DrawTests(unittest.TestCase):
    def test_grocery_wave_example_fills_fefo(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "grocery-wave.json"
        result = draw(Wave.from_dict(json.loads(example.read_text())))
        self.assertTrue(result.all_clear)
        self.assertEqual(result.filled_qty, 102)
        by_order: dict[str, list[str]] = {}
        qty: dict[tuple[str, str], int] = {}
        for item in result.allocations:
            by_order.setdefault(item.order_id, []).append(item.lot_id)
            qty[(item.order_id, item.lot_id)] = item.qty
        self.assertEqual(by_order["SO-1001"], ["L-M1", "L-M2"])
        self.assertEqual(qty[("SO-1001", "L-M1")], 24)
        self.assertEqual(qty[("SO-1001", "L-M2")], 16)
        self.assertEqual(qty[("SO-1002", "L-M2")], 20)
        leftover_milk = {item["id"]: item["remaining"] for item in result.unused}
        self.assertEqual(leftover_milk["L-M2"], 12)

    def test_fefo_picks_earlier_expiry(self) -> None:
        result = draw(
            wave(
                orders=[order("SO-1", qty=10)],
                lots=[
                    lot("L-NEW", qty=20, expiry="2026-11-01", received="2026-09-01"),
                    lot("L-OLD", qty=20, expiry="2026-10-20", received="2026-09-15"),
                ],
            )
        )
        self.assertEqual(result.allocations[0].lot_id, "L-OLD")

    def test_fifo_picks_earlier_received(self) -> None:
        result = draw(
            wave(
                strategy="fifo",
                orders=[order("SO-1", qty=10)],
                lots=[
                    lot("L-A", qty=20, expiry="2026-10-20", received="2026-09-15"),
                    lot("L-B", qty=20, expiry="2026-11-01", received="2026-09-01"),
                ],
            )
        )
        self.assertEqual(result.allocations[0].lot_id, "L-B")

    def test_fewest_uses_the_larger_lot(self) -> None:
        result = draw(
            wave(
                strategy="fewest",
                orders=[order("SO-1", qty=40)],
                lots=[
                    lot("L-M1", qty=24, expiry="2026-10-20"),
                    lot("L-M2", qty=48, expiry="2026-10-27"),
                ],
            )
        )
        self.assertEqual(len(result.allocations), 1)
        self.assertEqual(result.allocations[0].lot_id, "L-M2")
        self.assertEqual(result.allocations[0].qty, 40)

    def test_short_life_skips_near_expiry_lot(self) -> None:
        result = draw(
            wave(
                orders=[order("SO-1", qty=10, min_remaining_days=21)],
                lots=[
                    lot("L-J1", qty=50, expiry="2026-10-22"),
                    lot("L-J2", qty=10, expiry="2026-11-20"),
                ],
            )
        )
        self.assertTrue(result.all_clear)
        self.assertEqual(result.allocations[0].lot_id, "L-J2")

    def test_short_life_leftover_when_no_lot_meets_floor(self) -> None:
        result = draw(
            wave(
                orders=[order("SO-1", qty=5, min_remaining_days=60)],
                lots=[lot("L-J1", qty=50, expiry="2026-10-22")],
            )
        )
        self.assertFalse(result.all_clear)
        self.assertEqual(result.leftover[0]["reason"], "short-life")
        self.assertEqual(result.filled_qty, 0)

    def test_quality_hold_is_skipped(self) -> None:
        result = draw(
            wave(
                policy={"preset": "pharma_vault"},
                orders=[order("SO-1", sku="API-X", qty=20, ship_by="2026-11-01")],
                lots=[
                    lot(
                        "L-H1",
                        sku="API-X",
                        qty=40,
                        expiry="2027-06-01",
                        received="2026-01-15",
                        hold="quality",
                    )
                ],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "on-hold")
        self.assertEqual(result.held[0]["id"], "L-H1")

    def test_partial_fill_is_short_qty(self) -> None:
        result = draw(
            wave(
                orders=[order("SO-1", qty=10)],
                lots=[lot("L-1", qty=8)],
            )
        )
        self.assertEqual(result.allocations[0].qty, 8)
        self.assertEqual(result.leftover[0]["reason"], "short-qty")
        self.assertEqual(result.leftover[0]["short"], 2)

    def test_no_split_rejects_two_small_lots(self) -> None:
        result = draw(
            wave(
                policy={"preset": "cosmetics_fc"},
                orders=[order("SO-1", sku="SERUM", qty=30, ship_by="2026-10-20")],
                lots=[
                    lot("L-S1", sku="SERUM", qty=18, expiry="2027-01-15", received="2026-06-01"),
                    lot("L-S2", sku="SERUM", qty=18, expiry="2027-04-01", received="2026-07-01"),
                ],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "no-split")
        self.assertEqual(result.filled_qty, 0)

    def test_expired_lot_is_not_drawn(self) -> None:
        result = draw(
            wave(
                orders=[order("SO-1", qty=5)],
                lots=[lot("L-OLD", qty=20, expiry="2026-10-09")],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "expired")
        self.assertEqual(result.expired[0]["id"], "L-OLD")

    def test_unknown_sku_is_no_stock(self) -> None:
        result = draw(
            wave(
                orders=[order("SO-1", sku="MISSING", qty=5)],
                lots=[lot("L-1")],
            )
        )
        self.assertEqual(result.leftover[0]["reason"], "no-stock")

    def test_priority_draws_first(self) -> None:
        result = draw(
            wave(
                orders=[
                    order("SO-LOW", qty=24, priority=2),
                    order("SO-HIGH", qty=24, priority=1),
                ],
                lots=[lot("L-1", qty=24)],
            )
        )
        self.assertEqual(result.allocations[0].order_id, "SO-HIGH")
        leftover = {item["id"]: item["reason"] for item in result.leftover}
        self.assertEqual(leftover["SO-LOW"], "no-stock")

    def test_lot_cap_stops_after_max_lots(self) -> None:
        result = draw(
            wave(
                policy={"preset": "grocery_dc", "max_lots_per_line": 1},
                orders=[order("SO-1", qty=40)],
                lots=[
                    lot("L-M1", qty=24, expiry="2026-10-20"),
                    lot("L-M2", qty=48, expiry="2026-10-27"),
                ],
            )
        )
        self.assertEqual(result.allocations[0].lot_id, "L-M1")
        self.assertEqual(result.allocations[0].qty, 24)
        self.assertEqual(result.leftover[0]["reason"], "lot-cap")

    def test_quality_hold_example(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "quality-hold.json"
        result = draw(Wave.from_dict(json.loads(example.read_text())))
        reasons = {item["id"]: item["reason"] for item in result.leftover}
        self.assertEqual(reasons["SO-3001"], "on-hold")
        self.assertEqual(reasons["SO-3002"], "short-qty")
        self.assertEqual(result.filled_qty, 8)
