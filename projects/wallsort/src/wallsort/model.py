"""Batch input types: wall, orders, and unit lines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .walls import STRATEGIES, TEMPS, Wall, get_wall


def _as_int(value: Any, field: str, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


@dataclass(frozen=True)
class OrderLine:
    sku: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    temp: str = "ambient"
    quantity: int = 1

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each line needs a sku")
        if self.length_mm < 1 or self.width_mm < 1 or self.height_mm < 1:
            raise ValueError(f"SKU '{self.sku}' dimensions must be at least 1 mm")
        if self.weight_kg <= 0:
            raise ValueError(f"SKU '{self.sku}' weight must be positive")
        if self.temp not in TEMPS:
            raise ValueError(f"SKU '{self.sku}' temp must be {', '.join(TEMPS)}")
        if self.quantity < 1:
            raise ValueError(f"SKU '{self.sku}' quantity must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "temp": self.temp,
            "quantity": self.quantity,
        }


@dataclass(frozen=True)
class Piece:
    id: str
    order_id: str
    sku: str
    carrier: str
    priority: int
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    temp: str

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm


@dataclass(frozen=True)
class Order:
    id: str
    carrier: str
    priority: int
    lines: list[OrderLine]

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each order needs an id")
        if not self.carrier.strip():
            raise ValueError(f"Order '{self.id}' needs a carrier")
        if self.priority < 1:
            raise ValueError(f"Order '{self.id}' priority must be at least 1")
        if not self.lines:
            raise ValueError(f"Order '{self.id}' has no lines")
        for line in self.lines:
            line.validate()

    def expand(self) -> list[Piece]:
        pieces: list[Piece] = []
        for line_no, line in enumerate(self.lines, start=1):
            base = f"{self.id}-L{line_no}"
            for index in range(line.quantity):
                piece_id = base if line.quantity == 1 else f"{base}-{index + 1}"
                pieces.append(
                    Piece(
                        id=piece_id,
                        order_id=self.id,
                        sku=line.sku,
                        carrier=self.carrier,
                        priority=self.priority,
                        length_mm=line.length_mm,
                        width_mm=line.width_mm,
                        height_mm=line.height_mm,
                        weight_kg=line.weight_kg,
                        temp=line.temp,
                    )
                )
        return pieces

    @property
    def piece_count(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def volume_mm3(self) -> int:
        return sum(line.volume_mm3 * line.quantity for line in self.lines)

    @property
    def weight_kg(self) -> float:
        return sum(line.weight_kg * line.quantity for line in self.lines)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "carrier": self.carrier,
            "priority": self.priority,
            "lines": [item.as_dict() for item in self.lines],
        }


@dataclass
class Batch:
    wall: Wall
    orders: list[Order]
    strategy: str = "auto"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.wall.max_labor_min

    def validate(self) -> None:
        self.wall.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.orders:
            raise ValueError("Batch has no orders")
        seen: set[str] = set()
        for order in self.orders:
            order.validate()
            if order.id in seen:
                raise ValueError(f"Duplicate order '{order.id}'")
            seen.add(order.id)

    def expand(self) -> list[Piece]:
        pieces: list[Piece] = []
        for order in self.orders:
            pieces.extend(order.expand())
        return pieces

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Batch:
        orders: list[Order] = []
        for raw in payload.get("orders") or []:
            lines: list[OrderLine] = []
            for item in raw.get("lines") or []:
                lines.append(
                    OrderLine(
                        sku=str(item.get("sku", "")).strip(),
                        length_mm=_as_int(item.get("length_mm"), "length_mm"),
                        width_mm=_as_int(item.get("width_mm"), "width_mm"),
                        height_mm=_as_int(item.get("height_mm"), "height_mm"),
                        weight_kg=_as_float(item.get("weight_kg"), "weight_kg"),
                        temp=str(item.get("temp", "ambient")).strip() or "ambient",
                        quantity=_as_int(item.get("quantity", 1), "quantity", 1),
                    )
                )
            orders.append(
                Order(
                    id=str(raw.get("id", "")).strip(),
                    carrier=str(raw.get("carrier", "")).strip() or "LOCAL",
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                    lines=lines,
                )
            )
        labor = payload.get("labor_minutes")
        batch = cls(
            wall=get_wall(payload.get("wall") or {}),
            orders=orders,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        batch.validate()
        return batch
