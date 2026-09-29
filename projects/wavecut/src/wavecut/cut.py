"""Greedy wave cutter."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Order, WavePlan
from .shifts import Shift, format_hhmm


@dataclass
class WaveBucket:
    id: str
    start_min: int
    end_min: int
    orders: list[Order] = field(default_factory=list)

    @property
    def lines(self) -> int:
        return sum(order.lines for order in self.orders)

    @property
    def cube_m3(self) -> float:
        return sum(order.cube_m3 for order in self.orders)

    @property
    def pick_min(self) -> int:
        return sum(order.pick_min for order in self.orders)

    @property
    def zones(self) -> list[str]:
        seen: list[str] = []
        for order in self.orders:
            if order.zone not in seen:
                seen.append(order.zone)
        return seen

    @property
    def zone(self) -> str | None:
        names = self.zones
        if not names:
            return None
        if len(names) == 1:
            return names[0]
        return "mixed"

    def as_dict(self, shift: Shift) -> dict[str, object]:
        return {
            "id": self.id,
            "start": format_hhmm(self.start_min),
            "end": format_hhmm(self.end_min),
            "zone": self.zone,
            "order_count": len(self.orders),
            "lines": self.lines,
            "cube_m3": round(self.cube_m3, 3),
            "pick_min": self.pick_min,
            "fill_orders": len(self.orders) / shift.max_orders if shift.max_orders else 0.0,
            "fill_cube": self.cube_m3 / shift.max_cube_m3 if shift.max_cube_m3 else 0.0,
            "fill_pick": self.pick_min / shift.max_pick_min if shift.max_pick_min else 0.0,
            "orders": [order.as_dict() for order in self.orders],
        }


@dataclass
class Assignment:
    wave: WaveBucket
    order: Order

    def as_dict(self) -> dict[str, object]:
        return {
            "wave_id": self.wave.id,
            "start": format_hhmm(self.wave.start_min),
            "end": format_hhmm(self.wave.end_min),
            "order": self.order.as_dict(),
        }


@dataclass
class CutResult:
    shift: Shift
    strategy: str
    waves: list[WaveBucket]
    assignments: list[Assignment]
    leftover: list[dict[str, str]]

    @property
    def all_cut(self) -> bool:
        return not self.leftover

    @property
    def assigned_count(self) -> int:
        return len(self.assignments)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def used_waves(self) -> list[WaveBucket]:
        return [wave for wave in self.waves if wave.orders]

    @property
    def utilization(self) -> float:
        capacity = len(self.waves) * self.shift.max_pick_min
        if capacity <= 0:
            return 0.0
        used = sum(wave.pick_min for wave in self.waves)
        return used / capacity

    @property
    def cube_utilization(self) -> float:
        capacity = len(self.waves) * self.shift.max_cube_m3
        if capacity <= 0:
            return 0.0
        used = sum(wave.cube_m3 for wave in self.waves)
        return used / capacity

    def as_dict(self) -> dict[str, object]:
        return {
            "shift": self.shift.as_dict(),
            "strategy": self.strategy,
            "all_cut": self.all_cut,
            "assigned_count": self.assigned_count,
            "leftover_count": self.leftover_count,
            "utilization": self.utilization,
            "cube_utilization": self.cube_utilization,
            "waves": [wave.as_dict(self.shift) for wave in self.waves],
            "assignments": [item.as_dict() for item in self.assignments],
            "leftover": list(self.leftover),
        }


def _sort_orders(orders: list[Order], strategy: str) -> list[Order]:
    if strategy == "cutoff":
        key = lambda order: (order.priority, order.cutoff_min, order.lines, order.id)
    elif strategy == "zone":
        key = lambda order: (order.priority, order.zone, order.cutoff_min, order.id)
    elif strategy == "cube":
        key = lambda order: (order.priority, -order.cube_m3, order.cutoff_min, order.id)
    else:
        key = lambda order: (order.priority, order.cutoff_min, order.zone, order.lines, order.id)
    return sorted(orders, key=key)


def _hard_reason(order: Order, shift: Shift) -> str | None:
    if order.cube_m3 > shift.max_cube_m3:
        return "over cube for every wave"
    if order.lines > shift.max_lines:
        return "over lines for every wave"
    if order.pick_min > shift.max_pick_min:
        return "over pick time for every wave"
    slots = shift.slots()
    if not slots or all(start + order.pick_min > order.cutoff_min for start, _end in slots):
        return "misses every cutoff window"
    return None


def _fits(wave: WaveBucket, order: Order, shift: Shift) -> bool:
    if wave.start_min + order.pick_min > order.cutoff_min:
        return False
    if len(wave.orders) + 1 > shift.max_orders:
        return False
    if wave.lines + order.lines > shift.max_lines:
        return False
    if wave.cube_m3 + order.cube_m3 > shift.max_cube_m3 + 1e-9:
        return False
    if wave.pick_min + order.pick_min > shift.max_pick_min:
        return False
    if shift.zone_pure and wave.zone and wave.zone != order.zone:
        return False
    return True


def _choose_wave(
    waves: list[WaveBucket], order: Order, shift: Shift, strategy: str
) -> WaveBucket | None:
    candidates = [wave for wave in waves if _fits(wave, order, shift)]
    if not candidates:
        return None
    if strategy in ("zone", "auto"):
        same = [wave for wave in candidates if order.zone in wave.zones]
        if same:
            return same[0]
        if strategy == "zone":
            empty = [wave for wave in candidates if not wave.orders]
            if empty:
                return empty[0]
    return candidates[0]


def cut(plan: WavePlan) -> CutResult:
    plan.validate()
    shift = plan.shift
    waves = [
        WaveBucket(id=f"W{index}", start_min=start, end_min=end)
        for index, (start, end) in enumerate(shift.slots(), start=1)
    ]
    assignments: list[Assignment] = []
    leftover: list[dict[str, str]] = []

    for order in _sort_orders(plan.orders, plan.strategy):
        reason = _hard_reason(order, shift)
        if reason:
            leftover.append({"id": order.id, "reason": reason})
            continue
        wave = _choose_wave(waves, order, shift, plan.strategy)
        if wave is None:
            leftover.append({"id": order.id, "reason": "no remaining capacity before cutoff"})
            continue
        wave.orders.append(order)
        assignments.append(Assignment(wave=wave, order=order))

    leftover.sort(key=lambda item: item["id"])
    assignments.sort(key=lambda item: (item.wave.start_min, item.order.id))
    return CutResult(
        shift=shift,
        strategy=plan.strategy,
        waves=waves,
        assignments=assignments,
        leftover=leftover,
    )
