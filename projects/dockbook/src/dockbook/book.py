"""Assign trailers to dock doors inside appointment windows.

Trailers are sorted by priority, then by how tight the window is. Each one
takes the first feasible slot under the chosen strategy. The search is greedy:
an earlier booking is never unpacked to make a later one fit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import DayPlan, Trailer
from .yards import Door, Yard, format_hhmm


@dataclass(frozen=True)
class Booking:
    trailer: Trailer
    door_id: str
    start_min: int
    end_min: int

    def as_dict(self) -> dict[str, object]:
        data = self.trailer.as_dict()
        data.update(
            {
                "door_id": self.door_id,
                "start": format_hhmm(self.start_min),
                "end": format_hhmm(self.end_min),
                "wait_min": self.start_min - self.trailer.start_min,
            }
        )
        return data


@dataclass
class BookResult:
    yard: Yard
    strategy: str
    bookings: list[Booking]
    leftover: list[dict[str, object]]

    @property
    def all_booked(self) -> bool:
        return not self.leftover

    @property
    def booked_min(self) -> int:
        return sum(item.end_min - item.start_min for item in self.bookings)

    @property
    def door_minutes(self) -> dict[str, int]:
        used = {door.id: 0 for door in self.yard.doors}
        for item in self.bookings:
            used[item.door_id] += item.end_min - item.start_min
        return used

    @property
    def utilization(self) -> float:
        capacity = self.yard.span_min * len(self.yard.doors)
        return self.booked_min / capacity if capacity else 0.0

    def as_dict(self) -> dict[str, object]:
        used = self.door_minutes
        return {
            "yard": self.yard.as_dict(),
            "strategy": self.strategy,
            "bookings": [item.as_dict() for item in sorted(self.bookings, key=_booking_sort)],
            "leftover": self.leftover,
            "booked_count": len(self.bookings),
            "leftover_count": len(self.leftover),
            "all_booked": self.all_booked,
            "booked_min": self.booked_min,
            "utilization": round(self.utilization, 4),
            "doors": [
                {
                    **door.as_dict(),
                    "booked_min": used[door.id],
                    "utilization": round(used[door.id] / self.yard.span_min, 4)
                    if self.yard.span_min
                    else 0.0,
                }
                for door in self.yard.doors
            ],
        }


def book(plan: DayPlan) -> BookResult:
    plan.validate()
    order = sorted(plan.trailers, key=_trailer_sort)
    placed: list[Booking] = []
    leftover: list[dict[str, object]] = []
    for trailer in order:
        choice = _choose_slot(plan.yard, trailer, placed, plan.strategy)
        if choice is None:
            item = trailer.as_dict()
            item["reason"] = _reject_reason(plan.yard, trailer)
            leftover.append(item)
        else:
            placed.append(choice)
    return BookResult(
        yard=plan.yard,
        strategy=plan.strategy,
        bookings=placed,
        leftover=leftover,
    )


def _trailer_sort(trailer: Trailer) -> tuple:
    slack = trailer.end_min - trailer.start_min - trailer.duration_min
    return (trailer.priority, slack, trailer.start_min, trailer.id)


def _booking_sort(item: Booking) -> tuple:
    return (item.door_id, item.start_min, item.trailer.id)


def _choose_slot(
    yard: Yard, trailer: Trailer, placed: list[Booking], strategy: str
) -> Booking | None:
    candidates: list[Booking] = []
    for door in yard.doors:
        start = _earliest_start(yard, door, trailer, placed)
        if start is None:
            continue
        candidates.append(
            Booking(
                trailer=trailer,
                door_id=door.id,
                start_min=start,
                end_min=start + trailer.duration_min,
            )
        )
    if not candidates:
        return None
    if strategy in {"preferred", "auto"} and trailer.prefer_door:
        preferred = [item for item in candidates if item.door_id == trailer.prefer_door]
        if preferred:
            return preferred[0]
        if strategy == "preferred":
            return None
    if strategy == "spread":
        used = {door.id: 0 for door in yard.doors}
        for item in placed:
            used[item.door_id] += item.end_min - item.start_min
        return min(candidates, key=lambda item: (used[item.door_id], item.start_min, item.door_id))
    return min(candidates, key=lambda item: (item.start_min, item.door_id))


def _earliest_start(
    yard: Yard, door: Door, trailer: Trailer, placed: list[Booking]
) -> int | None:
    if not door.accepts(trailer.direction, trailer.temp, trailer.length_m):
        return None
    lo = max(trailer.start_min, yard.open_min)
    hi = min(trailer.end_min, yard.close_min) - trailer.duration_min
    if lo > hi:
        return None
    occupied = [
        (item.start_min, item.end_min + yard.turnaround_min)
        for item in placed
        if item.door_id == door.id
    ]
    occupied.sort()
    cursor = yard.open_min
    gaps: list[tuple[int, int]] = []
    for start, end in occupied:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < yard.close_min:
        gaps.append((cursor, yard.close_min))
    for gap_start, gap_end in gaps:
        start = max(lo, gap_start)
        if start <= hi and start + trailer.duration_min <= gap_end:
            return start
    return None


def _reject_reason(yard: Yard, trailer: Trailer) -> str:
    capable = [
        door
        for door in yard.doors
        if door.accepts(trailer.direction, trailer.temp, trailer.length_m)
    ]
    if not capable:
        if trailer.length_m > max(door.max_length_m for door in yard.doors):
            return (
                f"{trailer.length_m:g} m trailer is longer than every door "
                f"(max {max(door.max_length_m for door in yard.doors):g} m)"
            )
        return (
            f"no door accepts {trailer.direction} / {trailer.temp} "
            f"at {trailer.length_m:g} m"
        )
    if trailer.end_min <= yard.open_min or trailer.start_min >= yard.close_min:
        return (
            f"window {trailer.window_start}–{trailer.window_end} "
            f"is outside yard hours {format_hhmm(yard.open_min)}–{format_hhmm(yard.close_min)}"
        )
    return (
        f"no free slot of {trailer.duration_min} min "
        f"in {trailer.window_start}–{trailer.window_end} "
        f"on a matching door"
    )
