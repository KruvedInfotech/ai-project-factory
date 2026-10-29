"""Pack-job input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import TEMPS, Catalog, get_catalog


@dataclass(frozen=True)
class Item:
    order_id: str
    sku: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    quantity: int = 1
    temp: str = "dry"

    def validate(self) -> None:
        if not self.order_id.strip():
            raise ValueError("Each item needs an order_id")
        if not self.sku.strip():
            raise ValueError("Each item needs a sku")
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0:
            raise ValueError(f"Item '{self.sku}' dimensions must be positive")
        if self.weight_kg < 0:
            raise ValueError(f"Item '{self.sku}' weight cannot be negative")
        if self.quantity < 1:
            raise ValueError(f"Item '{self.sku}' quantity must be at least 1")
        if self.temp not in TEMPS:
            raise ValueError(f"Item '{self.sku}' temp must be one of {TEMPS}")

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    def as_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "sku": self.sku,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "quantity": self.quantity,
            "temp": self.temp,
        }


@dataclass(frozen=True)
class Piece:
    order_id: str
    sku: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    temp: str
    index: int

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    @property
    def key(self) -> tuple:
        return (
            self.order_id,
            self.sku,
            self.length_mm,
            self.width_mm,
            self.height_mm,
            self.weight_kg,
            self.temp,
        )


@dataclass
class PackJob:
    catalog: Catalog
    items: list[Item]
    labor_minutes: int = 60
    minutes_per_piece: int = 1
    minutes_per_carton: int = 2
    allow_rotation: bool = True
    this_side_up: bool = True

    def validate(self) -> None:
        if self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if self.minutes_per_piece < 1:
            raise ValueError("minutes_per_piece must be at least 1")
        if self.minutes_per_carton < 1:
            raise ValueError("minutes_per_carton must be at least 1")
        if not self.items:
            raise ValueError("Job has no items")
        if not self.catalog.cartons:
            raise ValueError("Catalog has no shipper cartons")
        seen: set[tuple[str, str]] = set()
        for item in self.items:
            item.validate()
            key = (item.order_id, item.sku)
            if key in seen:
                raise ValueError(f"Duplicate sku '{item.sku}' on order '{item.order_id}'")
            seen.add(key)

    def expand(self) -> list[Piece]:
        pieces: list[Piece] = []
        index = 0
        for item in self.items:
            for _ in range(item.quantity):
                pieces.append(
                    Piece(
                        order_id=item.order_id,
                        sku=item.sku,
                        length_mm=item.length_mm,
                        width_mm=item.width_mm,
                        height_mm=item.height_mm,
                        weight_kg=item.weight_kg,
                        temp=item.temp,
                        index=index,
                    )
                )
                index += 1
        return pieces

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PackJob:
        items = []
        for raw in payload.get("items") or []:
            items.append(
                Item(
                    order_id=str(raw.get("order_id") or "").strip(),
                    sku=str(raw.get("sku") or "").strip(),
                    length_mm=int(raw["length_mm"]),
                    width_mm=int(raw["width_mm"]),
                    height_mm=int(raw["height_mm"]),
                    weight_kg=float(raw["weight_kg"]),
                    quantity=int(raw.get("quantity", 1)),
                    temp=str(raw.get("temp") or "dry").strip().lower(),
                )
            )
        job = cls(
            catalog=get_catalog(payload.get("catalog") or {}),
            items=items,
            labor_minutes=int(payload.get("labor_minutes", 60)),
            minutes_per_piece=int(payload.get("minutes_per_piece", 1)),
            minutes_per_carton=int(payload.get("minutes_per_carton", 2)),
            allow_rotation=bool(payload.get("allow_rotation", True)),
            this_side_up=bool(payload.get("this_side_up", True)),
        )
        job.validate()
        return job
