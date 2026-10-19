"""Greedy put-to-wall assigner: one order per cubby, waist row first."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Batch, Order, Piece
from .walls import Wall


@dataclass(frozen=True)
class Placement:
    seq: int
    piece_id: str
    order_id: str
    sku: str
    carrier: str
    priority: int
    row: int
    col: int
    cubby: str
    zone: str
    weight_kg: float
    volume_mm3: int
    temp: str
    minutes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "piece_id": self.piece_id,
            "order_id": self.order_id,
            "sku": self.sku,
            "carrier": self.carrier,
            "priority": self.priority,
            "row": self.row,
            "col": self.col,
            "cubby": self.cubby,
            "zone": self.zone,
            "weight_kg": self.weight_kg,
            "volume_mm3": self.volume_mm3,
            "temp": self.temp,
            "minutes": self.minutes,
        }


@dataclass
class SortResult:
    wall: Wall
    strategy: str
    labor_cap_min: int
    labor_used_min: int
    weight_used_kg: float
    placements: list[Placement]
    leftover: list[dict[str, object]]
    orders: list[dict[str, object]]
    wall_map: list[dict[str, object]]
    packed_count: int
    packed_orders: int
    piece_count: int
    order_count: int

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def leftover_orders(self) -> int:
        return len({item["order_id"] for item in self.leftover})

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def cubby_utilization(self) -> float:
        if self.wall.cubby_count <= 0:
            return 0.0
        return self.packed_orders / self.wall.cubby_count

    @property
    def labor_utilization(self) -> float:
        if self.labor_cap_min <= 0:
            return 0.0
        return self.labor_used_min / self.labor_cap_min

    def as_dict(self) -> dict[str, object]:
        return {
            "wall": self.wall.as_dict(),
            "strategy": self.strategy,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "weight_used_kg": self.weight_used_kg,
            "cubby_utilization": round(self.cubby_utilization, 4),
            "placements": [item.as_dict() for item in self.placements],
            "leftover": list(self.leftover),
            "orders": list(self.orders),
            "wall_map": list(self.wall_map),
            "packed_count": self.packed_count,
            "packed_orders": self.packed_orders,
            "leftover_count": self.leftover_count,
            "leftover_orders": self.leftover_orders,
            "piece_count": self.piece_count,
            "order_count": self.order_count,
            "all_fit": self.all_fit,
        }


def _piece_fits(piece: Piece, wall: Wall) -> bool:
    dims = sorted((piece.length_mm, piece.width_mm, piece.height_mm))
    box = sorted((wall.length_mm, wall.width_mm, wall.height_mm))
    return all(edge <= limit for edge, limit in zip(dims, box))


def _order_reject_reason(order: Order, wall: Wall) -> str | None:
    pieces = order.expand()
    if any(not wall.accepts_temp(piece.temp) for piece in pieces):
        return "temp"
    if any(not _piece_fits(piece, wall) for piece in pieces):
        return "too-big"
    if order.volume_mm3 > wall.cubby_volume_mm3:
        return "too-big"
    if order.weight_kg > wall.max_weight_kg + 1e-9:
        return "too-heavy"
    return None


def _sort_orders(orders: list[Order], strategy: str) -> list[Order]:
    if strategy == "compact":
        return sorted(orders, key=lambda item: (item.volume_mm3, item.id))
    if strategy == "carrier":
        return sorted(orders, key=lambda item: (item.carrier, -item.volume_mm3, item.id))
    return sorted(orders, key=lambda item: (item.priority, -item.volume_mm3, item.id))


def _adjacent(cell: tuple[int, int], other: tuple[int, int]) -> bool:
    return abs(cell[0] - other[0]) + abs(cell[1] - other[1]) == 1


def _pick_cubby(
    order: Order,
    empty: list[tuple[int, int]],
    by_carrier: dict[str, list[tuple[int, int]]],
    wall: Wall,
    strategy: str,
) -> tuple[int, int]:
    if strategy in {"carrier", "compact"}:
        return min(empty, key=lambda cell: (wall.raster_index(*cell), cell))

    neighbors = by_carrier.get(order.carrier, [])

    def score(cell: tuple[int, int]) -> tuple[float, int, int]:
        gold = wall.golden_score(*cell)
        if strategy == "auto" and neighbors:
            clustered = any(_adjacent(cell, other) for other in neighbors)
            gold = gold if clustered else gold + 10
        return (gold, cell[0], cell[1])

    return min(empty, key=score)


def _leftover_rows(order: Order, reason: str) -> list[dict[str, object]]:
    rows = []
    for piece in order.expand():
        rows.append(
            {
                "id": piece.id,
                "order_id": order.id,
                "sku": piece.sku,
                "carrier": order.carrier,
                "priority": order.priority,
                "weight_kg": piece.weight_kg,
                "reason": reason,
            }
        )
    return rows


def _build_wall_map(
    wall: Wall, assigned: dict[tuple[int, int], Order]
) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for row in range(1, wall.rows + 1):
        for col in range(1, wall.cols + 1):
            order = assigned.get((row, col))
            cell: dict[str, object] = {
                "row": row,
                "col": col,
                "cubby": wall.cubby_id(row, col),
                "zone": wall.zone_of(row),
                "order_id": None,
                "carrier": None,
                "priority": None,
                "piece_count": 0,
                "weight_kg": 0,
                "skus": [],
            }
            if order is not None:
                cell.update(
                    {
                        "order_id": order.id,
                        "carrier": order.carrier,
                        "priority": order.priority,
                        "piece_count": order.piece_count,
                        "weight_kg": order.weight_kg,
                        "skus": [piece.sku for piece in order.expand()],
                    }
                )
            cells.append(cell)
    return cells


def _order_rows(
    batch: Batch,
    assigned: dict[tuple[int, int], Order],
    leftover: list[dict[str, object]],
) -> list[dict[str, object]]:
    cubby_of = {order.id: cell for cell, order in assigned.items()}
    left_by = {item["order_id"] for item in leftover}
    rows = []
    for order in batch.orders:
        cell = cubby_of.get(order.id)
        rows.append(
            {
                "id": order.id,
                "carrier": order.carrier,
                "priority": order.priority,
                "piece_count": order.piece_count,
                "packed": 0 if order.id in left_by else order.piece_count,
                "leftover": order.piece_count if order.id in left_by else 0,
                "row": cell[0] if cell else None,
                "col": cell[1] if cell else None,
                "cubby": batch.wall.cubby_id(*cell) if cell else None,
                "zone": batch.wall.zone_of(cell[0]) if cell else None,
            }
        )
    return rows


def sort_wall(batch: Batch) -> SortResult:
    batch.validate()
    wall = batch.wall
    leftover: list[dict[str, object]] = []
    placements: list[Placement] = []
    assigned: dict[tuple[int, int], Order] = {}
    by_carrier: dict[str, list[tuple[int, int]]] = {}
    empty = [(row, col) for row in range(1, wall.rows + 1) for col in range(1, wall.cols + 1)]
    labor_cap = batch.labor_cap()
    labor_used = 0
    weight_used = 0.0
    minutes_each = wall.minutes_per_unit

    for order in _sort_orders(batch.orders, batch.strategy):
        reason = _order_reject_reason(order, wall)
        if reason is not None:
            leftover.extend(_leftover_rows(order, reason))
            continue
        minutes = minutes_each * order.piece_count
        if labor_used + minutes > labor_cap:
            leftover.extend(_leftover_rows(order, "labor-cap"))
            continue
        if not empty:
            leftover.extend(_leftover_rows(order, "no-cubby"))
            continue
        cell = _pick_cubby(order, empty, by_carrier, wall, batch.strategy)
        empty.remove(cell)
        assigned[cell] = order
        by_carrier.setdefault(order.carrier, []).append(cell)
        labor_used += minutes
        weight_used += order.weight_kg
        row, col = cell
        zone = wall.zone_of(row)
        cubby = wall.cubby_id(row, col)
        for piece in order.expand():
            placements.append(
                Placement(
                    seq=len(placements) + 1,
                    piece_id=piece.id,
                    order_id=order.id,
                    sku=piece.sku,
                    carrier=order.carrier,
                    priority=order.priority,
                    row=row,
                    col=col,
                    cubby=cubby,
                    zone=zone,
                    weight_kg=piece.weight_kg,
                    volume_mm3=piece.volume_mm3,
                    temp=piece.temp,
                    minutes=minutes_each,
                )
            )

    return SortResult(
        wall=wall,
        strategy=batch.strategy,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        weight_used_kg=weight_used,
        placements=placements,
        leftover=leftover,
        orders=_order_rows(batch, assigned, leftover),
        wall_map=_build_wall_map(wall, assigned),
        packed_count=len(placements),
        packed_orders=len(assigned),
        piece_count=len(batch.expand()),
        order_count=len(batch.orders),
    )
