"""Greedy staging seater: top-off a carrier lane, else open an empty bay."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import PalletSpec, Wave
from .yards import Lane, Yard

REASON_ORDER = (
    "temp",
    "too-heavy",
    "too-long",
    "dwell",
    "cutoff",
    "door",
    "lane-full",
    "carrier-mix",
)


@dataclass(frozen=True)
class Seat:
    pallet_id: str
    lane: str
    door: int | None
    carrier: str
    temp: str
    x_mm: int
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    stack_level: int
    labor_min: int
    priority: int

    @property
    def x2_mm(self) -> int:
        return self.x_mm + self.length_mm

    def as_dict(self) -> dict[str, object]:
        return {
            "pallet_id": self.pallet_id,
            "lane": self.lane,
            "door": self.door,
            "carrier": self.carrier,
            "temp": self.temp,
            "x_mm": self.x_mm,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "stack_level": self.stack_level,
            "labor_min": self.labor_min,
            "priority": self.priority,
        }


@dataclass
class _LaneState:
    lane: Lane
    next_x: int = 0
    weight_used: float = 0.0
    carrier: str | None = None
    door: int | None = None
    seats: list[Seat] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.door is None:
            self.door = self.lane.door

    @property
    def remaining_length(self) -> int:
        return self.lane.length_mm - self.next_x

    @property
    def remaining_weight(self) -> float:
        return self.lane.max_weight_kg - self.weight_used


@dataclass
class SeatResult:
    yard: Yard
    strategy: str
    mix_carriers: bool
    mix_doors: bool
    allow_stack: bool
    labor_cap_min: int
    labor_used_min: int
    seats: list[Seat]
    leftover: list[dict[str, object]]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def seated_count(self) -> int:
        return len(self.seats)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used_min / self.labor_cap_min if self.labor_cap_min else 0.0

    @property
    def length_used_mm(self) -> int:
        return sum(item.length_mm for item in self.seats if item.stack_level == 0)

    @property
    def length_utilization(self) -> float:
        total = self.yard.length_mm
        return self.length_used_mm / total if total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "yard": self.yard.as_dict(),
            "strategy": self.strategy,
            "mix_carriers": self.mix_carriers,
            "mix_doors": self.mix_doors,
            "allow_stack": self.allow_stack,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "length_used_mm": self.length_used_mm,
            "length_utilization": round(self.length_utilization, 4),
            "seated_count": self.seated_count,
            "leftover_count": self.leftover_count,
            "all_fit": self.all_fit,
            "seats": [item.as_dict() for item in self.seats],
            "leftover": list(self.leftover),
        }


def seat(wave: Wave) -> SeatResult:
    wave.validate()
    labor_cap = wave.labor_cap()
    labor_used = 0
    seats: list[Seat] = []
    leftover: list[dict[str, object]] = []
    states = {lane.id: _LaneState(lane) for lane in wave.yard.lanes}

    for pallet in _sort_pallets(wave.pallets, wave.strategy):
        hard = _hard_reason(pallet, wave)
        if hard:
            leftover.append(_leftover(pallet, hard))
            continue
        if len(seats) >= wave.yard.max_pallets:
            leftover.append(_leftover(pallet, "pallet-cap"))
            continue
        cost = wave.yard.minutes_per_pallet
        if labor_used + cost > labor_cap:
            leftover.append(_leftover(pallet, "labor-cap"))
            continue
        choice, stacked, reason = _best_lane(pallet, wave, states)
        if choice is None:
            leftover.append(_leftover(pallet, reason))
            continue
        placed = _place(pallet, states[choice], stacked, cost)
        seats.append(placed)
        labor_used += cost

    return SeatResult(
        yard=wave.yard,
        strategy=wave.strategy,
        mix_carriers=wave.mix_carriers,
        mix_doors=wave.mix_doors,
        allow_stack=wave.allow_stack,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        seats=seats,
        leftover=leftover,
    )


def _sort_pallets(pallets: list[PalletSpec], strategy: str) -> list[PalletSpec]:
    if strategy == "cutoff":
        return sorted(pallets, key=lambda item: (_depart_key(item), item.priority, item.id))
    if strategy == "cluster":
        return sorted(
            pallets,
            key=lambda item: (item.carrier, item.door if item.door is not None else 0, item.priority, item.id),
        )
    if strategy == "compact":
        return sorted(pallets, key=lambda item: (item.length_mm, item.weight_kg, item.id))
    return sorted(
        pallets,
        key=lambda item: (item.priority, _depart_key(item), -item.weight_kg, item.id),
    )


def _depart_key(pallet: PalletSpec) -> int:
    return pallet.depart_min if pallet.depart_min is not None else 10**9


def _hard_reason(pallet: PalletSpec, wave: Wave) -> str | None:
    if pallet.depart_min is not None and pallet.ready_min > pallet.depart_min:
        return "cutoff"
    lanes = [lane for lane in wave.yard.lanes if lane.accepts_temp(pallet.temp)]
    if not lanes:
        return "temp"
    if all(pallet.weight_kg > lane.max_weight_kg for lane in lanes):
        return "too-heavy"
    if all(pallet.length_mm > lane.length_mm for lane in lanes):
        return "too-long"
    if pallet.door is not None and not wave.mix_doors:
        door_lanes = [lane for lane in lanes if lane.door is None or lane.door == pallet.door]
        if not door_lanes:
            return "door"
    return None


def _can_stack(pallet: PalletSpec, state: _LaneState, wave: Wave) -> bool:
    if not wave.allow_stack or not state.seats:
        return False
    last = state.seats[-1]
    if last.stack_level != 0:
        return False
    if last.carrier != pallet.carrier or last.temp != pallet.temp:
        return False
    if pallet.length_mm > last.length_mm:
        return False
    if last.height_mm + pallet.height_mm > state.lane.max_height_mm:
        return False
    if pallet.weight_kg > state.remaining_weight:
        return False
    return True


def _lane_reason(pallet: PalletSpec, state: _LaneState, wave: Wave) -> str | None:
    lane = state.lane
    if not lane.accepts_temp(pallet.temp):
        return "temp"
    if pallet.weight_kg > lane.max_weight_kg:
        return "too-heavy"
    if pallet.length_mm > lane.length_mm:
        return "too-long"
    if pallet.door is not None and not wave.mix_doors:
        claimed = state.door if state.door is not None else lane.door
        if claimed is not None and claimed != pallet.door:
            return "door"
    if state.carrier is not None and state.carrier != pallet.carrier and not wave.mix_carriers:
        return "carrier-mix"
    if lane.is_warmer_than(pallet.temp) and wave.yard.max_dwell_min > 0 and pallet.depart_min is not None:
        if pallet.depart_min - pallet.ready_min > wave.yard.max_dwell_min:
            return "dwell"
    if _can_stack(pallet, state, wave):
        return None
    if pallet.length_mm > state.remaining_length:
        return "lane-full"
    if pallet.weight_kg > state.remaining_weight:
        return "too-heavy"
    return None


def _best_lane(
    pallet: PalletSpec,
    wave: Wave,
    states: dict[str, _LaneState],
) -> tuple[str | None, bool, str]:
    candidates: list[tuple[tuple, str, bool]] = []
    reasons: list[str] = []
    for lane in wave.yard.lanes:
        state = states[lane.id]
        reason = _lane_reason(pallet, state, wave)
        if reason:
            reasons.append(reason)
            continue
        stacked = _can_stack(pallet, state, wave)
        leftover_len = 0 if stacked else state.remaining_length - pallet.length_mm
        top_off = 0 if state.carrier == pallet.carrier else 1
        door_pref = 0 if (pallet.door is None or lane.door == pallet.door) else 1
        stack_pref = 0 if stacked else 1
        score = (stack_pref, top_off, door_pref, leftover_len, lane.id)
        candidates.append((score, lane.id, stacked))
    if candidates:
        candidates.sort()
        _score, lane_id, stacked = candidates[0]
        return lane_id, stacked, ""
    for key in REASON_ORDER:
        if key in reasons:
            return None, False, key
    return None, False, "lane-full"


def _place(pallet: PalletSpec, state: _LaneState, stacked: bool, labor_min: int) -> Seat:
    if stacked:
        last = state.seats[-1]
        x_mm = last.x_mm
        level = 1
    else:
        x_mm = state.next_x
        level = 0
        state.next_x += pallet.length_mm
    door = pallet.door if pallet.door is not None else state.door
    placed = Seat(
        pallet_id=pallet.id,
        lane=state.lane.id,
        door=door,
        carrier=pallet.carrier,
        temp=pallet.temp,
        x_mm=x_mm,
        length_mm=pallet.length_mm,
        width_mm=pallet.width_mm,
        height_mm=pallet.height_mm,
        weight_kg=pallet.weight_kg,
        stack_level=level,
        labor_min=labor_min,
        priority=pallet.priority,
    )
    state.seats.append(placed)
    state.weight_used += pallet.weight_kg
    state.carrier = pallet.carrier if state.carrier is None else state.carrier
    if door is not None:
        state.door = door
    return placed


def _leftover(pallet: PalletSpec, reason: str) -> dict[str, object]:
    row = pallet.as_dict()
    row["reason"] = reason
    return row
