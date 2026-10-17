"""Greedy LIFO trailer loader: last stop into the nose, first stop at the doors."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Load, Pallet
from .trailers import Trailer


@dataclass(frozen=True)
class Placement:
    seq: int
    pallet_id: str
    sku: str
    stop_id: str
    stop_seq: int
    stop_name: str
    row: int
    col: int
    side: str
    level: int
    weight_kg: float
    height_mm: int
    temp: str
    minutes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "pallet_id": self.pallet_id,
            "sku": self.sku,
            "stop_id": self.stop_id,
            "stop_seq": self.stop_seq,
            "stop_name": self.stop_name,
            "row": self.row,
            "col": self.col,
            "side": self.side,
            "level": self.level,
            "weight_kg": self.weight_kg,
            "height_mm": self.height_mm,
            "temp": self.temp,
            "minutes": self.minutes,
        }


@dataclass
class StackResult:
    trailer: Trailer
    strategy: str
    labor_cap_min: int
    labor_used_min: int
    weight_used_kg: float
    placements: list[Placement]
    leftover: list[dict[str, object]]
    stops: list[dict[str, object]]
    deck: list[dict[str, object]]
    packed_count: int
    piece_count: int

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def weight_utilization(self) -> float:
        if self.trailer.max_weight_kg <= 0:
            return 0.0
        return self.weight_used_kg / self.trailer.max_weight_kg

    @property
    def cube_utilization(self) -> float:
        if self.trailer.slot_count <= 0:
            return 0.0
        return self.packed_count / self.trailer.slot_count

    @property
    def labor_utilization(self) -> float:
        if self.labor_cap_min <= 0:
            return 0.0
        return self.labor_used_min / self.labor_cap_min

    def as_dict(self) -> dict[str, object]:
        return {
            "trailer": self.trailer.as_dict(),
            "strategy": self.strategy,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "weight_used_kg": self.weight_used_kg,
            "weight_utilization": round(self.weight_utilization, 4),
            "cube_utilization": round(self.cube_utilization, 4),
            "placements": [item.as_dict() for item in self.placements],
            "leftover": list(self.leftover),
            "stops": list(self.stops),
            "deck": list(self.deck),
            "packed_count": self.packed_count,
            "leftover_count": self.leftover_count,
            "piece_count": self.piece_count,
            "all_fit": self.all_fit,
        }


def _sort_stop_pallets(pallets: list[Pallet], strategy: str) -> list[Pallet]:
    if strategy in {"heavy", "auto"}:
        return sorted(pallets, key=lambda item: (-item.weight_kg, -item.height_mm, item.id))
    return list(pallets)


def _load_order(load: Load) -> list[Pallet]:
    by_stop = {stop.id: list(stop.expand()) for stop in load.stops}
    ordered: list[Pallet] = []
    for stop in sorted(load.stops, key=lambda item: (-item.seq, item.id)):
        ordered.extend(_sort_stop_pallets(by_stop[stop.id], load.strategy))
    return ordered


def _leftover_row(pallet: Pallet, reason: str) -> dict[str, object]:
    return {
        "id": pallet.id,
        "sku": pallet.sku,
        "stop_id": pallet.stop_id,
        "stop_seq": pallet.stop_seq,
        "stop_name": pallet.stop_name,
        "weight_kg": pallet.weight_kg,
        "height_mm": pallet.height_mm,
        "temp": pallet.temp,
        "reason": reason,
    }


def _find_stack(
    pallet: Pallet,
    trailer: Trailer,
    floor: dict[tuple[int, int], Placement],
    stacked: set[tuple[int, int]],
) -> tuple[int, int, int] | None:
    if trailer.stack_levels < 2:
        return None
    for row in range(1, trailer.rows + 1):
        for col in range(1, trailer.cols + 1):
            key = (row, col)
            base = floor.get(key)
            if base is None or key in stacked:
                continue
            if base.stop_seq != pallet.stop_seq:
                continue
            if base.height_mm + pallet.height_mm > trailer.max_height_mm:
                continue
            return row, col, 1
    return None


def _row_owner(
    row: int,
    trailer: Trailer,
    floor: dict[tuple[int, int], Placement],
) -> int | None:
    owners = {
        floor[(row, col)].stop_seq
        for col in range(1, trailer.cols + 1)
        if (row, col) in floor
    }
    if not owners:
        return None
    if len(owners) == 1:
        return next(iter(owners))
    return -1


def _find_floor(
    pallet: Pallet,
    trailer: Trailer,
    floor: dict[tuple[int, int], Placement],
    no_mix: bool,
) -> tuple[int, int, int] | None:
    for row in range(1, trailer.rows + 1):
        if no_mix:
            owner = _row_owner(row, trailer, floor)
            if owner is not None and owner != pallet.stop_seq:
                continue
        for col in range(1, trailer.cols + 1):
            if (row, col) not in floor:
                return row, col, 0
    return None


def _build_deck(trailer: Trailer, placements: list[Placement]) -> list[dict[str, object]]:
    by_cell: dict[tuple[int, int], dict[str, object]] = {}
    for item in placements:
        cell = by_cell.setdefault(
            (item.row, item.col),
            {
                "row": item.row,
                "col": item.col,
                "side": item.side,
                "floor": None,
                "stack": None,
            },
        )
        payload = {
            "pallet_id": item.pallet_id,
            "sku": item.sku,
            "stop_id": item.stop_id,
            "stop_seq": item.stop_seq,
            "stop_name": item.stop_name,
            "weight_kg": item.weight_kg,
            "height_mm": item.height_mm,
        }
        if item.level == 0:
            cell["floor"] = payload
        else:
            cell["stack"] = payload
    deck: list[dict[str, object]] = []
    for row in range(1, trailer.rows + 1):
        for col in range(1, trailer.cols + 1):
            deck.append(
                by_cell.get(
                    (row, col),
                    {
                        "row": row,
                        "col": col,
                        "side": trailer.side_of(col),
                        "floor": None,
                        "stack": None,
                    },
                )
            )
    return deck


def _stop_rows(load: Load, placements: list[Placement], leftover: list[dict[str, object]]) -> list[dict[str, object]]:
    packed_by_stop: dict[str, int] = {}
    left_by_stop: dict[str, int] = {}
    for item in placements:
        packed_by_stop[item.stop_id] = packed_by_stop.get(item.stop_id, 0) + 1
    for item in leftover:
        left_by_stop[item["stop_id"]] = left_by_stop.get(item["stop_id"], 0) + 1
    rows = []
    for stop in sorted(load.stops, key=lambda item: item.seq):
        piece_count = len(stop.expand())
        packed = packed_by_stop.get(stop.id, 0)
        rows.append(
            {
                "id": stop.id,
                "seq": stop.seq,
                "name": stop.name,
                "piece_count": piece_count,
                "packed": packed,
                "leftover": left_by_stop.get(stop.id, 0),
            }
        )
    return rows


def stack(load: Load) -> StackResult:
    load.validate()
    trailer = load.trailer
    no_mix = load.strategy == "no-mix"
    leftover: list[dict[str, object]] = []
    placements: list[Placement] = []
    floor: dict[tuple[int, int], Placement] = {}
    stacked: set[tuple[int, int]] = set()
    labor_cap = load.labor_cap()
    labor_used = 0
    weight_used = 0.0
    minutes = trailer.minutes_per_pallet

    for pallet in _load_order(load):
        if not trailer.accepts_temp(pallet.temp):
            leftover.append(_leftover_row(pallet, "temp"))
            continue
        if pallet.height_mm > trailer.max_height_mm:
            leftover.append(_leftover_row(pallet, "too-tall"))
            continue
        if labor_used + minutes > labor_cap:
            leftover.append(_leftover_row(pallet, "labor-cap"))
            continue
        slot = _find_stack(pallet, trailer, floor, stacked)
        if slot is None:
            slot = _find_floor(pallet, trailer, floor, no_mix)
        if slot is None:
            leftover.append(_leftover_row(pallet, "no-slot"))
            continue
        if weight_used + pallet.weight_kg > trailer.max_weight_kg + 1e-9:
            leftover.append(_leftover_row(pallet, "payload"))
            continue
        row, col, level = slot
        labor_used += minutes
        weight_used += pallet.weight_kg
        placed = Placement(
            seq=len(placements) + 1,
            pallet_id=pallet.id,
            sku=pallet.sku,
            stop_id=pallet.stop_id,
            stop_seq=pallet.stop_seq,
            stop_name=pallet.stop_name,
            row=row,
            col=col,
            side=trailer.side_of(col),
            level=level,
            weight_kg=pallet.weight_kg,
            height_mm=pallet.height_mm,
            temp=pallet.temp,
            minutes=minutes,
        )
        placements.append(placed)
        if level == 0:
            floor[(row, col)] = placed
        else:
            stacked.add((row, col))

    return StackResult(
        trailer=trailer,
        strategy=load.strategy,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        weight_used_kg=weight_used,
        placements=placements,
        leftover=leftover,
        stops=_stop_rows(load, placements, leftover),
        deck=_build_deck(trailer, placements),
        packed_count=len(placements),
        piece_count=len(load.expand()),
    )
