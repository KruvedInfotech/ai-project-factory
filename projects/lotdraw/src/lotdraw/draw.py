"""Greedy lot draw: FEFO, FIFO, or fewest-lots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .model import Lot, Order, Wave
from .policies import Policy, is_held


@dataclass(frozen=True)
class Allocation:
    order_id: str
    sku: str
    lot_id: str
    qty: int
    expiry: str
    received: str
    location: str
    remaining_days: int
    life_at_ship: int

    def as_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "sku": self.sku,
            "lot_id": self.lot_id,
            "qty": self.qty,
            "expiry": self.expiry,
            "received": self.received,
            "location": self.location,
            "remaining_days": self.remaining_days,
            "life_at_ship": self.life_at_ship,
        }


@dataclass
class DrawResult:
    policy: Policy
    strategy: str
    today: str
    allocations: list[Allocation]
    leftover: list[dict[str, object]]
    unused: list[dict[str, object]]
    held: list[dict[str, object]]
    expired: list[dict[str, object]]
    lots: list[dict[str, object]]
    asked_qty: int
    filled_qty: int

    @property
    def all_clear(self) -> bool:
        return not self.leftover

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def allocation_count(self) -> int:
        return len(self.allocations)

    @property
    def fill_rate(self) -> float:
        if self.asked_qty <= 0:
            return 0.0
        return self.filled_qty / self.asked_qty

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy.as_dict(),
            "strategy": self.strategy,
            "today": self.today,
            "allocations": [item.as_dict() for item in self.allocations],
            "leftover": list(self.leftover),
            "unused": list(self.unused),
            "held": list(self.held),
            "expired": list(self.expired),
            "lots": list(self.lots),
            "asked_qty": self.asked_qty,
            "filled_qty": self.filled_qty,
            "leftover_count": self.leftover_count,
            "allocation_count": self.allocation_count,
            "fill_rate": self.fill_rate,
            "all_clear": self.all_clear,
        }


def _life_at_ship(lot: Lot, order: Order) -> int:
    return (lot.expiry_date() - order.ship_date()).days


def _remaining_today(lot: Lot, today: date) -> int:
    return (lot.expiry_date() - today).days


def _eligible(lot: Lot, order: Order, remaining: int, today: date, floor: int) -> bool:
    if remaining <= 0:
        return False
    if is_held(lot.hold):
        return False
    if lot.expiry_date() <= today:
        return False
    return _life_at_ship(lot, order) >= floor


def _sort_orders(orders: list[Order]) -> list[Order]:
    return sorted(orders, key=lambda item: (item.priority, item.ship_date(), item.id))


def _sort_lots(lots: list[Lot], remaining: dict[str, int], strategy: str) -> list[Lot]:
    def key(lot: Lot) -> tuple:
        left = remaining[lot.id]
        if strategy == "fifo":
            return (lot.received_date(), lot.expiry_date(), lot.id)
        if strategy == "fewest":
            return (-left, lot.expiry_date(), lot.id)
        return (lot.expiry_date(), lot.received_date(), lot.id)

    return sorted(lots, key=key)


def _reason(
    order: Order,
    sku_lots: list[Lot],
    remaining: dict[str, int],
    today: date,
    floor: int,
    policy: Policy,
) -> str:
    if not sku_lots:
        return "no-stock"
    free = [
        lot
        for lot in sku_lots
        if remaining[lot.id] > 0 and not is_held(lot.hold) and lot.expiry_date() > today
    ]
    held = [lot for lot in sku_lots if remaining[lot.id] > 0 and is_held(lot.hold)]
    eligible = [lot for lot in free if _life_at_ship(lot, order) >= floor]
    if not eligible:
        if free:
            return "short-life"
        if held:
            return "on-hold"
        if any(lot.expiry_date() <= today and remaining[lot.id] > 0 for lot in sku_lots):
            return "expired"
        return "no-stock"
    eligible_qty = sum(remaining[lot.id] for lot in eligible)
    if eligible_qty >= order.qty and not policy.allow_split:
        return "no-split"
    if eligible_qty >= order.qty:
        return "lot-cap"
    return "short-qty"


def _lot_row(lot: Lot, remaining: int, today: date) -> dict[str, object]:
    allocated = lot.qty - remaining
    return {
        **lot.as_dict(),
        "remaining": remaining,
        "allocated": allocated,
        "remaining_days": _remaining_today(lot, today),
    }


def draw(wave: Wave) -> DrawResult:
    today = wave.today_date()
    remaining = {lot.id: lot.qty for lot in wave.lots}
    by_sku: dict[str, list[Lot]] = {}
    for lot in wave.lots:
        by_sku.setdefault(lot.sku, []).append(lot)

    allocations: list[Allocation] = []
    leftover: list[dict[str, object]] = []
    filled_qty = 0
    asked_qty = sum(order.qty for order in wave.orders)

    for order in _sort_orders(wave.orders):
        floor = order.life_floor(wave.policy)
        sku_lots = by_sku.get(order.sku, [])
        before = dict(remaining)
        candidates = [
            lot
            for lot in sku_lots
            if _eligible(lot, order, remaining[lot.id], today, floor)
        ]
        candidates = _sort_lots(candidates, remaining, wave.strategy)
        need = order.qty
        used = 0
        for lot in candidates:
            if used >= wave.policy.max_lots_per_line or need <= 0:
                break
            left = remaining[lot.id]
            if not wave.policy.allow_split and left < need:
                continue
            take = min(left, need)
            if take <= 0:
                continue
            remaining[lot.id] -= take
            need -= take
            used += 1
            filled_qty += take
            allocations.append(
                Allocation(
                    order_id=order.id,
                    sku=order.sku,
                    lot_id=lot.id,
                    qty=take,
                    expiry=lot.expiry,
                    received=lot.received,
                    location=lot.location,
                    remaining_days=_remaining_today(lot, today),
                    life_at_ship=_life_at_ship(lot, order),
                )
            )
        if need > 0:
            leftover.append(
                {
                    **order.as_dict(),
                    "allocated": order.qty - need,
                    "short": need,
                    "reason": _reason(order, sku_lots, before, today, floor, wave.policy),
                }
            )

    unused: list[dict[str, object]] = []
    held: list[dict[str, object]] = []
    expired: list[dict[str, object]] = []
    lot_state: list[dict[str, object]] = []
    for lot in wave.lots:
        row = _lot_row(lot, remaining[lot.id], today)
        lot_state.append(row)
        if remaining[lot.id] <= 0:
            continue
        if is_held(lot.hold):
            held.append(row)
        elif lot.expiry_date() <= today:
            expired.append(row)
        else:
            unused.append(row)

    allocations.sort(key=lambda item: (item.order_id, item.lot_id))
    lot_state.sort(key=lambda item: (str(item["sku"]), str(item["expiry"]), str(item["id"])))
    return DrawResult(
        policy=wave.policy,
        strategy=wave.strategy,
        today=wave.today,
        allocations=allocations,
        leftover=leftover,
        unused=unused,
        held=held,
        expired=expired,
        lots=lot_state,
        asked_qty=asked_qty,
        filled_qty=filled_qty,
    )
