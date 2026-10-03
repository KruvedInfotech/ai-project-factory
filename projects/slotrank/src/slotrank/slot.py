"""Greedy velocity-based slotting planner."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Location, SlotPlan, Sku
from .warehouses import Warehouse


def classify_abc(skus: list[Sku], a_share: float, b_share: float) -> dict[str, str]:
    """Assign A/B/C from pick velocity. The SKU that crosses a band stays in it."""
    ordered = sorted(skus, key=lambda item: (-item.picks, item.sku))
    total = sum(item.picks for item in skus)
    classes: dict[str, str] = {}
    if total <= 0:
        return {item.sku: "C" for item in skus}
    a_cut = total * a_share
    b_cut = total * (a_share + b_share)
    running = 0
    for item in ordered:
        previous = running
        running += item.picks
        if previous < a_cut:
            classes[item.sku] = "A"
        elif previous < b_cut:
            classes[item.sku] = "B"
        else:
            classes[item.sku] = "C"
    return classes


def distance(aisle: int, bay: int) -> float:
    """Walk cost from the depot at the front of aisle 1."""
    return aisle + 0.2 * bay


def compatible(sku: Sku, loc: Location) -> bool:
    if loc.slot_type != sku.slot_type:
        return False
    if loc.max_cube < sku.cube:
        return False
    if sku.is_heavy and not loc.allow_heavy:
        return False
    return True


def class_fit(abc: str, golden: bool) -> float:
    if abc == "A":
        return 0.0 if golden else 14.0
    if abc == "B":
        return 4.0 if golden else 1.0
    return 12.0 if golden else 0.0


@dataclass
class Move:
    sku: str
    abc: str
    from_id: str
    to_id: str
    from_aisle: int
    to_aisle: int
    from_bay: int
    to_bay: int
    labor_min: int
    benefit: float
    wave: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "abc": self.abc,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "from_aisle": self.from_aisle,
            "to_aisle": self.to_aisle,
            "from_bay": self.from_bay,
            "to_bay": self.to_bay,
            "labor_min": self.labor_min,
            "benefit": self.benefit,
            "wave": self.wave,
        }


@dataclass
class Placement:
    sku: Sku
    abc: str
    location: Location | None
    status: str
    current: Location | None = None

    @property
    def golden(self) -> bool:
        return bool(self.location and self._golden)

    def __post_init__(self) -> None:
        self._golden = False

    def mark_golden(self, warehouse: Warehouse) -> None:
        if self.location:
            self._golden = warehouse.is_golden(self.location.aisle, self.location.bay)

    def as_dict(self) -> dict[str, object]:
        loc = self.location
        cur = self.current
        return {
            "sku": self.sku.sku,
            "abc": self.abc,
            "picks": self.sku.picks,
            "family": self.sku.family,
            "heavy": self.sku.is_heavy,
            "slot_type": self.sku.slot_type,
            "location_id": loc.id if loc else "",
            "aisle": loc.aisle if loc else 0,
            "bay": loc.bay if loc else 0,
            "golden": self.golden,
            "current_id": cur.id if cur else self.sku.current,
            "status": self.status,
        }


@dataclass
class SlotState:
    location: Location
    golden: bool
    sku: str = ""
    abc: str = ""
    status: str = "empty"
    picks: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.location.id,
            "aisle": self.location.aisle,
            "bay": self.location.bay,
            "golden": self.golden,
            "allow_heavy": self.location.allow_heavy,
            "slot_type": self.location.slot_type,
            "sku": self.sku,
            "abc": self.abc,
            "status": self.status,
            "picks": self.picks,
        }


@dataclass
class SlotResult:
    warehouse: Warehouse
    strategy: str
    abc: dict[str, str]
    placements: list[Placement]
    moves: list[Move]
    leftover: list[dict[str, str]]
    locations: list[SlotState]
    labor_min: int
    travel_before: float
    travel_after: float
    a_golden_before: float
    a_golden_after: float
    a_count: int

    @property
    def all_slotted(self) -> bool:
        return not self.leftover

    @property
    def move_count(self) -> int:
        return sum(1 for move in self.moves if move.wave == "now")

    @property
    def later_count(self) -> int:
        return sum(1 for move in self.moves if move.wave == "later")

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def keep_count(self) -> int:
        return sum(1 for item in self.placements if item.status == "keep")

    @property
    def labor_fill(self) -> float:
        if self.warehouse.max_labor_min <= 0:
            return 0.0
        return self.labor_min / self.warehouse.max_labor_min

    def as_dict(self) -> dict[str, object]:
        return {
            "warehouse": self.warehouse.as_dict(),
            "strategy": self.strategy,
            "abc": self.abc,
            "placements": [item.as_dict() for item in self.placements],
            "moves": [move.as_dict() for move in self.moves],
            "leftover": self.leftover,
            "locations": [item.as_dict() for item in self.locations],
            "labor_min": self.labor_min,
            "labor_fill": self.labor_fill,
            "travel_before": self.travel_before,
            "travel_after": self.travel_after,
            "a_golden_before": self.a_golden_before,
            "a_golden_after": self.a_golden_after,
            "a_count": self.a_count,
            "move_count": self.move_count,
            "later_count": self.later_count,
            "leftover_count": self.leftover_count,
            "keep_count": self.keep_count,
            "all_slotted": self.all_slotted,
        }


def _sku_order(plan: SlotPlan, abc: dict[str, str]) -> list[Sku]:
    rank = {"A": 0, "B": 1, "C": 2}

    def key(sku: Sku) -> tuple:
        abc_rank = rank[abc[sku.sku]]
        if plan.strategy in ("auto", "heavy"):
            return (0 if sku.is_heavy else 1, abc_rank, -sku.picks, sku.sku)
        return (abc_rank, -sku.picks, sku.sku)

    return sorted(plan.skus, key=key)


def _score(
    sku: Sku,
    loc: Location,
    abc: str,
    warehouse: Warehouse,
    family_aisle: dict[str, int],
    strategy: str,
) -> float:
    value = distance(loc.aisle, loc.bay) + class_fit(abc, warehouse.is_golden(loc.aisle, loc.bay))
    if strategy in ("affinity", "auto") and sku.family:
        partner = family_aisle.get(sku.family)
        if partner == loc.aisle:
            value -= 5.0
    if sku.is_heavy and loc.allow_heavy:
        value -= 0.5
    return value


def _current_location(sku: Sku, by_id: dict[str, Location]) -> Location | None:
    if not sku.current:
        return None
    return by_id.get(sku.current)


def _travel(pairs: list[tuple[Sku, Location | None]], warehouse: Warehouse) -> float:
    weighted = 0.0
    picks = 0
    far = warehouse.aisle_count + 2.0
    for sku, loc in pairs:
        weighted += sku.picks * (distance(loc.aisle, loc.bay) if loc else far)
        picks += sku.picks
    return weighted / picks if picks else 0.0


def _a_golden_share(
    pairs: list[tuple[Sku, Location | None]],
    abc: dict[str, str],
    warehouse: Warehouse,
) -> float:
    a_items = [(sku, loc) for sku, loc in pairs if abc[sku.sku] == "A"]
    if not a_items:
        return 0.0
    golden = sum(
        1
        for sku, loc in a_items
        if loc is not None and warehouse.is_golden(loc.aisle, loc.bay)
    )
    return golden / len(a_items)


def slot(plan: SlotPlan) -> SlotResult:
    warehouse = plan.warehouse
    abc = classify_abc(plan.skus, warehouse.a_share, warehouse.b_share)
    by_id = plan.location_map()
    free = {loc.id: loc for loc in plan.locations}
    family_aisle: dict[str, int] = {}
    assignment: dict[str, Location] = {}
    leftover: list[dict[str, str]] = []

    for sku in _sku_order(plan, abc):
        eligible = [loc for loc in free.values() if compatible(sku, loc)]
        if not eligible:
            reason = "no-slot"
            if sku.is_heavy and not any(loc.allow_heavy and loc.slot_type == sku.slot_type for loc in plan.locations):
                reason = "no-heavy-slot"
            leftover.append({"id": sku.sku, "reason": reason})
            continue
        scored = sorted(
            eligible,
            key=lambda loc: (
                _score(sku, loc, abc[sku.sku], warehouse, family_aisle, plan.strategy),
                loc.aisle,
                loc.bay,
                loc.id,
            ),
        )
        chosen = scored[0]
        current = _current_location(sku, by_id)
        if (
            current
            and current.id in free
            and compatible(sku, current)
        ):
            keep_score = _score(sku, current, abc[sku.sku], warehouse, family_aisle, plan.strategy)
            best_score = _score(sku, chosen, abc[sku.sku], warehouse, family_aisle, plan.strategy)
            if keep_score <= best_score + 1.0:
                chosen = current
        assignment[sku.sku] = chosen
        del free[chosen.id]
        if sku.family and sku.family not in family_aisle:
            family_aisle[sku.family] = chosen.aisle

    sku_by_id = {item.sku: item for item in plan.skus}
    proposed_pairs: list[tuple[Sku, Location | None]] = []
    current_pairs: list[tuple[Sku, Location | None]] = []
    placements: list[Placement] = []
    candidates: list[Move] = []

    for sku in plan.skus:
        proposed = assignment.get(sku.sku)
        current = _current_location(sku, by_id)
        proposed_pairs.append((sku, proposed))
        current_pairs.append((sku, current))
        if proposed is None:
            status = "unslotted"
        elif current and current.id == proposed.id:
            status = "keep"
        else:
            status = "move"
            from_aisle = current.aisle if current else 0
            from_bay = current.bay if current else 0
            from_id = current.id if current else "UNSLOTTED"
            minutes = warehouse.minutes_per_move + warehouse.aisle_change_min * abs(
                from_aisle - proposed.aisle
            )
            before = distance(current.aisle, current.bay) if current else warehouse.aisle_count + 2.0
            after = distance(proposed.aisle, proposed.bay)
            benefit = (before - after) * sku.picks
            if abc[sku.sku] == "A" and warehouse.is_golden(proposed.aisle, proposed.bay):
                benefit += sku.picks * 2
            candidates.append(
                Move(
                    sku=sku.sku,
                    abc=abc[sku.sku],
                    from_id=from_id,
                    to_id=proposed.id,
                    from_aisle=from_aisle,
                    to_aisle=proposed.aisle,
                    from_bay=from_bay,
                    to_bay=proposed.bay,
                    labor_min=minutes,
                    benefit=benefit,
                    wave="later",
                )
            )
        placement = Placement(
            sku=sku,
            abc=abc[sku.sku],
            location=proposed,
            status=status,
            current=current,
        )
        placement.mark_golden(warehouse)
        placements.append(placement)

    candidates.sort(key=lambda move: (-move.benefit, move.sku))
    labor = 0
    accepted = 0
    moves: list[Move] = []
    leftover_ids = {item["id"] for item in leftover}
    for move in candidates:
        if accepted >= warehouse.max_moves or labor + move.labor_min > warehouse.max_labor_min:
            move.wave = "later"
            leftover.append({"id": move.sku, "reason": "capped"})
            leftover_ids.add(move.sku)
        else:
            move.wave = "now"
            labor += move.labor_min
            accepted += 1
        moves.append(move)

    placements.sort(key=lambda item: ({"A": 0, "B": 1, "C": 2}[item.abc], -item.sku.picks, item.sku.sku))

    by_loc: dict[str, Placement] = {
        item.location.id: item for item in placements if item.location is not None
    }
    states: list[SlotState] = []
    for loc in sorted(plan.locations, key=lambda item: (item.aisle, item.bay, item.id)):
        placed = by_loc.get(loc.id)
        status = "empty"
        sku_name = ""
        abc_name = ""
        picks = 0
        if placed:
            sku_name = placed.sku.sku
            abc_name = placed.abc
            picks = placed.sku.picks
            if placed.sku.sku in leftover_ids and placed.status == "move":
                status = "later"
            else:
                status = placed.status
        states.append(
            SlotState(
                location=loc,
                golden=warehouse.is_golden(loc.aisle, loc.bay),
                sku=sku_name,
                abc=abc_name,
                status=status,
                picks=picks,
            )
        )

    a_items = [item for item in plan.skus if abc[item.sku] == "A"]
    return SlotResult(
        warehouse=warehouse,
        strategy=plan.strategy,
        abc=abc,
        placements=placements,
        moves=moves,
        leftover=leftover,
        locations=states,
        labor_min=labor,
        travel_before=_travel(current_pairs, warehouse),
        travel_after=_travel(proposed_pairs, warehouse),
        a_golden_before=_a_golden_share(current_pairs, abc, warehouse),
        a_golden_after=_a_golden_share(proposed_pairs, abc, warehouse),
        a_count=len(a_items),
    )
