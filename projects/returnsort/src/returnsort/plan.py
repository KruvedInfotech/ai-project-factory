"""Greedy returns-dock planner.

Each physical unit gets a disposition, then the first legal lane that
still has a slot. Labor minutes are spent as units are parked; leftovers
keep a reason so the dock can decide what waits.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .floors import Floor, Lane
from .model import ReturnBatch, ReturnUnit

DISP_ORDER = {"hold": 0, "rma": 1, "restock": 2, "refurb": 3, "scrap": 4}
VEL_ORDER = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class Assignment:
    ticket: str
    sku: str
    index: int
    disposition: str
    lane_id: str
    slot: int
    minutes: int
    temp: str
    velocity: str

    def as_dict(self) -> dict[str, object]:
        return {
            "ticket": self.ticket,
            "sku": self.sku,
            "index": self.index,
            "disposition": self.disposition,
            "lane_id": self.lane_id,
            "slot": self.slot,
            "minutes": self.minutes,
            "temp": self.temp,
            "velocity": self.velocity,
        }


@dataclass
class PlanResult:
    floor: Floor
    assignments: list[Assignment]
    leftover: list[dict[str, object]]
    labor_used: int
    labor_cap: int

    @property
    def all_parked(self) -> bool:
        return not self.leftover

    @property
    def assigned_count(self) -> int:
        return len(self.assignments)

    @property
    def leftover_count(self) -> int:
        return sum(int(item["quantity"]) for item in self.leftover)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used / self.labor_cap if self.labor_cap else 0.0

    def disposition_counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for item in self.assignments:
            counts[item.disposition] += 1
        return dict(counts)

    def as_dict(self) -> dict[str, object]:
        return {
            "floor": self.floor.as_dict(),
            "all_parked": self.all_parked,
            "assigned_count": self.assigned_count,
            "leftover_count": self.leftover_count,
            "labor_used": self.labor_used,
            "labor_cap": self.labor_cap,
            "labor_utilization": round(self.labor_utilization, 4),
            "disposition_counts": self.disposition_counts(),
            "assignments": [item.as_dict() for item in self.assignments],
            "leftover": self.leftover,
        }


def plan(batch: ReturnBatch) -> PlanResult:
    batch.validate()
    pieces = sorted(batch.expand(), key=_unit_key)
    occupancy: dict[str, list[ReturnUnit]] = {lane.id: [] for lane in batch.floor.lanes}
    assignments: list[Assignment] = []
    leftover_pieces: list[tuple[ReturnUnit, str]] = []
    labor = 0

    for piece in pieces:
        cost = piece.labor_minutes()
        if labor + cost > batch.labor_minutes:
            leftover_pieces.append((piece, "labor cap"))
            continue
        lane = _choose_lane(piece, batch.floor, occupancy)
        if lane is None:
            leftover_pieces.append((piece, _leftover_reason(piece, batch.floor, occupancy)))
            continue
        slot = len(occupancy[lane.id])
        occupancy[lane.id].append(piece)
        labor += cost
        assignments.append(
            Assignment(
                ticket=piece.ticket,
                sku=piece.sku,
                index=len(assignments),
                disposition=piece.disposition,
                lane_id=lane.id,
                slot=slot,
                minutes=cost,
                temp=piece.temp,
                velocity=piece.velocity,
            )
        )

    return PlanResult(
        floor=batch.floor,
        assignments=assignments,
        leftover=_group_leftover(leftover_pieces),
        labor_used=labor,
        labor_cap=batch.labor_minutes,
    )


def _unit_key(unit: ReturnUnit) -> tuple:
    life = unit.remaining_life_days if unit.remaining_life_days is not None else 10**9
    return (
        DISP_ORDER[unit.disposition],
        life,
        VEL_ORDER.get(unit.velocity, 1),
        unit.ticket,
        unit.sku,
    )


def _choose_lane(unit: ReturnUnit, floor: Floor, occupancy: dict[str, list[ReturnUnit]]) -> Lane | None:
    candidates = [
        lane
        for lane in floor.lanes
        if lane.accepts(unit.disposition, unit.temp) and len(occupancy[lane.id]) < lane.slots
    ]
    if not candidates:
        return None
    preferred_zone = _preferred_zone(unit)
    return min(candidates, key=lambda lane: _lane_key(lane, unit, occupancy, preferred_zone))


def _preferred_zone(unit: ReturnUnit) -> str | None:
    if unit.disposition != "restock":
        return None
    if unit.velocity == "C":
        return "reserve"
    return "pick_face"


def _lane_key(
    lane: Lane,
    unit: ReturnUnit,
    occupancy: dict[str, list[ReturnUnit]],
    preferred_zone: str | None,
) -> tuple:
    same = sum(1 for parked in occupancy[lane.id] if parked.sku == unit.sku)
    remaining = lane.slots - len(occupancy[lane.id])
    door_rank = 0 if unit.disposition == "rma" and lane.door_adjacent else 1
    zone_rank = 0 if preferred_zone and lane.zone == preferred_zone else 1
    return (door_rank, zone_rank, -same, -remaining, lane.id)


def _leftover_reason(unit: ReturnUnit, floor: Floor, occupancy: dict[str, list[ReturnUnit]]) -> str:
    matching = [lane for lane in floor.lanes if lane.accepts(unit.disposition, unit.temp)]
    if not matching:
        return "no matching lane"
    if all(len(occupancy[lane.id]) >= lane.slots for lane in matching):
        return "lanes full"
    return "no matching lane"


def _group_leftover(pieces: list[tuple[ReturnUnit, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple, dict[str, object]] = {}
    for unit, reason in pieces:
        key = (unit.ticket, unit.sku, unit.disposition, reason)
        if key not in grouped:
            grouped[key] = {
                "ticket": unit.ticket,
                "sku": unit.sku,
                "disposition": unit.disposition,
                "temp": unit.temp,
                "quantity": 0,
                "reason": reason,
            }
        grouped[key]["quantity"] = int(grouped[key]["quantity"]) + 1
    return list(grouped.values())
