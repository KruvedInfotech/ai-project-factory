"""Wave input types: orders, pick lines, floor, and cart."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .floor import TEMPS, STRATEGIES, Cart, Warehouse, get_cart, get_warehouse


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
class Line:
    sku: str
    aisle: str
    bay: int
    quantity: int
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm * self.quantity

    @property
    def total_weight_kg(self) -> float:
        return self.weight_kg * self.quantity

    def validate(self, warehouse: Warehouse) -> None:
        if not self.sku.strip():
            raise ValueError("Each line needs a sku")
        if not self.aisle.strip():
            raise ValueError(f"SKU '{self.sku}' needs an aisle")
        if self.quantity < 1:
            raise ValueError(f"SKU '{self.sku}' quantity must be at least 1")
        if min(self.length_mm, self.width_mm, self.height_mm) < 1:
            raise ValueError(f"SKU '{self.sku}' dimensions must be at least 1 mm")
        if self.weight_kg < 0:
            raise ValueError(f"SKU '{self.sku}' weight cannot be negative")
        if not warehouse.contains(self.aisle, self.bay):
            raise ValueError(
                f"SKU '{self.sku}' location {self.aisle}-{self.bay} is not on this floor"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "aisle": self.aisle,
            "bay": self.bay,
            "quantity": self.quantity,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
        }


@dataclass(frozen=True)
class Order:
    id: str
    priority: int
    temp: str
    lines: list[Line]

    def validate(self, warehouse: Warehouse) -> None:
        if not self.id.strip():
            raise ValueError("Each order needs an id")
        if self.priority < 1:
            raise ValueError(f"Order '{self.id}' priority must be at least 1")
        if self.temp not in TEMPS:
            raise ValueError(f"Order '{self.id}' temp must be {', '.join(TEMPS)}")
        if not self.lines:
            raise ValueError(f"Order '{self.id}' has no lines")
        seen: set[str] = set()
        for line in self.lines:
            line.validate(warehouse)
            key = f"{line.sku}@{line.aisle}-{line.bay}"
            if key in seen:
                raise ValueError(f"Order '{self.id}' repeats {key}")
            seen.add(key)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def piece_count(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def weight_kg(self) -> float:
        return sum(line.total_weight_kg for line in self.lines)

    @property
    def volume_mm3(self) -> int:
        return sum(line.volume_mm3 for line in self.lines)

    @property
    def volume_l(self) -> float:
        return self.volume_mm3 / 1_000_000

    def aisle_set(self) -> set[str]:
        return {line.aisle for line in self.lines}

    def aisle_span(self, warehouse: Warehouse) -> int:
        return warehouse.span(self.aisle_set())

    def primary_aisle(self, warehouse: Warehouse) -> tuple[int, int]:
        first = min(self.lines, key=lambda line: (warehouse.aisle_index(line.aisle), line.bay))
        return warehouse.aisle_index(first.aisle), first.bay

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "priority": self.priority,
            "temp": self.temp,
            "lines": [line.as_dict() for line in self.lines],
            "weight_kg": round(self.weight_kg, 3),
            "volume_l": round(self.volume_l, 4),
            "aisles": sorted(self.aisle_set()),
            "line_count": self.line_count,
            "piece_count": self.piece_count,
        }


@dataclass
class Wave:
    warehouse: Warehouse
    cart: Cart
    orders: list[Order]
    strategy: str = "auto"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.cart.max_labor_min

    def validate(self) -> None:
        self.cart.validate()
        if self.warehouse.bays < 1 or not self.warehouse.aisles:
            raise ValueError("Warehouse floor is empty")
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.orders:
            raise ValueError("Wave has no orders")
        seen: set[str] = set()
        for order in self.orders:
            order.validate(self.warehouse)
            if order.id in seen:
                raise ValueError(f"Duplicate order '{order.id}'")
            seen.add(order.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        warehouse = get_warehouse(payload.get("warehouse") or {})
        cart = get_cart(payload.get("cart") or {})
        orders: list[Order] = []
        for raw in payload.get("orders") or []:
            lines = [
                Line(
                    sku=str(item.get("sku", "")).strip(),
                    aisle=str(item.get("aisle", "")).strip().upper(),
                    bay=_as_int(item.get("bay"), "bay"),
                    quantity=_as_int(item.get("quantity", 1), "quantity", 1),
                    length_mm=_as_int(item.get("length_mm"), "length_mm"),
                    width_mm=_as_int(item.get("width_mm"), "width_mm"),
                    height_mm=_as_int(item.get("height_mm"), "height_mm"),
                    weight_kg=_as_float(item.get("weight_kg"), "weight_kg"),
                )
                for item in raw.get("lines") or []
            ]
            orders.append(
                Order(
                    id=str(raw.get("id", "")).strip(),
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    lines=lines,
                )
            )
        labor = payload.get("labor_minutes")
        wave = cls(
            warehouse=warehouse,
            cart=cart,
            orders=orders,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        wave.validate()
        return wave
