"""Greedy sortation assigner: many cartons share a destination chute."""

from __future__ import annotations

from dataclasses import dataclass, field

from .banks import Bank
from .model import Carton, Wave


@dataclass
class ChuteState:
    row: int
    col: int
    dest: str | None = None
    carrier: str | None = None
    carton_ids: list[str] = field(default_factory=list)
    weight_kg: float = 0.0
    volume_mm3: int = 0

    @property
    def count(self) -> int:
        return len(self.carton_ids)


@dataclass(frozen=True)
class Placement:
    seq: int
    carton_id: str
    dest: str
    carrier: str
    priority: int
    row: int
    col: int
    chute: str
    zone: str
    weight_kg: float
    volume_mm3: int
    temp: str
    minutes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "carton_id": self.carton_id,
            "dest": self.dest,
            "carrier": self.carrier,
            "priority": self.priority,
            "row": self.row,
            "col": self.col,
            "chute": self.chute,
            "zone": self.zone,
            "weight_kg": self.weight_kg,
            "volume_mm3": self.volume_mm3,
            "temp": self.temp,
            "minutes": self.minutes,
        }


@dataclass
class PlanResult:
    bank: Bank
    strategy: str
    labor_cap_min: int
    labor_used_min: int
    placements: list[Placement]
    leftover: list[dict[str, object]]
    cartons: list[dict[str, object]]
    dests: list[dict[str, object]]
    bank_map: list[dict[str, object]]
    packed_cartons: int
    carton_count: int
    dest_count: int
    leftover_cartons: int
    used_chutes: int

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def chute_utilization(self) -> float:
        if self.bank.chute_count <= 0:
            return 0.0
        return self.used_chutes / self.bank.chute_count

    @property
    def labor_utilization(self) -> float:
        if self.labor_cap_min <= 0:
            return 0.0
        return self.labor_used_min / self.labor_cap_min

    def as_dict(self) -> dict[str, object]:
        return {
            "bank": self.bank.as_dict(),
            "strategy": self.strategy,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "placements": [item.as_dict() for item in self.placements],
            "leftover": list(self.leftover),
            "cartons": list(self.cartons),
            "dests": list(self.dests),
            "bank_map": list(self.bank_map),
            "packed_cartons": self.packed_cartons,
            "carton_count": self.carton_count,
            "dest_count": self.dest_count,
            "leftover_count": self.leftover_count,
            "leftover_cartons": self.leftover_cartons,
            "used_chutes": self.used_chutes,
            "chute_utilization": round(self.chute_utilization, 4),
            "all_fit": self.all_fit,
        }


def _carton_fits_mouth(carton: Carton, bank: Bank) -> bool:
    dims = sorted((carton.length_mm, carton.width_mm, carton.height_mm))
    mouth = sorted((bank.length_mm, bank.width_mm, bank.height_mm))
    return all(edge <= limit for edge, limit in zip(dims, mouth))


def _hard_reject(carton: Carton, bank: Bank) -> dict[str, object] | None:
    if not bank.accepts_temp(carton.temp):
        return _leftover_row(carton, "temp")
    if not _carton_fits_mouth(carton, bank) or carton.volume_mm3 > bank.mouth_volume_mm3:
        return _leftover_row(carton, "too-big")
    if carton.weight_kg > bank.max_weight_kg + 1e-9:
        return _leftover_row(carton, "too-heavy")
    return None


def _chute_can_take(state: ChuteState, carton: Carton, bank: Bank, strategy: str) -> bool:
    if state.count >= bank.max_cartons:
        return False
    if state.weight_kg + carton.weight_kg > bank.max_weight_kg + 1e-9:
        return False
    if state.dest is not None and state.dest != carton.dest:
        return False
    if strategy == "carrier" and state.carrier is not None and state.carrier != carton.carrier:
        return False
    return True


def _sort_cartons(cartons: list[Carton], strategy: str) -> list[Carton]:
    if strategy == "compact":
        return sorted(cartons, key=lambda item: (item.volume_mm3, item.weight_kg, item.id))
    if strategy == "dest":
        return sorted(cartons, key=lambda item: (item.dest, item.id))
    if strategy == "carrier":
        return sorted(cartons, key=lambda item: (item.carrier, item.dest, item.id))
    return sorted(cartons, key=lambda item: (item.priority, -item.volume_mm3, item.dest, item.id))


def _adjacent(cell: tuple[int, int], other: tuple[int, int]) -> bool:
    return abs(cell[0] - other[0]) + abs(cell[1] - other[1]) == 1


def _pick_existing(
    carton: Carton,
    filled: dict[tuple[int, int], ChuteState],
    bank: Bank,
    strategy: str,
) -> tuple[int, int] | None:
    matches = [
        cell
        for cell, state in filled.items()
        if _chute_can_take(state, carton, bank, strategy)
        and state.dest == carton.dest
    ]
    if not matches:
        return None

    def score(cell: tuple[int, int]) -> tuple[int, float, int, int]:
        state = filled[cell]
        remaining = bank.max_cartons - state.count
        return (-remaining, bank.golden_score(*cell), cell[0], cell[1])

    return min(matches, key=score)


def _pick_empty(
    carton: Carton,
    empty: list[tuple[int, int]],
    filled: dict[tuple[int, int], ChuteState],
    bank: Bank,
    strategy: str,
) -> tuple[int, int]:
    if strategy in {"dest", "carrier", "compact"}:
        return min(empty, key=lambda cell: (bank.raster_index(*cell), cell))

    dest_cells = [cell for cell, state in filled.items() if state.dest == carton.dest]

    def score(cell: tuple[int, int]) -> tuple[int, float, int, int]:
        gold = bank.golden_score(*cell)
        cluster = 0
        if dest_cells:
            cluster = 0 if any(_adjacent(cell, other) for other in dest_cells) else 10
        return (cluster, gold, cell[0], cell[1])

    return min(empty, key=score)


def _leftover_row(carton: Carton, reason: str) -> dict[str, object]:
    return {
        "id": carton.id,
        "dest": carton.dest,
        "carrier": carton.carrier,
        "priority": carton.priority,
        "reason": reason,
    }


def _build_bank_map(bank: Bank, filled: dict[tuple[int, int], ChuteState]) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for row in range(1, bank.rows + 1):
        for col in range(1, bank.cols + 1):
            state = filled.get((row, col))
            cell: dict[str, object] = {
                "row": row,
                "col": col,
                "chute": bank.chute_id(row, col),
                "zone": bank.zone_of(row),
                "dest": None,
                "carrier": None,
                "count": 0,
                "weight_kg": 0.0,
                "carton_ids": [],
            }
            if state is not None:
                cell.update(
                    {
                        "dest": state.dest,
                        "carrier": state.carrier,
                        "count": state.count,
                        "weight_kg": round(state.weight_kg, 3),
                        "carton_ids": list(state.carton_ids),
                    }
                )
            cells.append(cell)
    return cells


def _build_carton_rows(
    wave: Wave,
    assigned: dict[str, tuple[int, int]],
    leftover: list[dict[str, object]],
) -> list[dict[str, object]]:
    left_by = {item["id"] for item in leftover}
    rows = []
    for carton in wave.cartons:
        cell = assigned.get(carton.id)
        packed = carton.id not in left_by
        rows.append(
            {
                "id": carton.id,
                "dest": carton.dest,
                "carrier": carton.carrier,
                "priority": carton.priority,
                "packed": packed,
                "row": cell[0] if cell else None,
                "col": cell[1] if cell else None,
                "chute": wave.bank.chute_id(*cell) if cell else None,
                "zone": wave.bank.zone_of(cell[0]) if cell else None,
                "minutes": wave.bank.minutes_per_carton if packed else 0,
            }
        )
    return rows


def _build_dest_rows(
    wave: Wave,
    filled: dict[tuple[int, int], ChuteState],
    leftover: list[dict[str, object]],
) -> list[dict[str, object]]:
    dests = sorted({carton.dest for carton in wave.cartons})
    left_count: dict[str, int] = {}
    for item in leftover:
        dest = str(item["dest"])
        left_count[dest] = left_count.get(dest, 0) + 1
    rows = []
    for dest in dests:
        chutes = [
            wave.bank.chute_id(row, col)
            for (row, col), state in filled.items()
            if state.dest == dest
        ]
        packed = sum(state.count for state in filled.values() if state.dest == dest)
        rows.append(
            {
                "dest": dest,
                "packed": packed,
                "leftover": left_count.get(dest, 0),
                "chutes": sorted(chutes),
            }
        )
    return rows


def plan_bank(wave: Wave) -> PlanResult:
    wave.validate()
    bank = wave.bank
    leftover: list[dict[str, object]] = []
    placements: list[Placement] = []
    filled: dict[tuple[int, int], ChuteState] = {}
    assigned: dict[str, tuple[int, int]] = {}
    empty = [(row, col) for row in range(1, bank.rows + 1) for col in range(1, bank.cols + 1)]
    labor_cap = wave.labor_cap()
    labor_used = 0
    minutes_each = bank.minutes_per_carton

    for carton in _sort_cartons(wave.cartons, wave.strategy):
        blocked = _hard_reject(carton, bank)
        if blocked is not None:
            leftover.append(blocked)
            continue
        if labor_used + minutes_each > labor_cap:
            leftover.append(_leftover_row(carton, "labor-cap"))
            continue
        cell = _pick_existing(carton, filled, bank, wave.strategy)
        if cell is None:
            openable = [spot for spot in empty if _chute_can_take(ChuteState(*spot), carton, bank, wave.strategy)]
            if not openable:
                had_dest = any(state.dest == carton.dest for state in filled.values())
                leftover.append(_leftover_row(carton, "chute-full" if had_dest else "no-chute"))
                continue
            cell = _pick_empty(carton, openable, filled, bank, wave.strategy)
            empty.remove(cell)
            filled[cell] = ChuteState(row=cell[0], col=cell[1])
        state = filled[cell]
        state.dest = carton.dest
        state.carrier = carton.carrier if state.carrier is None else state.carrier
        state.carton_ids.append(carton.id)
        state.weight_kg += carton.weight_kg
        state.volume_mm3 += carton.volume_mm3
        assigned[carton.id] = cell
        labor_used += minutes_each
        row, col = cell
        placements.append(
            Placement(
                seq=len(placements) + 1,
                carton_id=carton.id,
                dest=carton.dest,
                carrier=carton.carrier,
                priority=carton.priority,
                row=row,
                col=col,
                chute=bank.chute_id(row, col),
                zone=bank.zone_of(row),
                weight_kg=carton.weight_kg,
                volume_mm3=carton.volume_mm3,
                temp=carton.temp,
                minutes=minutes_each,
            )
        )

    dests = _build_dest_rows(wave, filled, leftover)
    return PlanResult(
        bank=bank,
        strategy=wave.strategy,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        placements=placements,
        leftover=leftover,
        cartons=_build_carton_rows(wave, assigned, leftover),
        dests=dests,
        bank_map=_build_bank_map(bank, filled),
        packed_cartons=len(placements),
        carton_count=len(wave.cartons),
        dest_count=len(dests),
        leftover_cartons=len(leftover),
        used_chutes=len(filled),
    )
