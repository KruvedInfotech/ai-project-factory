"""Greedy kitting-line assigner: one build per bench, aisle first."""

from __future__ import annotations

from dataclasses import dataclass

from .lines import Line
from .model import Build, Kit, Wave


@dataclass(frozen=True)
class Placement:
    seq: int
    build_id: str
    kit_sku: str
    quantity: int
    priority: int
    row: int
    col: int
    bench: str
    zone: str
    weight_kg: float
    volume_mm3: int
    temp: str
    minutes: int
    components: list[dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "build_id": self.build_id,
            "kit_sku": self.kit_sku,
            "quantity": self.quantity,
            "priority": self.priority,
            "row": self.row,
            "col": self.col,
            "bench": self.bench,
            "zone": self.zone,
            "weight_kg": self.weight_kg,
            "volume_mm3": self.volume_mm3,
            "temp": self.temp,
            "minutes": self.minutes,
            "components": list(self.components),
        }


@dataclass
class PlanResult:
    line: Line
    strategy: str
    labor_cap_min: int
    labor_used_min: int
    kit_count: int
    placements: list[Placement]
    leftover: list[dict[str, object]]
    builds: list[dict[str, object]]
    line_map: list[dict[str, object]]
    inventory_left: list[dict[str, object]]
    packed_builds: int
    packed_kits: int
    build_count: int
    leftover_kits: int

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def leftover_builds(self) -> int:
        return len(self.leftover)

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def bench_utilization(self) -> float:
        if self.line.bench_count <= 0:
            return 0.0
        return self.packed_builds / self.line.bench_count

    @property
    def labor_utilization(self) -> float:
        if self.labor_cap_min <= 0:
            return 0.0
        return self.labor_used_min / self.labor_cap_min

    def as_dict(self) -> dict[str, object]:
        return {
            "line": self.line.as_dict(),
            "strategy": self.strategy,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "kit_count": self.kit_count,
            "placements": [item.as_dict() for item in self.placements],
            "leftover": list(self.leftover),
            "builds": list(self.builds),
            "line_map": list(self.line_map),
            "inventory_left": list(self.inventory_left),
            "packed_builds": self.packed_builds,
            "packed_kits": self.packed_kits,
            "leftover_count": self.leftover_count,
            "leftover_builds": self.leftover_builds,
            "leftover_kits": self.leftover_kits,
            "build_count": self.build_count,
            "bench_utilization": round(self.bench_utilization, 4),
            "all_fit": self.all_fit,
        }


def _kit_fits(kit: Kit, line: Line) -> bool:
    dims = sorted((kit.length_mm, kit.width_mm, kit.height_mm))
    box = sorted((line.length_mm, line.width_mm, line.height_mm))
    return all(edge <= limit for edge, limit in zip(dims, box))


def _build_reject_reason(
    build: Build, kit: Kit, line: Line, stock: dict[str, int]
) -> dict[str, object] | None:
    if not line.accepts_temp(kit.temp):
        return _leftover_row(build, kit, "temp")
    if not _kit_fits(kit, line) or kit.volume_mm3 > line.bench_volume_mm3:
        return _leftover_row(build, kit, "too-big")
    if kit.weight_kg > line.max_weight_kg + 1e-9:
        return _leftover_row(build, kit, "too-heavy")
    if build.quantity > line.max_run:
        return _leftover_row(build, kit, "over-run")
    for sku, need in kit.need_for(build.quantity).items():
        on_hand = stock.get(sku, 0)
        if on_hand < need:
            row = _leftover_row(build, kit, "short")
            row["missing_sku"] = sku
            row["need"] = need
            row["on_hand"] = on_hand
            return row
    return None


def _sort_builds(builds: list[Build], kits: dict[str, Kit], strategy: str) -> list[Build]:
    def work(build: Build) -> int:
        return kits[build.kit_sku].bom_units * build.quantity

    if strategy == "compact":
        return sorted(builds, key=lambda item: (item.quantity, work(item), item.id))
    if strategy == "family":
        return sorted(builds, key=lambda item: (item.kit_sku, -item.quantity, item.id))
    return sorted(builds, key=lambda item: (item.priority, -work(item), item.id))


def _adjacent(cell: tuple[int, int], other: tuple[int, int]) -> bool:
    return abs(cell[0] - other[0]) + abs(cell[1] - other[1]) == 1


def _pick_bench(
    build: Build,
    empty: list[tuple[int, int]],
    by_kit: dict[str, list[tuple[int, int]]],
    line: Line,
    strategy: str,
) -> tuple[int, int]:
    if strategy in {"family", "compact"}:
        return min(empty, key=lambda cell: (line.raster_index(*cell), cell))

    neighbors = by_kit.get(build.kit_sku, [])

    def score(cell: tuple[int, int]) -> tuple[float, int, int]:
        gold = line.golden_score(*cell)
        if strategy == "auto" and neighbors:
            clustered = any(_adjacent(cell, other) for other in neighbors)
            gold = gold if clustered else gold + 10
        return (gold, cell[0], cell[1])

    return min(empty, key=score)


def _leftover_row(build: Build, kit: Kit, reason: str) -> dict[str, object]:
    return {
        "id": build.id,
        "kit_sku": kit.sku,
        "quantity": build.quantity,
        "priority": build.priority,
        "reason": reason,
    }


def _build_line_map(
    line: Line, assigned: dict[tuple[int, int], tuple[Build, Kit]]
) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for row in range(1, line.rows + 1):
        for col in range(1, line.cols + 1):
            seated = assigned.get((row, col))
            cell: dict[str, object] = {
                "row": row,
                "col": col,
                "bench": line.bench_id(row, col),
                "zone": line.zone_of(row),
                "build_id": None,
                "kit_sku": None,
                "priority": None,
                "quantity": 0,
                "minutes": 0,
                "bom": [],
            }
            if seated is not None:
                build, kit = seated
                cell.update(
                    {
                        "build_id": build.id,
                        "kit_sku": kit.sku,
                        "priority": build.priority,
                        "quantity": build.quantity,
                        "minutes": line.minutes_per_kit * build.quantity,
                        "bom": [item.as_dict() for item in kit.bom],
                    }
                )
            cells.append(cell)
    return cells


def _build_rows(
    wave: Wave,
    assigned: dict[tuple[int, int], tuple[Build, Kit]],
    leftover: list[dict[str, object]],
) -> list[dict[str, object]]:
    bench_of = {build.id: cell for cell, (build, _kit) in assigned.items()}
    left_by = {item["id"] for item in leftover}
    kits = wave.kit_map()
    rows = []
    for build in wave.builds:
        cell = bench_of.get(build.id)
        kit = kits[build.kit_sku]
        packed = 0 if build.id in left_by else build.quantity
        rows.append(
            {
                "id": build.id,
                "kit_sku": build.kit_sku,
                "priority": build.priority,
                "quantity": build.quantity,
                "packed": packed,
                "leftover": build.quantity - packed,
                "row": cell[0] if cell else None,
                "col": cell[1] if cell else None,
                "bench": wave.line.bench_id(*cell) if cell else None,
                "zone": wave.line.zone_of(cell[0]) if cell else None,
                "minutes": wave.line.minutes_per_kit * packed,
                "bom_units": kit.bom_units * packed,
            }
        )
    return rows


def plan_line(wave: Wave) -> PlanResult:
    wave.validate()
    line = wave.line
    kits = wave.kit_map()
    leftover: list[dict[str, object]] = []
    placements: list[Placement] = []
    assigned: dict[tuple[int, int], tuple[Build, Kit]] = {}
    by_kit: dict[str, list[tuple[int, int]]] = {}
    empty = [(row, col) for row in range(1, line.rows + 1) for col in range(1, line.cols + 1)]
    labor_cap = wave.labor_cap()
    labor_used = 0
    packed_kits = 0
    stock = dict(wave.inventory)
    minutes_each = line.minutes_per_kit

    for build in _sort_builds(wave.builds, kits, wave.strategy):
        kit = kits[build.kit_sku]
        blocked = _build_reject_reason(build, kit, line, stock)
        if blocked is not None:
            leftover.append(blocked)
            continue
        minutes = minutes_each * build.quantity
        if labor_used + minutes > labor_cap:
            leftover.append(_leftover_row(build, kit, "labor-cap"))
            continue
        if not empty:
            leftover.append(_leftover_row(build, kit, "no-bench"))
            continue
        cell = _pick_bench(build, empty, by_kit, line, wave.strategy)
        empty.remove(cell)
        assigned[cell] = (build, kit)
        by_kit.setdefault(build.kit_sku, []).append(cell)
        labor_used += minutes
        packed_kits += build.quantity
        for sku, need in kit.need_for(build.quantity).items():
            stock[sku] = stock.get(sku, 0) - need
        row, col = cell
        placements.append(
            Placement(
                seq=len(placements) + 1,
                build_id=build.id,
                kit_sku=kit.sku,
                quantity=build.quantity,
                priority=build.priority,
                row=row,
                col=col,
                bench=line.bench_id(row, col),
                zone=line.zone_of(row),
                weight_kg=kit.weight_kg * build.quantity,
                volume_mm3=kit.volume_mm3,
                temp=kit.temp,
                minutes=minutes,
                components=[
                    {"sku": sku, "quantity": qty}
                    for sku, qty in kit.need_for(build.quantity).items()
                ],
            )
        )

    inventory_left = [
        {"sku": sku, "on_hand": stock.get(sku, 0)}
        for sku in sorted(set(wave.inventory) | set(stock))
    ]
    leftover_kits = sum(int(item["quantity"]) for item in leftover)
    return PlanResult(
        line=line,
        strategy=wave.strategy,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        kit_count=sum(build.quantity for build in wave.builds),
        placements=placements,
        leftover=leftover,
        builds=_build_rows(wave, assigned, leftover),
        line_map=_build_line_map(line, assigned),
        inventory_left=inventory_left,
        packed_builds=len(assigned),
        packed_kits=packed_kits,
        build_count=len(wave.builds),
        leftover_kits=leftover_kits,
    )
