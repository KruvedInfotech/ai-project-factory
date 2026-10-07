"""Greedy yard parking and pull-to-door sequencer."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Trailer, YardPlan
from .yards import Spot, Yard, clock_to_min, min_to_clock


@dataclass(frozen=True)
class Parked:
    trailer_id: str
    spot_id: str
    row: str
    bay: int
    kind: str
    temp: str
    door: str
    spot_door: str
    spot_kind: str
    available: str
    length_ft: int
    dwell_h: float
    appointment: str
    priority: int
    needs_power: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "trailer_id": self.trailer_id,
            "spot_id": self.spot_id,
            "row": self.row,
            "bay": self.bay,
            "kind": self.kind,
            "temp": self.temp,
            "door": self.door,
            "spot_door": self.spot_door,
            "spot_kind": self.spot_kind,
            "available": self.available,
            "length_ft": self.length_ft,
            "dwell_h": self.dwell_h,
            "appointment": self.appointment,
            "priority": self.priority,
            "needs_power": self.needs_power,
        }


@dataclass(frozen=True)
class Pull:
    trailer_id: str
    spot_id: str
    door: str
    start: str
    ready: str
    labor_min: int
    walk_min: int
    row: str

    def as_dict(self) -> dict[str, object]:
        return {
            "trailer_id": self.trailer_id,
            "spot_id": self.spot_id,
            "door": self.door,
            "start": self.start,
            "ready": self.ready,
            "labor_min": self.labor_min,
            "walk_min": self.walk_min,
            "row": self.row,
        }


@dataclass
class YardResult:
    yard: Yard
    strategy: str
    parked: list[Parked]
    pulls: list[Pull]
    leftover: list[dict[str, object]]
    held: list[dict[str, object]]
    labor_min: int

    @property
    def all_clear(self) -> bool:
        return not self.leftover

    @property
    def parked_count(self) -> int:
        return len(self.parked)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def pull_count(self) -> int:
        return len(self.pulls)

    @property
    def fill_rate(self) -> float:
        if not self.yard.spots:
            return 0.0
        return self.parked_count / len(self.yard.spots)

    def as_dict(self) -> dict[str, object]:
        return {
            "yard": self.yard.as_dict(),
            "strategy": self.strategy,
            "parked": [item.as_dict() for item in self.parked],
            "pulls": [item.as_dict() for item in self.pulls],
            "leftover": list(self.leftover),
            "held": list(self.held),
            "labor_min": self.labor_min,
            "parked_count": self.parked_count,
            "leftover_count": self.leftover_count,
            "pull_count": self.pull_count,
            "fill_rate": self.fill_rate,
            "all_clear": self.all_clear,
        }


def _compat_reason(trailer: Trailer, spot: Spot) -> str | None:
    if trailer.length_ft > spot.max_ft:
        return "too-long"
    if trailer.temp == "reefer" and spot.kind not in {"reefer", "power"}:
        return "no-reefer"
    if trailer.needs_power and spot.kind not in {"power", "reefer"}:
        return "no-power"
    return None


def _spot_score(trailer: Trailer, spot: Spot) -> tuple[int, int, str]:
    score = 0
    if trailer.door and spot.door == trailer.door:
        score += 100
    if trailer.kind == "outbound":
        score += 20
    score -= spot.walk_min
    if trailer.temp == "dry" and not trailer.needs_power:
        if spot.kind == "power":
            score -= 50
        elif spot.kind == "reefer":
            score -= 30
    return (-score, spot.walk_min, spot.id)


def _leftover_reason(trailer: Trailer, spots: tuple[Spot, ...]) -> str:
    if any(_compat_reason(trailer, spot) is None for spot in spots):
        return "no-spot"
    reasons = {_compat_reason(trailer, spot) for spot in spots}
    reasons.discard(None)
    if trailer.temp == "reefer" and "no-reefer" in reasons:
        return "no-reefer"
    if trailer.needs_power and "no-power" in reasons:
        return "no-power"
    if "too-long" in reasons:
        return "too-long"
    return "no-spot"


def _sort_trailers(trailers: list[Trailer], strategy: str) -> list[Trailer]:
    def key(trailer: Trailer) -> tuple:
        appointment = clock_to_min(trailer.appointment) if trailer.appointment else 10**6
        eta = clock_to_min(trailer.eta)
        if strategy == "dwell":
            return (-trailer.dwell_h, trailer.priority, eta, trailer.id)
        if strategy == "door":
            return (0 if trailer.door else 1, appointment, trailer.priority, trailer.id)
        if strategy == "pull":
            pullable = 0 if trailer.kind == "outbound" and trailer.appointment else 1
            return (pullable, appointment, trailer.priority, trailer.id)
        return (trailer.priority, appointment, -trailer.dwell_h, eta, trailer.id)

    return sorted(trailers, key=key)


def _available_min(trailer: Trailer, yard: Yard) -> int:
    return max(clock_to_min(trailer.eta), yard.open_min)


def _should_pull(trailer: Trailer) -> bool:
    return bool(trailer.door and trailer.appointment and trailer.kind != "empty")


def _pick_spot(trailer: Trailer, free: list[Spot]) -> Spot | None:
    candidates = [spot for spot in free if _compat_reason(trailer, spot) is None]
    if not candidates:
        return None
    return min(candidates, key=lambda spot: _spot_score(trailer, spot))


def park(plan: YardPlan) -> YardResult:
    yard = plan.yard
    parked: list[Parked] = []
    leftover: list[dict[str, object]] = []
    free = list(yard.spots)
    parked_by_id: dict[str, tuple[Trailer, Parked, Spot]] = {}

    for trailer in _sort_trailers(plan.trailers, plan.strategy):
        if clock_to_min(trailer.eta) >= yard.close_min:
            leftover.append({**trailer.as_dict(), "reason": "closed"})
            continue
        chosen = _pick_spot(trailer, free)
        if chosen is None:
            leftover.append({**trailer.as_dict(), "reason": _leftover_reason(trailer, yard.spots)})
            continue
        free.remove(chosen)
        assignment = Parked(
            trailer_id=trailer.id,
            spot_id=chosen.id,
            row=chosen.row,
            bay=chosen.bay,
            kind=trailer.kind,
            temp=trailer.temp,
            door=trailer.door,
            spot_door=chosen.door,
            spot_kind=chosen.kind,
            available=min_to_clock(_available_min(trailer, yard)),
            length_ft=trailer.length_ft,
            dwell_h=trailer.dwell_h,
            appointment=trailer.appointment,
            priority=trailer.priority,
            needs_power=trailer.needs_power,
        )
        parked.append(assignment)
        parked_by_id[trailer.id] = (trailer, assignment, chosen)

    pulls: list[Pull] = []
    held: list[dict[str, object]] = []
    labor = 0
    last_end = yard.open_min
    last_row: str | None = None

    pull_queue = [
        parked_by_id[item.trailer_id]
        for item in parked
        if _should_pull(parked_by_id[item.trailer_id][0])
    ]
    pull_queue.sort(
        key=lambda row: (
            clock_to_min(row[0].appointment),
            row[0].priority,
            row[0].id,
        )
    )

    for trailer, assignment, spot in pull_queue:
        duration = yard.minutes_per_move + spot.walk_min
        if last_row is not None and last_row != spot.row:
            duration += yard.row_change_min
        if len(pulls) >= yard.max_moves or labor + duration > yard.max_labor_min:
            held.append({**trailer.as_dict(), "spot_id": spot.id, "reason": "capped"})
            continue
        start = max(_available_min(trailer, yard), last_end, yard.open_min)
        window = clock_to_min(trailer.appointment) - yard.pull_lead_min
        start = max(start, window)
        ready = start + duration
        if ready > yard.close_min or ready > clock_to_min(trailer.appointment):
            held.append({**trailer.as_dict(), "spot_id": spot.id, "reason": "late"})
            continue
        pulls.append(
            Pull(
                trailer_id=trailer.id,
                spot_id=spot.id,
                door=trailer.door,
                start=min_to_clock(start),
                ready=min_to_clock(ready),
                labor_min=duration,
                walk_min=spot.walk_min,
                row=spot.row,
            )
        )
        labor += duration
        last_end = ready
        last_row = spot.row

    pulled_ids = {item.trailer_id for item in pulls}
    held_ids = {str(item["id"]) for item in held}
    for trailer, assignment, spot in parked_by_id.values():
        if trailer.id in pulled_ids or trailer.id in held_ids:
            continue
        reason = "idle" if not _should_pull(trailer) else "held"
        held.append({**trailer.as_dict(), "spot_id": spot.id, "reason": reason})

    parked.sort(key=lambda item: (item.row, item.bay, item.trailer_id))
    return YardResult(
        yard=yard,
        strategy=plan.strategy,
        parked=parked,
        pulls=pulls,
        leftover=leftover,
        held=held,
        labor_min=labor,
    )
