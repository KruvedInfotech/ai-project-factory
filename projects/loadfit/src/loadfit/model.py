"""Shipment input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .containers import Container, get_container


@dataclass(frozen=True)
class BoxSpec:
    sku: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    quantity: int = 1

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each carton needs a sku")
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0:
            raise ValueError(f"Carton '{self.sku}' dimensions must be positive")
        if self.weight_kg < 0:
            raise ValueError(f"Carton '{self.sku}' weight cannot be negative")
        if self.quantity < 1:
            raise ValueError(f"Carton '{self.sku}' quantity must be at least 1")

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm


@dataclass
class Shipment:
    container: Container
    boxes: list[BoxSpec]
    allow_rotation: bool = True
    this_side_up: bool = True

    def validate(self) -> None:
        if self.container.length_mm <= 0 or self.container.width_mm <= 0 or self.container.height_mm <= 0:
            raise ValueError("Container dimensions must be positive")
        if self.container.max_weight_kg <= 0:
            raise ValueError("Container payload must be positive")
        if not self.boxes:
            raise ValueError("Shipment has no cartons")
        seen: set[str] = set()
        for box in self.boxes:
            box.validate()
            if box.sku in seen:
                raise ValueError(f"Duplicate sku '{box.sku}'")
            seen.add(box.sku)

    def expand(self) -> list[BoxSpec]:
        """One spec per physical piece, sku kept, quantity forced to 1."""
        pieces: list[BoxSpec] = []
        for box in self.boxes:
            for _ in range(box.quantity):
                pieces.append(
                    BoxSpec(
                        sku=box.sku,
                        length_mm=box.length_mm,
                        width_mm=box.width_mm,
                        height_mm=box.height_mm,
                        weight_kg=box.weight_kg,
                        quantity=1,
                    )
                )
        return pieces

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Shipment:
        container = get_container(payload.get("container") or {})
        boxes = []
        for raw in payload.get("boxes") or []:
            boxes.append(
                BoxSpec(
                    sku=str(raw.get("sku", "")).strip(),
                    length_mm=int(raw["length_mm"]),
                    width_mm=int(raw["width_mm"]),
                    height_mm=int(raw["height_mm"]),
                    weight_kg=float(raw["weight_kg"]),
                    quantity=int(raw.get("quantity", 1)),
                )
            )
        shipment = cls(
            container=container,
            boxes=boxes,
            allow_rotation=bool(payload.get("allow_rotation", True)),
            this_side_up=bool(payload.get("this_side_up", True)),
        )
        shipment.validate()
        return shipment
