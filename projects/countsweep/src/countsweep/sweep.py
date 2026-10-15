"""Greedy cycle-count walk: due first, labor-capped, aisle travel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .model import Location, Wave
from .policies import NEVER_COUNTED, Policy

ABC_RANK = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class Count:
    seq: int
    location_id: str
    sku: str
    abc: str
    aisle: int
    bay: int
    level: int
    book_qty: int
    counted_qty: int | None
    variance: int | None
    variance_pct: float | None
    flag: bool
    days_since: int | None
    overdue_days: int
    minutes: int
    freeze: bool
    high_shrink: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "location_id": self.location_id,
            "sku": self.sku,
            "abc": self.abc,
            "aisle": self.aisle,
            "bay": self.bay,
            "level": self.level,
            "book_qty": self.book_qty,
            "counted_qty": self.counted_qty,
            "variance": self.variance,
            "variance_pct": None if self.variance_pct is None else round(self.variance_pct, 4),
            "flag": self.flag,
            "days_since": self.days_since,
            "overdue_days": None if self.days_since is None else self.overdue_days,
            "minutes": self.minutes,
            "freeze": self.freeze,
            "high_shrink": self.high_shrink,
        }


@dataclass
class SweepResult:
    policy: Policy
    strategy: str
    as_of: date
    labor_cap_min: int
    labor_used_min: int
    counts: list[Count]
    leftover: list[dict[str, object]]
    locations: list[dict[str, object]]
    due_count: int
    scheduled_count: int
    flag_count: int

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def all_clear(self) -> bool:
        return not self.leftover

    @property
    def cover_rate(self) -> float:
        if self.due_count <= 0:
            return 1.0
        return self.scheduled_count / self.due_count

    @property
    def labor_utilization(self) -> float:
        if self.labor_cap_min <= 0:
            return 0.0
        return self.labor_used_min / self.labor_cap_min

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy.as_dict(),
            "strategy": self.strategy,
            "as_of": self.as_of.isoformat(),
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "counts": [item.as_dict() for item in self.counts],
            "leftover": list(self.leftover),
            "locations": list(self.locations),
            "due_count": self.due_count,
            "scheduled_count": self.scheduled_count,
            "leftover_count": self.leftover_count,
            "flag_count": self.flag_count,
            "cover_rate": self.cover_rate,
            "all_clear": self.all_clear,
        }


def cycle_for(location: Location, policy: Policy) -> int:
    days = policy.cycle_days(location.abc)
    if location.high_shrink:
        return min(days, policy.shrink_cycle_days)
    return days


def days_since(location: Location, as_of: date) -> int | None:
    if location.last_counted is None:
        return None
    return (as_of - location.last_counted).days


def overdue_days(location: Location, policy: Policy, as_of: date) -> int:
    elapsed = days_since(location, as_of)
    if elapsed is None:
        return NEVER_COUNTED
    return elapsed - cycle_for(location, policy)


def is_due(location: Location, policy: Policy, as_of: date) -> bool:
    return overdue_days(location, policy, as_of) >= 0


def variance_of(location: Location, policy: Policy) -> tuple[int | None, float | None, bool]:
    if location.counted_qty is None:
        return None, None, False
    delta = location.counted_qty - location.book_qty
    if location.book_qty == 0:
        pct = 1.0 if location.counted_qty != 0 else 0.0
    else:
        pct = abs(delta) / location.book_qty
    flag = abs(delta) >= policy.variance_units or pct + 1e-12 >= policy.variance_pct
    return delta, pct, flag


def _sort_due(locations: list[Location], strategy: str, policy: Policy, as_of: date) -> list[Location]:
    def key(location: Location) -> tuple:
        overdue = overdue_days(location, policy, as_of)
        abc = ABC_RANK[location.abc]
        shrink = 0 if location.high_shrink else 1
        if strategy == "abc":
            return (abc, -overdue, location.aisle, location.bay, location.level, location.id)
        if strategy == "aisle":
            bay = location.bay if location.aisle % 2 else -location.bay
            return (location.aisle, bay, location.level, location.id)
        if strategy == "shrink":
            return (shrink, -overdue, abc, location.aisle, location.bay, location.level, location.id)
        return (-overdue, abc, location.aisle, location.bay, location.level, location.id)

    return sorted(locations, key=key)


def _travel_minutes(policy: Policy, aisle: int, previous_aisle: int) -> int:
    return policy.minutes_per_count + policy.aisle_change_min * abs(aisle - previous_aisle)


def _leftover_row(location: Location, reason: str, policy: Policy, as_of: date) -> dict[str, object]:
    elapsed = days_since(location, as_of)
    return {
        "id": location.id,
        "sku": location.sku,
        "abc": location.abc,
        "aisle": location.aisle,
        "bay": location.bay,
        "level": location.level,
        "book_qty": location.book_qty,
        "days_since": elapsed,
        "overdue_days": None if elapsed is None else overdue_days(location, policy, as_of),
        "reason": reason,
    }


def _location_row(
    location: Location,
    *,
    status: str,
    seq: int | None,
    reason: str | None,
    flag: bool,
    freeze: bool,
) -> dict[str, object]:
    data = location.as_dict()
    data["status"] = status
    data["seq"] = seq
    data["reason"] = reason
    data["flag"] = flag
    data["freeze"] = freeze
    return data


def sweep(wave: Wave) -> SweepResult:
    wave.validate()
    policy = wave.policy
    as_of = wave.as_of
    leftover: list[dict[str, object]] = []
    due: list[Location] = []
    status: dict[str, str] = {}
    leftover_reason: dict[str, str] = {}

    for location in wave.locations:
        if not is_due(location, policy, as_of):
            status[location.id] = "blocked" if location.blocked else "ok"
            continue
        if location.blocked:
            leftover.append(_leftover_row(location, "blocked", policy, as_of))
            leftover_reason[location.id] = "blocked"
            status[location.id] = "blocked"
            continue
        if policy.skip_empty and location.book_qty == 0:
            leftover.append(_leftover_row(location, "skip-empty", policy, as_of))
            leftover_reason[location.id] = "skip-empty"
            status[location.id] = "leftover"
            continue
        due.append(location)
        status[location.id] = "due"

    counts: list[Count] = []
    labor_cap = wave.labor_cap()
    labor_used = 0
    previous_aisle = 0
    scheduled_ids: set[str] = set()
    flags = 0

    for location in _sort_due(due, wave.strategy, policy, as_of):
        minutes = _travel_minutes(policy, location.aisle, previous_aisle)
        if labor_used + minutes > labor_cap:
            leftover.append(_leftover_row(location, "labor-cap", policy, as_of))
            leftover_reason[location.id] = "labor-cap"
            status[location.id] = "leftover"
            continue
        labor_used += minutes
        previous_aisle = location.aisle
        delta, pct, flag = variance_of(location, policy)
        if flag:
            flags += 1
        freeze = policy.freeze_on_count
        seq = len(counts) + 1
        counts.append(
            Count(
                seq=seq,
                location_id=location.id,
                sku=location.sku,
                abc=location.abc,
                aisle=location.aisle,
                bay=location.bay,
                level=location.level,
                book_qty=location.book_qty,
                counted_qty=location.counted_qty,
                variance=delta,
                variance_pct=pct,
                flag=flag,
                days_since=days_since(location, as_of),
                overdue_days=overdue_days(location, policy, as_of),
                minutes=minutes,
                freeze=freeze,
                high_shrink=location.high_shrink,
            )
        )
        scheduled_ids.add(location.id)
        status[location.id] = "scheduled"

    locations = []
    for location in wave.locations:
        loc_status = status[location.id]
        seq = next((item.seq for item in counts if item.location_id == location.id), None)
        flag = next((item.flag for item in counts if item.location_id == location.id), False)
        freeze = next((item.freeze for item in counts if item.location_id == location.id), False)
        locations.append(
            _location_row(
                location,
                status=loc_status,
                seq=seq,
                reason=leftover_reason.get(location.id),
                flag=flag,
                freeze=freeze,
            )
        )

    due_count = len(due) + sum(1 for row in leftover if row["reason"] in {"blocked", "skip-empty"})
    return SweepResult(
        policy=policy,
        strategy=wave.strategy,
        as_of=as_of,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        counts=counts,
        leftover=leftover,
        locations=locations,
        due_count=due_count,
        scheduled_count=len(counts),
        flag_count=flags,
    )
