"""Greedy seater: pin an associate to an hour, never unseat an earlier hour."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Associate, Board, DemandSlot
from .sites import Site, hour_in_span

REASON_ORDER = (
    "skill",
    "cert",
    "temp",
    "window",
    "break",
    "ot-cap",
    "head-cap",
    "labor-cap",
    "no-body",
)

OT_MULTIPLIER = 1.5


@dataclass(frozen=True)
class Ticket:
    hour: int
    skill: str
    temp: str
    equipment: str
    priority: int
    seq: int


@dataclass(frozen=True)
class Seat:
    associate_id: str
    name: str
    kind: str
    hour: int
    skill: str
    temp: str
    ot: bool
    cost: float
    equipment: str = ""

    def as_dict(self) -> dict[str, object]:
        row: dict[str, object] = {
            "associate_id": self.associate_id,
            "name": self.name,
            "kind": self.kind,
            "hour": self.hour,
            "skill": self.skill,
            "temp": self.temp,
            "ot": self.ot,
            "cost": self.cost,
        }
        if self.equipment:
            row["equipment"] = self.equipment
        return row


@dataclass
class _Person:
    assoc: Associate
    hours: dict[int, Seat] = field(default_factory=dict)
    cost: float = 0.0


@dataclass
class StaffResult:
    site: Site
    strategy: str
    labor_cap: float
    labor_used: float
    head_cap: int
    demand: list[DemandSlot]
    seats: list[Seat]
    leftover: list[dict[str, object]]
    crew: list[Associate]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def seated_count(self) -> int:
        return len(self.seats)

    @property
    def leftover_heads(self) -> int:
        return sum(int(item["heads"]) for item in self.leftover)

    @property
    def demand_heads(self) -> int:
        return sum(slot.heads for slot in self.demand)

    @property
    def fill_ratio(self) -> float:
        return self.seated_count / self.demand_heads if self.demand_heads else 0.0

    @property
    def punched_count(self) -> int:
        return len({seat.associate_id for seat in self.seats})

    @property
    def ot_count(self) -> int:
        return sum(1 for seat in self.seats if seat.ot)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used / self.labor_cap if self.labor_cap else 0.0

    def coverage(self) -> list[dict[str, object]]:
        hours = list(self.site.hours)
        seen = set(hours)
        extras = []
        for slot in self.demand:
            if slot.hour not in seen:
                extras.append(slot.hour)
                seen.add(slot.hour)
        extras.sort(key=self.site.hour_index)
        rows = []
        for hour in hours + extras:
            need = sum(slot.heads for slot in self.demand if slot.hour == hour)
            got = sum(1 for seat in self.seats if seat.hour == hour)
            rows.append({"hour": hour, "demand": need, "seated": got, "short": max(0, need - got)})
        return rows

    def roster(self) -> list[dict[str, object]]:
        by_id = {person.id: person for person in self.crew}
        rows = []
        punched = {seat.associate_id for seat in self.seats}
        order = [person.id for person in self.crew if person.id in punched]
        order.extend(person.id for person in self.crew if person.id not in punched)
        for ident in order:
            person = by_id[ident]
            assigned = [seat for seat in self.seats if seat.associate_id == ident]
            assigned.sort(key=lambda seat: self.site.hour_index(seat.hour))
            rows.append(
                {
                    "id": person.id,
                    "name": person.name,
                    "kind": person.kind,
                    "temp": person.temp,
                    "skills": list(person.skills),
                    "hours": [seat.hour for seat in assigned],
                    "ot_hours": [seat.hour for seat in assigned if seat.ot],
                    "cost": round(sum(seat.cost for seat in assigned), 2),
                    "seats": [seat.as_dict() for seat in assigned],
                }
            )
        return rows

    def as_dict(self) -> dict[str, object]:
        return {
            "site": self.site.as_dict(),
            "strategy": self.strategy,
            "labor_cap": self.labor_cap,
            "labor_used": round(self.labor_used, 2),
            "labor_utilization": round(self.labor_utilization, 4),
            "head_cap": self.head_cap,
            "punched_count": self.punched_count,
            "seated_count": self.seated_count,
            "demand_heads": self.demand_heads,
            "leftover_heads": self.leftover_heads,
            "fill_ratio": round(self.fill_ratio, 4),
            "ot_count": self.ot_count,
            "all_fit": self.all_fit,
            "seats": [seat.as_dict() for seat in self.seats],
            "leftover": list(self.leftover),
            "coverage": self.coverage(),
            "roster": self.roster(),
        }


def hour_cost(assoc: Associate, hour: int) -> float:
    if hour_in_span(hour, assoc.available_start, assoc.available_end):
        return round(assoc.rate_per_hour, 2)
    return round(assoc.rate_per_hour * OT_MULTIPLIER, 2)


def is_ot(assoc: Associate, hour: int) -> bool:
    return not hour_in_span(hour, assoc.available_start, assoc.available_end)


def consecutive_before(hours: set[int], hour: int) -> int:
    n = 0
    cursor = (hour - 1) % 24
    for _ in range(24):
        if cursor not in hours:
            break
        n += 1
        cursor = (cursor - 1) % 24
    return n


def staff(board: Board) -> StaffResult:
    board.validate()
    labor_cap = board.labor_cap()
    labor_used = 0.0
    seats: list[Seat] = []
    leftover_tickets: list[tuple[Ticket, str]] = []
    people = [_Person(person) for person in board.crew]

    for ticket in _expand(board):
        chosen, reason = _best_person(ticket, board, people, labor_cap - labor_used)
        if chosen is None:
            leftover_tickets.append((ticket, reason))
            continue
        cost = hour_cost(chosen.assoc, ticket.hour)
        seat = Seat(
            associate_id=chosen.assoc.id,
            name=chosen.assoc.name,
            kind=chosen.assoc.kind,
            hour=ticket.hour,
            skill=ticket.skill,
            temp=ticket.temp,
            ot=is_ot(chosen.assoc, ticket.hour),
            cost=cost,
            equipment=ticket.equipment,
        )
        chosen.hours[ticket.hour] = seat
        chosen.cost += cost
        labor_used += cost
        seats.append(seat)

    return StaffResult(
        site=board.site,
        strategy=board.strategy,
        labor_cap=labor_cap,
        labor_used=round(labor_used, 2),
        head_cap=board.heads_cap(),
        demand=list(board.demand),
        seats=seats,
        leftover=_merge_leftover(leftover_tickets),
        crew=list(board.crew),
    )


def _expand(board: Board) -> list[Ticket]:
    tickets: list[Ticket] = []
    seq = 0
    for slot in board.demand:
        for _ in range(slot.heads):
            tickets.append(
                Ticket(
                    hour=slot.hour,
                    skill=slot.skill,
                    temp=slot.temp,
                    equipment=slot.equipment,
                    priority=slot.priority,
                    seq=seq,
                )
            )
            seq += 1
    tickets.sort(key=lambda item: (item.priority, board.site.hour_index(item.hour), item.skill, item.temp, item.seq))
    return tickets


def _best_person(
    ticket: Ticket,
    board: Board,
    people: list[_Person],
    remaining: float,
) -> tuple[_Person | None, str]:
    eligible: list[_Person] = []
    reasons: list[str] = []
    punched = sum(1 for person in people if person.hours)
    for person in people:
        if ticket.hour in person.hours:
            continue
        why = _reason(person, ticket, board, remaining, punched)
        if why is None:
            eligible.append(person)
        else:
            reasons.append(why)
    if not eligible:
        return None, _closest_reason(reasons)
    eligible.sort(key=lambda person: _score(person, ticket, board))
    return eligible[0], ""


def _reason(
    person: _Person,
    ticket: Ticket,
    board: Board,
    remaining: float,
    punched: int,
) -> str | None:
    assoc = person.assoc
    if ticket.skill not in assoc.skills:
        return "skill"
    if ticket.skill == "forklift" and ticket.equipment and ticket.equipment not in assoc.certs:
        return "cert"
    if assoc.temp != "mixed" and assoc.temp != ticket.temp:
        return "temp"
    if is_ot(assoc, ticket.hour):
        used_ot = sum(1 for hour in person.hours if is_ot(assoc, hour))
        if assoc.ot_cap_hours <= 0:
            return "window"
        if used_ot >= assoc.ot_cap_hours:
            return "ot-cap"
    if consecutive_before(set(person.hours), ticket.hour) >= board.site.break_after:
        return "break"
    if not person.hours and punched >= board.heads_cap():
        return "head-cap"
    cost = hour_cost(assoc, ticket.hour)
    if cost - remaining > 1e-9:
        return "labor-cap"
    return None


def _closest_reason(reasons: list[str]) -> str:
    if not reasons:
        return "no-body"
    return max(reasons, key=lambda reason: REASON_ORDER.index(reason) if reason in REASON_ORDER else -1)


def _score(person: _Person, ticket: Ticket, board: Board) -> tuple:
    assoc = person.assoc
    prev = (ticket.hour - 1) % 24
    if prev in person.hours:
        continuity = 0
    elif person.hours:
        continuity = 1
    else:
        continuity = 2
    overtime = 1 if is_ot(assoc, ticket.hour) else 0
    kind = 0 if assoc.kind == "regular" else 1
    flex = len(assoc.skills)
    cost = hour_cost(assoc, ticket.hour)
    ident = assoc.id
    if board.strategy == "regular":
        return (kind, overtime, continuity, cost, flex, ident)
    if board.strategy == "temp":
        return (1 - kind, continuity, overtime, cost, flex, ident)
    if board.strategy == "overtime":
        return (continuity, kind, cost, flex, ident)
    return (overtime, continuity, kind, flex, cost, ident)


def _merge_leftover(items: list[tuple[Ticket, str]]) -> list[dict[str, object]]:
    merged: dict[tuple, dict[str, object]] = {}
    order: list[tuple] = []
    for ticket, reason in items:
        key = (ticket.hour, ticket.skill, ticket.temp, ticket.equipment, reason)
        if key not in merged:
            row: dict[str, object] = {
                "hour": ticket.hour,
                "skill": ticket.skill,
                "temp": ticket.temp,
                "heads": 0,
                "reason": reason,
            }
            if ticket.equipment:
                row["equipment"] = ticket.equipment
            merged[key] = row
            order.append(key)
        merged[key]["heads"] = int(merged[key]["heads"]) + 1
    return [merged[key] for key in order]
