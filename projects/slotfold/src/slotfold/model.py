"""Honeycomb fold-plan input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .warehouse import KINDS, TEMPS, Warehouse, get_warehouse


def location_id(aisle: str, bay: int, level: int) -> str:
    return f"{aisle}-{bay:02d}-{level}"


@dataclass(frozen=True)
class Location:
    aisle: str
    bay: int
    level: int
    sku: str
    qty: int
    max_qty: int
    kind: str = "reserve"
    temp: str = "dry"
    lot: str = ""
    unit_kg: float = 1.0
    max_kg: float | None = None
    locked: bool = False
    hold: bool = False
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", location_id(self.aisle, self.bay, self.level))

    def validate(self) -> None:
        if not self.aisle.strip():
            raise ValueError("Each location needs an aisle")
        if self.bay < 1 or self.level < 1:
            raise ValueError(f"Location '{self.id}' bay and level must be at least 1")
        if not self.sku.strip():
            raise ValueError(f"Location '{self.id}' needs a sku")
        if self.qty < 1:
            raise ValueError(f"Location '{self.id}' qty must be at least 1")
        if self.max_qty < 1:
            raise ValueError(f"Location '{self.id}' max_qty must be at least 1")
        if self.qty > self.max_qty:
            raise ValueError(f"Location '{self.id}' qty cannot exceed max_qty")
        if self.kind not in KINDS:
            raise ValueError(f"Location '{self.id}' kind must be one of {KINDS}")
        if self.temp not in TEMPS:
            raise ValueError(f"Location '{self.id}' temp must be one of {TEMPS}")
        if self.unit_kg < 0:
            raise ValueError(f"Location '{self.id}' unit_kg cannot be negative")
        if self.max_kg is not None and self.max_kg <= 0:
            raise ValueError(f"Location '{self.id}' max_kg must be positive")
        if self.max_kg is not None and self.qty * self.unit_kg - self.max_kg > 1e-9:
            raise ValueError(f"Location '{self.id}' weight exceeds max_kg")

    @property
    def fill(self) -> float:
        return self.qty / self.max_qty if self.max_qty else 0.0

    @property
    def family(self) -> tuple[str, str, str]:
        return (self.sku, self.lot, self.temp)

    def remaining_capacity(self, qty: int | None = None) -> int:
        current = self.qty if qty is None else qty
        by_qty = self.max_qty - current
        if self.max_kg is None or self.unit_kg <= 0:
            return max(0, by_qty)
        used_kg = current * self.unit_kg
        by_kg = int((self.max_kg - used_kg + 1e-9) / self.unit_kg)
        return max(0, min(by_qty, by_kg))

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "aisle": self.aisle,
            "bay": self.bay,
            "level": self.level,
            "sku": self.sku,
            "lot": self.lot,
            "qty": self.qty,
            "max_qty": self.max_qty,
            "unit_kg": self.unit_kg,
            "max_kg": self.max_kg,
            "temp": self.temp,
            "kind": self.kind,
            "locked": self.locked,
            "hold": self.hold,
            "fill": round(self.fill, 4),
        }


@dataclass
class FoldPlan:
    warehouse: Warehouse
    locations: list[Location]
    labor_minutes: int = 48
    minutes_per_move: int = 4
    keep_last_pick_face: bool = True

    def validate(self) -> None:
        if self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if self.minutes_per_move < 1:
            raise ValueError("minutes_per_move must be at least 1")
        if not self.locations:
            raise ValueError("Plan has no locations")
        seen: set[str] = set()
        for loc in self.locations:
            loc.validate()
            if not self.warehouse.contains(loc.aisle, loc.bay, loc.level):
                raise ValueError(f"Location '{loc.id}' is outside the warehouse grid")
            if loc.id in seen:
                raise ValueError(f"Duplicate location '{loc.id}'")
            seen.add(loc.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FoldPlan:
        locations = []
        for raw in payload.get("locations") or []:
            max_kg = raw.get("max_kg")
            loc_id = str(raw.get("id") or "").strip()
            aisle = str(raw.get("aisle") or "").strip().upper()
            bay = int(raw["bay"])
            level = int(raw["level"])
            locations.append(
                Location(
                    aisle=aisle,
                    bay=bay,
                    level=level,
                    sku=str(raw.get("sku") or "").strip(),
                    qty=int(raw["qty"]),
                    max_qty=int(raw["max_qty"]),
                    kind=str(raw.get("kind") or "reserve").strip().lower(),
                    temp=str(raw.get("temp") or "dry").strip().lower(),
                    lot=str(raw.get("lot") or "").strip(),
                    unit_kg=float(raw.get("unit_kg", 1.0)),
                    max_kg=float(max_kg) if max_kg is not None else None,
                    locked=bool(raw.get("locked", False)),
                    hold=bool(raw.get("hold", False)),
                    id=loc_id or location_id(aisle, bay, level),
                )
            )
        plan = cls(
            warehouse=get_warehouse(payload.get("warehouse") or {}),
            locations=locations,
            labor_minutes=int(payload.get("labor_minutes", 48)),
            minutes_per_move=int(payload.get("minutes_per_move", 4)),
            keep_last_pick_face=bool(payload.get("keep_last_pick_face", True)),
        )
        plan.validate()
        return plan
