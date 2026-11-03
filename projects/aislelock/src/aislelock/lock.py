"""Greedy aisle-traffic locker: earliest feasible window per cart."""

from __future__ import annotations

from dataclasses import dataclass

from .floors import Aisle, Floor
from .model import CartSpec, Wave


@dataclass(frozen=True)
class Occupancy:
    cart_id: str
    aisle: str
    start_min: int
    end_min: int
    slots: int
    picks: int

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min

    def as_dict(self) -> dict[str, object]:
        return {
            "cart_id": self.cart_id,
            "aisle": self.aisle,
            "start_min": self.start_min,
            "end_min": self.end_min,
            "duration_min": self.duration_min,
            "slots": self.slots,
            "picks": self.picks,
        }


@dataclass(frozen=True)
class Lock:
    cart_id: str
    priority: int
    temp: str
    bulky: bool
    start_min: int
    end_min: int
    labor_min: int
    visits: tuple[Occupancy, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "cart_id": self.cart_id,
            "priority": self.priority,
            "temp": self.temp,
            "bulky": self.bulky,
            "start_min": self.start_min,
            "end_min": self.end_min,
            "labor_min": self.labor_min,
            "aisles": [visit.aisle for visit in self.visits],
            "visits": [visit.as_dict() for visit in self.visits],
        }


@dataclass
class LockResult:
    floor: Floor
    strategy: str
    exclusive_bulky: bool
    labor_cap_min: int
    labor_used_min: int
    locks: list[Lock]
    leftover: list[dict[str, object]]
    occupancy: list[Occupancy]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def locked_count(self) -> int:
        return len(self.locks)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used_min / self.labor_cap_min if self.labor_cap_min else 0.0

    @property
    def horizon_utilization(self) -> float:
        last = max((item.end_min for item in self.occupancy), default=0)
        return last / self.floor.horizon_min if self.floor.horizon_min else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "floor": self.floor.as_dict(),
            "strategy": self.strategy,
            "exclusive_bulky": self.exclusive_bulky,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "horizon_min": self.floor.horizon_min,
            "horizon_utilization": round(self.horizon_utilization, 4),
            "locked_count": self.locked_count,
            "leftover_count": self.leftover_count,
            "all_fit": self.all_fit,
            "locks": [item.as_dict() for item in self.locks],
            "leftover": list(self.leftover),
            "occupancy": [item.as_dict() for item in self.occupancy],
        }


def lock(wave: Wave) -> LockResult:
    wave.validate()
    labor_cap = wave.labor_cap()
    labor_used = 0
    occupancies: list[Occupancy] = []
    locks: list[Lock] = []
    leftover: list[dict[str, object]] = []

    for cart in _sort_carts(wave.carts, wave.strategy):
        hard = _hard_reason(cart, wave)
        if hard:
            leftover.append(_leftover(cart, hard))
            continue
        if len(locks) >= wave.floor.max_carts:
            leftover.append(_leftover(cart, "cart-cap"))
            continue
        cost = labor_cost(cart, wave.floor)
        if labor_used + cost > labor_cap:
            leftover.append(_leftover(cart, "labor-cap"))
            continue
        start, visits, reason = _earliest_window(cart, wave, occupancies)
        if start is None or not visits:
            leftover.append(_leftover(cart, reason))
            continue
        booked = Lock(
            cart_id=cart.id,
            priority=cart.priority,
            temp=cart.temp,
            bulky=cart.bulky,
            start_min=start,
            end_min=visits[-1].end_min,
            labor_min=cost,
            visits=tuple(visits),
        )
        locks.append(booked)
        occupancies.extend(visits)
        labor_used += cost

    return LockResult(
        floor=wave.floor,
        strategy=wave.strategy,
        exclusive_bulky=wave.exclusive_bulky,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        locks=locks,
        leftover=leftover,
        occupancy=occupancies,
    )


def visit_duration(aisle: Aisle, picks: int, minutes_per_pick: int) -> int:
    return max(1, aisle.minutes + picks * minutes_per_pick)


def labor_cost(cart: CartSpec, floor: Floor) -> int:
    hop = floor.minutes_per_hop * max(0, len(cart.walk) - 1)
    dwell = sum(
        visit_duration(floor.aisle_map()[step.aisle], step.picks, floor.minutes_per_pick)
        for step in cart.walk
        if step.aisle in floor.aisle_map()
    )
    return floor.minutes_per_cart + dwell + hop


def _sort_carts(carts: list[CartSpec], strategy: str) -> list[CartSpec]:
    if strategy == "cutoff":
        return sorted(carts, key=lambda cart: (_cutoff_key(cart), cart.priority, cart.id))
    if strategy == "cluster":
        return sorted(
            carts,
            key=lambda cart: (cart.walk[0].aisle if cart.walk else "", cart.priority, cart.id),
        )
    if strategy == "compact":
        return sorted(
            carts,
            key=lambda cart: (len(cart.walk), sum(step.picks for step in cart.walk), cart.priority, cart.id),
        )
    return sorted(
        carts,
        key=lambda cart: (
            cart.priority,
            0 if cart.bulky else 1,
            _cutoff_key(cart),
            -len(cart.walk),
            cart.id,
        ),
    )


def _cutoff_key(cart: CartSpec) -> int:
    return cart.cutoff_min if cart.cutoff_min is not None else 10**9


def _hard_reason(cart: CartSpec, wave: Wave) -> str | None:
    lookup = wave.floor.aisle_map()
    for step in cart.walk:
        aisle = lookup.get(step.aisle)
        if aisle is None:
            return "unknown-aisle"
        if not aisle.accepts_temp(cart.temp):
            return "temp"
    return None


def _span_min(cart: CartSpec, floor: Floor) -> int:
    lookup = floor.aisle_map()
    dwell = sum(visit_duration(lookup[step.aisle], step.picks, floor.minutes_per_pick) for step in cart.walk)
    hop = floor.minutes_per_hop * max(0, len(cart.walk) - 1)
    return dwell + hop


def _slots_needed(cart: CartSpec, aisle: Aisle, exclusive_bulky: bool) -> int:
    if exclusive_bulky and cart.bulky:
        return aisle.capacity
    return 1


def _earliest_window(
    cart: CartSpec,
    wave: Wave,
    occupancies: list[Occupancy],
) -> tuple[int | None, list[Occupancy], str]:
    hard = _hard_reason(cart, wave)
    if hard:
        return None, [], hard
    span = _span_min(cart, wave.floor)
    horizon_latest = wave.floor.horizon_min - span
    if cart.ready_min > horizon_latest:
        return None, [], "aisle-busy"
    if cart.cutoff_min is not None and cart.ready_min > cart.cutoff_min - span:
        return None, [], "cutoff"
    latest = horizon_latest
    if cart.cutoff_min is not None:
        latest = min(latest, cart.cutoff_min - span)
    for start in range(cart.ready_min, latest + 1):
        visits = _try_start(cart, start, wave, occupancies)
        if visits is not None:
            return start, visits, ""
    return None, [], "aisle-busy"


def _try_start(
    cart: CartSpec,
    start: int,
    wave: Wave,
    occupancies: list[Occupancy],
) -> list[Occupancy] | None:
    lookup = wave.floor.aisle_map()
    clock = start
    visits: list[Occupancy] = []
    for index, step in enumerate(cart.walk):
        aisle = lookup[step.aisle]
        duration = visit_duration(aisle, step.picks, wave.floor.minutes_per_pick)
        slots = _slots_needed(cart, aisle, wave.exclusive_bulky)
        end = clock + duration
        if not _aisle_has_room(aisle, clock, end, slots, occupancies):
            return None
        visits.append(
            Occupancy(
                cart_id=cart.id,
                aisle=aisle.id,
                start_min=clock,
                end_min=end,
                slots=slots,
                picks=step.picks,
            )
        )
        clock = end
        if index < len(cart.walk) - 1:
            clock += wave.floor.minutes_per_hop
    return visits


def _aisle_has_room(
    aisle: Aisle,
    start: int,
    end: int,
    slots: int,
    occupancies: list[Occupancy],
) -> bool:
    used = 0
    for other in occupancies:
        if other.aisle != aisle.id:
            continue
        if start < other.end_min and other.start_min < end:
            used += other.slots
    return used + slots <= aisle.capacity


def _leftover(cart: CartSpec, reason: str) -> dict[str, object]:
    return {
        "id": cart.id,
        "priority": cart.priority,
        "temp": cart.temp,
        "bulky": cart.bulky,
        "ready_min": cart.ready_min,
        "cutoff_min": cart.cutoff_min,
        "walk": [step.as_dict() for step in cart.walk],
        "reason": reason,
    }
