"""Greedy honeycomb consolidator.

Partials of the same SKU + lot + temperature fold into fuller locations.
Reserve empties first. The last pick-face of a SKU stays put. Each
donor→sink trip spends labor minutes; leftovers keep a reason so the
floor can decide what waits.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import FoldPlan, Location
from .warehouse import Warehouse


@dataclass(frozen=True)
class Move:
    sku: str
    lot: str
    qty: int
    from_id: str
    to_id: str
    minutes: int
    from_aisle: str
    to_aisle: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "lot": self.lot,
            "qty": self.qty,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "minutes": self.minutes,
            "from_aisle": self.from_aisle,
            "to_aisle": self.to_aisle,
        }


@dataclass
class FoldResult:
    warehouse: Warehouse
    locations: list[dict[str, object]]
    moves: list[Move]
    freed: list[dict[str, object]]
    leftover: list[dict[str, object]]
    labor_used: int
    labor_cap: int
    units_moved: int

    @property
    def all_folded(self) -> bool:
        return not self.leftover

    @property
    def move_count(self) -> int:
        return len(self.moves)

    @property
    def freed_count(self) -> int:
        return len(self.freed)

    @property
    def leftover_count(self) -> int:
        return sum(int(item["qty"]) for item in self.leftover)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used / self.labor_cap if self.labor_cap else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "warehouse": self.warehouse.as_dict(),
            "all_folded": self.all_folded,
            "move_count": self.move_count,
            "units_moved": self.units_moved,
            "freed_count": self.freed_count,
            "leftover_count": self.leftover_count,
            "labor_used": self.labor_used,
            "labor_cap": self.labor_cap,
            "labor_utilization": round(self.labor_utilization, 4),
            "moves": [move.as_dict() for move in self.moves],
            "freed": self.freed,
            "leftover": self.leftover,
            "locations": self.locations,
        }


def fold(plan: FoldPlan) -> FoldResult:
    plan.validate()
    qty = {loc.id: loc.qty for loc in plan.locations}
    by_id = {loc.id: loc for loc in plan.locations}
    families: dict[tuple[str, str, str], list[Location]] = defaultdict(list)
    for loc in plan.locations:
        families[loc.family].append(loc)

    moves: list[Move] = []
    blocked: dict[str, str] = {}

    for family_key in sorted(families):
        members = families[family_key]
        labor = sum(move.minutes for move in moves)
        if labor + plan.minutes_per_move > plan.labor_minutes:
            _mark_labor_blocked(plan, members, qty, blocked)
            continue
        _fold_family(plan, members, qty, moves, blocked)
        labor = sum(move.minutes for move in moves)
        if labor + plan.minutes_per_move > plan.labor_minutes:
            _mark_labor_blocked(plan, members, qty, blocked)

    leftover = _leftovers(plan, families, qty, blocked)
    freed = [
        {
            "id": loc.id,
            "sku": loc.sku,
            "lot": loc.lot,
            "aisle": loc.aisle,
            "bay": loc.bay,
            "level": loc.level,
            "kind": loc.kind,
        }
        for loc in plan.locations
        if loc.qty > 0 and qty[loc.id] == 0
    ]
    after = [_location_state(by_id[loc_id], qty[loc_id]) for loc_id in sorted(by_id)]
    return FoldResult(
        warehouse=plan.warehouse,
        locations=after,
        moves=moves,
        freed=freed,
        leftover=leftover,
        labor_used=sum(move.minutes for move in moves),
        labor_cap=plan.labor_minutes,
        units_moved=sum(move.qty for move in moves),
    )


def _fold_family(
    plan: FoldPlan,
    members: list[Location],
    qty: dict[str, int],
    moves: list[Move],
    blocked: dict[str, str],
) -> None:
    keepers: set[str] = set()
    progressed = True
    while progressed:
        progressed = False
        labor = sum(move.minutes for move in moves)
        if labor + plan.minutes_per_move > plan.labor_minutes:
            return
        donors = [
            loc
            for loc in members
            if _is_donor_candidate(plan, loc, members, qty, keepers) and qty[loc.id] > 0
        ]
        donors.sort(key=lambda loc: _donor_key(loc, qty))
        for donor in donors:
            labor = sum(move.minutes for move in moves)
            if labor + plan.minutes_per_move > plan.labor_minutes:
                blocked.setdefault(donor.id, "labor cap")
                return
            sink = _choose_sink(donor, members, qty, keepers)
            if sink is None:
                blocked.setdefault(donor.id, _donor_block_reason(donor, members, qty))
                continue
            take = min(qty[donor.id], sink.remaining_capacity(qty[sink.id]))
            if take <= 0:
                blocked.setdefault(donor.id, "no sink capacity")
                continue
            qty[donor.id] -= take
            qty[sink.id] += take
            keepers.add(sink.id)
            moves.append(
                Move(
                    sku=donor.sku,
                    lot=donor.lot,
                    qty=take,
                    from_id=donor.id,
                    to_id=sink.id,
                    minutes=plan.minutes_per_move,
                    from_aisle=donor.aisle,
                    to_aisle=sink.aisle,
                )
            )
            progressed = True
            break


def _is_donor_candidate(
    plan: FoldPlan,
    loc: Location,
    members: list[Location],
    qty: dict[str, int],
    keepers: set[str] | None = None,
) -> bool:
    keepers = keepers or set()
    if loc.locked or loc.hold or loc.id in keepers:
        return False
    if qty[loc.id] <= 0:
        return False
    if _protect_pick_face(plan, loc, members, qty):
        return False
    return any(
        other.id != loc.id
        and qty[other.id] > 0
        and not other.locked
        and not other.hold
        and _is_better_keeper(other, loc, qty)
        for other in members
    )


def _protect_pick_face(plan: FoldPlan, loc: Location, members: list[Location], qty: dict[str, int]) -> bool:
    if not plan.keep_last_pick_face or loc.kind != "pick":
        return False
    live_picks = [other for other in members if other.kind == "pick" and qty[other.id] > 0]
    return len(live_picks) <= 1


def _is_better_keeper(candidate: Location, donor: Location, qty: dict[str, int]) -> bool:
    """True when candidate should keep product and donor should empty toward it."""
    return _keeper_key(candidate, qty) < _keeper_key(donor, qty)


def _keeper_key(loc: Location, qty: dict[str, int]) -> tuple:
    fill = qty[loc.id] / loc.max_qty if loc.max_qty else 0.0
    kind_rank = 0 if loc.kind == "pick" else 1
    return (kind_rank, -fill, loc.id)


def _donor_key(loc: Location, qty: dict[str, int]) -> tuple:
    fill = qty[loc.id] / loc.max_qty if loc.max_qty else 0.0
    kind_rank = 0 if loc.kind == "reserve" else 1
    return (kind_rank, fill, qty[loc.id], loc.id)


def _choose_sink(
    donor: Location,
    members: list[Location],
    qty: dict[str, int],
    keepers: set[str],
) -> Location | None:
    candidates = []
    for loc in members:
        if loc.id == donor.id:
            continue
        if loc.locked or loc.hold:
            continue
        if qty[loc.id] <= 0:
            continue
        if loc.remaining_capacity(qty[loc.id]) <= 0:
            continue
        if not _is_better_keeper(loc, donor, qty) and loc.id not in keepers:
            continue
        candidates.append(loc)
    if not candidates:
        return None
    return min(candidates, key=lambda loc: _sink_key(loc, donor, qty))


def _sink_key(loc: Location, donor: Location, qty: dict[str, int]) -> tuple:
    fill = qty[loc.id] / loc.max_qty if loc.max_qty else 0.0
    same_aisle = 0 if loc.aisle == donor.aisle else 1
    return (same_aisle, abs(loc.bay - donor.bay), abs(loc.level - donor.level), -fill, loc.id)


def _mark_labor_blocked(
    plan: FoldPlan,
    members: list[Location],
    qty: dict[str, int],
    blocked: dict[str, str],
) -> None:
    for loc in members:
        if _is_donor_candidate(plan, loc, members, qty) and qty[loc.id] > 0:
            blocked.setdefault(loc.id, "labor cap")


def _donor_block_reason(
    donor: Location,
    members: list[Location],
    qty: dict[str, int],
) -> str:
    open_sinks = [
        loc
        for loc in members
        if loc.id != donor.id
        and not loc.locked
        and not loc.hold
        and qty[loc.id] > 0
        and loc.remaining_capacity(qty[loc.id]) > 0
    ]
    return "no sink capacity" if not open_sinks else "labor cap"


def _leftovers(
    plan: FoldPlan,
    families: dict[tuple[str, str, str], list[Location]],
    qty: dict[str, int],
    blocked: dict[str, str],
) -> list[dict[str, object]]:
    leftover: list[dict[str, object]] = []
    for members in families.values():
        if len(members) < 2:
            continue
        for loc in members:
            remaining = qty[loc.id]
            if remaining <= 0:
                continue
            reason = _leftover_reason(plan, loc, members, qty, blocked)
            if reason is None:
                continue
            leftover.append(
                {
                    "id": loc.id,
                    "sku": loc.sku,
                    "lot": loc.lot,
                    "qty": remaining,
                    "max_qty": loc.max_qty,
                    "kind": loc.kind,
                    "temp": loc.temp,
                    "reason": reason,
                }
            )
    leftover.sort(key=lambda item: item["id"])
    return leftover


def _leftover_reason(
    plan: FoldPlan,
    loc: Location,
    members: list[Location],
    qty: dict[str, int],
    blocked: dict[str, str],
) -> str | None:
    if loc.locked:
        return "locked"
    if loc.hold:
        return "quality hold"
    if loc.id in blocked:
        return blocked[loc.id]
    return None


def _location_state(loc: Location, qty: int) -> dict[str, object]:
    fill = qty / loc.max_qty if loc.max_qty else 0.0
    return {
        "id": loc.id,
        "aisle": loc.aisle,
        "bay": loc.bay,
        "level": loc.level,
        "sku": loc.sku if qty > 0 else "",
        "lot": loc.lot if qty > 0 else "",
        "qty": qty,
        "max_qty": loc.max_qty,
        "unit_kg": loc.unit_kg,
        "max_kg": loc.max_kg,
        "temp": loc.temp,
        "kind": loc.kind,
        "locked": loc.locked,
        "hold": loc.hold,
        "fill": round(fill, 4),
        "freed": qty == 0 and loc.qty > 0,
    }
