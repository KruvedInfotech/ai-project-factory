"""Greedy interleaver: pin a truck leg, never unseat an earlier task."""

from __future__ import annotations

from dataclasses import dataclass, field

from .floors import Floor, Location, Truck, opposite_flow, travel_min
from .model import Board, TaskSpec

REASON_ORDER = (
    "equipment",
    "temp",
    "too-tall",
    "too-heavy",
    "cube",
    "too-late",
    "shift",
    "labor-cap",
)


@dataclass(frozen=True)
class Leg:
    task_id: str
    truck_id: str
    kind: str
    origin: str
    pickup: str
    drop: str
    start_min: int
    pickup_min: int
    drop_min: int
    end_min: int
    deadhead_min: int
    loaded_min: int
    handling_min: int
    dual: bool
    pallets: int
    temp: str
    priority: int

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "truck_id": self.truck_id,
            "kind": self.kind,
            "origin": self.origin,
            "from": self.pickup,
            "to": self.drop,
            "start_min": self.start_min,
            "pickup_min": self.pickup_min,
            "drop_min": self.drop_min,
            "end_min": self.end_min,
            "deadhead_min": self.deadhead_min,
            "loaded_min": self.loaded_min,
            "handling_min": self.handling_min,
            "dual": self.dual,
            "pallets": self.pallets,
            "temp": self.temp,
            "priority": self.priority,
            "duration_min": self.duration_min,
        }


@dataclass
class _TruckState:
    truck: Truck
    location: Location
    free_at: int = 0
    last_kind: str | None = None
    legs: list[Leg] = field(default_factory=list)


@dataclass
class WeaveResult:
    floor: Floor
    strategy: str
    labor_cap_min: int
    labor_used_min: int
    legs: list[Leg]
    leftover: list[dict[str, object]]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def weaved_count(self) -> int:
        return len(self.legs)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def deadhead_min(self) -> int:
        return sum(item.deadhead_min for item in self.legs)

    @property
    def loaded_min(self) -> int:
        return sum(item.loaded_min for item in self.legs)

    @property
    def deadhead_ratio(self) -> float:
        travel = self.deadhead_min + self.loaded_min
        return self.deadhead_min / travel if travel else 0.0

    @property
    def dual_count(self) -> int:
        return sum(1 for item in self.legs if item.dual)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used_min / self.labor_cap_min if self.labor_cap_min else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "floor": self.floor.as_dict(),
            "strategy": self.strategy,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "deadhead_min": self.deadhead_min,
            "loaded_min": self.loaded_min,
            "deadhead_ratio": round(self.deadhead_ratio, 4),
            "dual_count": self.dual_count,
            "weaved_count": self.weaved_count,
            "leftover_count": self.leftover_count,
            "all_fit": self.all_fit,
            "legs": [item.as_dict() for item in self.legs],
            "leftover": list(self.leftover),
        }


def weave(board: Board) -> WeaveResult:
    board.validate()
    labor_cap = board.labor_cap()
    labor_used = 0
    legs: list[Leg] = []
    leftover: list[dict[str, object]] = []
    locations = board.floor.location_map()
    states = {
        truck.id: _TruckState(truck, locations[truck.start])
        for truck in board.floor.trucks
    }

    remaining: list[TaskSpec] = []
    for task in board.tasks:
        hard = _hard_reason(task, board, locations)
        if hard:
            leftover.append(_leftover(task, hard))
        else:
            remaining.append(task)

    while remaining:
        truck_id, task, reason = _best_pair(remaining, board, states, locations, labor_cap - labor_used)
        if truck_id is None or task is None:
            leftover.extend(_dump_remaining(remaining, board, states, locations, labor_cap - labor_used, reason))
            break
        placed = _place(task, states[truck_id], board.floor, locations)
        legs.append(placed)
        labor_used += placed.duration_min
        remaining = [item for item in remaining if item.id != task.id]

    return WeaveResult(
        floor=board.floor,
        strategy=board.strategy,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        legs=legs,
        leftover=leftover,
    )


def _hard_reason(task: TaskSpec, board: Board, locations: dict[str, Location]) -> str | None:
    if task.ready_min >= board.floor.shift_end_min:
        return "too-late"
    pickup = locations[task.origin]
    drop = locations[task.dest]
    if task.height_mm > pickup.max_height_mm or task.height_mm > drop.max_height_mm:
        return "too-tall"
    trucks = board.floor.trucks
    if not any(_can_kind(truck, pickup, drop) for truck in trucks):
        return "equipment"
    if not any(truck.accepts_temp(task.temp) for truck in trucks):
        return "temp"
    if not any(task.height_mm <= truck.mast_mm for truck in trucks if _can_kind(truck, pickup, drop)):
        return "too-tall"
    if not any(task.weight_kg <= truck.max_weight_kg for truck in trucks):
        return "too-heavy"
    if not any(task.pallets <= truck.pallets for truck in trucks):
        return "cube"
    return None


def _can_kind(truck: Truck, pickup: Location, drop: Location) -> bool:
    return truck.accepts_location(pickup) and truck.accepts_location(drop)


def _truck_reason(
    task: TaskSpec,
    state: _TruckState,
    board: Board,
    pickup: Location,
    drop: Location,
    remaining_labor: int,
) -> str | None:
    truck = state.truck
    if not _can_kind(truck, pickup, drop):
        return "equipment"
    if not truck.accepts_temp(task.temp):
        return "temp"
    if task.height_mm > truck.mast_mm:
        return "too-tall"
    if task.weight_kg > truck.max_weight_kg:
        return "too-heavy"
    if task.pallets > truck.pallets:
        return "cube"
    start, deadhead, loaded, duration = _timing(task, state, board.floor, pickup, drop)
    if start + duration > board.floor.shift_end_min:
        return "shift"
    if duration > remaining_labor:
        return "labor-cap"
    return None


def _timing(
    task: TaskSpec,
    state: _TruckState,
    floor: Floor,
    pickup: Location,
    drop: Location,
) -> tuple[int, int, int, int]:
    deadhead = travel_min(state.location, pickup, state.truck.cells_per_min)
    loaded = travel_min(pickup, drop, state.truck.cells_per_min)
    duration = deadhead + floor.handling_min + loaded + floor.handling_min
    start = max(state.free_at, task.ready_min)
    return start, deadhead, loaded, duration


def _pair_score(
    strategy: str,
    task: TaskSpec,
    state: _TruckState,
    start: int,
    deadhead: int,
    duration: int,
    dual: int,
) -> tuple:
    wait = start - state.free_at
    truck_id = state.truck.id
    if strategy == "dual":
        return (dual, deadhead, start, task.priority, task.ready_min, truck_id, task.id)
    if strategy == "nearest":
        return (deadhead, start, dual, task.priority, truck_id, task.id)
    if strategy == "fifo":
        return (task.ready_min, start, deadhead, truck_id, task.id)
    return (task.priority, deadhead, dual, start, wait, truck_id, task.id)


def _best_pair(
    tasks: list[TaskSpec],
    board: Board,
    states: dict[str, _TruckState],
    locations: dict[str, Location],
    remaining_labor: int,
) -> tuple[str | None, TaskSpec | None, str]:
    candidates: list[tuple[tuple, str, TaskSpec]] = []
    reasons: list[str] = []
    for task in tasks:
        pickup = locations[task.origin]
        drop = locations[task.dest]
        for truck in board.floor.trucks:
            state = states[truck.id]
            reason = _truck_reason(task, state, board, pickup, drop, remaining_labor)
            if reason:
                reasons.append(reason)
                continue
            start, deadhead, _loaded, duration = _timing(task, state, board.floor, pickup, drop)
            dual = 0 if opposite_flow(state.last_kind, task.kind) else 1
            score = _pair_score(board.strategy, task, state, start, deadhead, duration, dual)
            candidates.append((score, truck.id, task))
    if candidates:
        candidates.sort(key=lambda item: item[0])
        _score, truck_id, task = candidates[0]
        return truck_id, task, ""
    for key in REASON_ORDER:
        if key in reasons:
            return None, None, key
    return None, None, "shift"


def _pick_reason(reasons: list[str], fallback: str) -> str:
    for key in REASON_ORDER:
        if key in reasons:
            return key
    return fallback


def _dump_remaining(
    tasks: list[TaskSpec],
    board: Board,
    states: dict[str, _TruckState],
    locations: dict[str, Location],
    remaining_labor: int,
    fallback: str,
) -> list[dict[str, object]]:
    dumped: list[dict[str, object]] = []
    for task in tasks:
        pickup = locations[task.origin]
        drop = locations[task.dest]
        reasons = [
            reason
            for truck in board.floor.trucks
            if (reason := _truck_reason(task, states[truck.id], board, pickup, drop, remaining_labor))
        ]
        dumped.append(_leftover(task, _pick_reason(reasons, fallback)))
    return dumped


def _place(task: TaskSpec, state: _TruckState, floor: Floor, locations: dict[str, Location]) -> Leg:
    pickup = locations[task.origin]
    drop = locations[task.dest]
    start, deadhead, loaded, duration = _timing(task, state, floor, pickup, drop)
    pickup_min = start + deadhead
    drop_min = pickup_min + floor.handling_min + loaded
    end = start + duration
    placed = Leg(
        task_id=task.id,
        truck_id=state.truck.id,
        kind=task.kind,
        origin=state.location.id,
        pickup=task.origin,
        drop=task.dest,
        start_min=start,
        pickup_min=pickup_min,
        drop_min=drop_min,
        end_min=end,
        deadhead_min=deadhead,
        loaded_min=loaded,
        handling_min=floor.handling_min * 2,
        dual=opposite_flow(state.last_kind, task.kind),
        pallets=task.pallets,
        temp=task.temp,
        priority=task.priority,
    )
    state.legs.append(placed)
    state.free_at = end
    state.location = drop
    state.last_kind = task.kind
    return placed


def _leftover(task: TaskSpec, reason: str) -> dict[str, object]:
    row = task.as_dict()
    row["reason"] = reason
    return row
