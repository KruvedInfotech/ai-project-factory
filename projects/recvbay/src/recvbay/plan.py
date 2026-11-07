"""Greedy inbound planner: pin a door window, never unseat an earlier ASN."""

from __future__ import annotations

from dataclasses import dataclass, field

from .docks import Door, Dock, duration_min
from .model import Board, LoadSpec

REASON_ORDER = (
    "temp",
    "equipment",
    "too-tall",
    "staging",
    "vendor-mix",
    "dwell",
    "wait",
    "door-busy",
    "door",
)


@dataclass(frozen=True)
class Slot:
    load_id: str
    vendor: str
    door: str
    door_number: int
    temp: str
    unload: str
    pallets: int
    start_min: int
    end_min: int
    labor_min: int
    priority: int
    floor_loaded: bool

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min

    def as_dict(self) -> dict[str, object]:
        return {
            "load_id": self.load_id,
            "vendor": self.vendor,
            "door": self.door,
            "door_number": self.door_number,
            "temp": self.temp,
            "unload": self.unload,
            "pallets": self.pallets,
            "start_min": self.start_min,
            "end_min": self.end_min,
            "labor_min": self.labor_min,
            "priority": self.priority,
            "floor_loaded": self.floor_loaded,
        }


@dataclass
class _DoorState:
    door: Door
    free_at: int = 0
    vendor: str | None = None
    slots: list[Slot] = field(default_factory=list)


@dataclass
class PlanResult:
    dock: Dock
    strategy: str
    mix_doors: bool
    mix_vendors: bool
    labor_cap_min: int
    labor_used_min: int
    slots: list[Slot]
    leftover: list[dict[str, object]]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def docked_count(self) -> int:
        return len(self.slots)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used_min / self.labor_cap_min if self.labor_cap_min else 0.0

    @property
    def door_time_used_min(self) -> int:
        return sum(item.duration_min for item in self.slots)

    @property
    def door_time_utilization(self) -> float:
        total = self.dock.door_time_min()
        return self.door_time_used_min / total if total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "dock": self.dock.as_dict(),
            "strategy": self.strategy,
            "mix_doors": self.mix_doors,
            "mix_vendors": self.mix_vendors,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "door_time_used_min": self.door_time_used_min,
            "door_time_utilization": round(self.door_time_utilization, 4),
            "docked_count": self.docked_count,
            "leftover_count": self.leftover_count,
            "all_fit": self.all_fit,
            "slots": [item.as_dict() for item in self.slots],
            "leftover": list(self.leftover),
        }


def plan(board: Board) -> PlanResult:
    board.validate()
    labor_cap = board.labor_cap()
    labor_used = 0
    slots: list[Slot] = []
    leftover: list[dict[str, object]] = []
    states = {door.id: _DoorState(door) for door in board.dock.doors}

    for load in _sort_loads(board.loads, board.strategy, board.dock.minutes_per_pallet):
        hard = _hard_reason(load, board)
        if hard:
            leftover.append(_leftover(load, hard))
            continue
        duration = duration_min(load.pallets, board.dock.minutes_per_pallet, load.floor_loaded)
        if labor_used + duration > labor_cap:
            leftover.append(_leftover(load, "labor-cap"))
            continue
        door_id, start, reason = _best_door(load, board, states, duration)
        if door_id is None:
            leftover.append(_leftover(load, reason))
            continue
        placed = _place(load, states[door_id], start, duration)
        slots.append(placed)
        labor_used += duration

    return PlanResult(
        dock=board.dock,
        strategy=board.strategy,
        mix_doors=board.mix_doors,
        mix_vendors=board.mix_vendors,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        slots=slots,
        leftover=leftover,
    )


def _sort_loads(loads: list[LoadSpec], strategy: str, rate: int) -> list[LoadSpec]:
    if strategy == "eta":
        return sorted(loads, key=lambda item: (item.eta_min, item.priority, item.id))
    if strategy == "cluster":
        return sorted(loads, key=lambda item: (item.vendor, item.temp, item.eta_min, item.id))
    if strategy == "compact":
        return sorted(
            loads,
            key=lambda item: (
                duration_min(item.pallets, rate, item.floor_loaded),
                item.eta_min,
                item.id,
            ),
        )
    return sorted(loads, key=lambda item: (item.priority, item.eta_min, -item.pallets, item.id))


def _candidates(load: LoadSpec, board: Board) -> list[Door]:
    doors = list(board.dock.doors)
    if load.door is not None and not board.mix_doors:
        doors = [door for door in doors if door.number == load.door]
    return doors


def _needs_reefer(load: LoadSpec) -> bool:
    return load.temp in ("chill", "freeze")


def _hard_reason(load: LoadSpec, board: Board) -> str | None:
    if load.eta_min >= board.dock.shift_end_min:
        return "too-late"
    doors = _candidates(load, board)
    if not doors:
        return "door"
    temp_ok = [door for door in doors if door.accepts_temp(load.temp)]
    if not temp_ok:
        return "temp"
    if load.floor_loaded and not any(door.has_leveler for door in temp_ok):
        return "equipment"
    if _needs_reefer(load) and not any(door.has_reefer for door in temp_ok):
        return "equipment"
    if all(load.trailer_height_mm > door.height_mm for door in temp_ok):
        return "too-tall"
    if all(load.pallets > door.staging_pallets for door in temp_ok):
        return "staging"
    duration = duration_min(load.pallets, board.dock.minutes_per_pallet, load.floor_loaded)
    if load.unload == "live" and load.appointment_min is not None and duration > load.appointment_min:
        return "dwell"
    return None


def _door_reason(load: LoadSpec, state: _DoorState, board: Board, duration: int) -> str | None:
    door = state.door
    if not door.accepts_temp(load.temp):
        return "temp"
    if load.floor_loaded and not door.has_leveler:
        return "equipment"
    if _needs_reefer(load) and not door.has_reefer:
        return "equipment"
    if load.trailer_height_mm > door.height_mm:
        return "too-tall"
    if load.pallets > door.staging_pallets:
        return "staging"
    if not board.mix_vendors and state.vendor is not None and state.vendor != load.vendor:
        return "vendor-mix"
    start = max(load.eta_min, state.free_at)
    end = start + duration
    if end > board.dock.shift_end_min:
        return "door-busy"
    if load.unload == "live":
        wait = start - load.eta_min
        if wait > board.dock.max_wait_min:
            return "wait"
        if load.appointment_min is not None and end - load.eta_min > load.appointment_min:
            return "dwell"
    return None


def _best_door(
    load: LoadSpec,
    board: Board,
    states: dict[str, _DoorState],
    duration: int,
) -> tuple[str | None, int, str]:
    candidates: list[tuple[tuple, str, int]] = []
    reasons: list[str] = []
    for door in _candidates(load, board):
        state = states[door.id]
        reason = _door_reason(load, state, board, duration)
        if reason:
            reasons.append(reason)
            continue
        start = max(load.eta_min, state.free_at)
        wait = start - load.eta_min
        preferred = 0 if (load.door is None or door.number == load.door) else 1
        continue_vendor = 0 if (state.vendor is None or state.vendor == load.vendor) else 1
        staging_left = door.staging_pallets - load.pallets
        score = (preferred, wait, continue_vendor, -staging_left, door.id)
        candidates.append((score, door.id, start))
    if candidates:
        candidates.sort()
        _score, door_id, start = candidates[0]
        return door_id, start, ""
    for key in REASON_ORDER:
        if key in reasons:
            return None, 0, key
    return None, 0, "door-busy"


def _place(load: LoadSpec, state: _DoorState, start: int, duration: int) -> Slot:
    placed = Slot(
        load_id=load.id,
        vendor=load.vendor,
        door=state.door.id,
        door_number=state.door.number,
        temp=load.temp,
        unload=load.unload,
        pallets=load.pallets,
        start_min=start,
        end_min=start + duration,
        labor_min=duration,
        priority=load.priority,
        floor_loaded=load.floor_loaded,
    )
    state.slots.append(placed)
    state.free_at = placed.end_min
    if state.vendor is None:
        state.vendor = load.vendor
    return placed


def _leftover(load: LoadSpec, reason: str) -> dict[str, object]:
    row = load.as_dict()
    row["reason"] = reason
    return row
