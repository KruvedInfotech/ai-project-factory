"""Wave input types: inbound pallets, locations, and putaway policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .policies import (
    LOCATION_TYPES,
    STRATEGIES,
    TEMPS,
    VELOCITIES,
    Policy,
    get_policy,
)


def _opt_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


@dataclass(frozen=True)
class Pallet:
    id: str
    sku: str
    qty: int
    height_mm: int
    weight_kg: float
    pallets: int = 1
    temp: str = "dry"
    velocity: str = "B"
    priority: int = 2
    home_aisle: int | None = None

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each pallet needs an id")
        if not self.sku.strip():
            raise ValueError(f"Pallet '{self.id}' needs a sku")
        if self.qty < 1:
            raise ValueError(f"Pallet '{self.id}' qty must be at least 1")
        if self.pallets < 1:
            raise ValueError(f"Pallet '{self.id}' pallets must be at least 1")
        if self.height_mm <= 0:
            raise ValueError(f"Pallet '{self.id}' height_mm must be positive")
        if self.weight_kg <= 0:
            raise ValueError(f"Pallet '{self.id}' weight_kg must be positive")
        if self.temp not in TEMPS:
            raise ValueError(f"Pallet '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.velocity not in VELOCITIES:
            raise ValueError(f"Pallet '{self.id}' velocity must be {', '.join(VELOCITIES)}")
        if self.priority < 1:
            raise ValueError(f"Pallet '{self.id}' priority must be at least 1")
        if self.home_aisle is not None and self.home_aisle < 1:
            raise ValueError(f"Pallet '{self.id}' home_aisle must be at least 1")

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "sku": self.sku,
            "qty": self.qty,
            "pallets": self.pallets,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "temp": self.temp,
            "velocity": self.velocity,
            "priority": self.priority,
        }
        if self.home_aisle is not None:
            data["home_aisle"] = self.home_aisle
        return data


@dataclass(frozen=True)
class Location:
    id: str
    zone: str
    type: str
    aisle: int
    bay: int
    level: int
    temp: str
    max_pallets: int
    max_height_mm: int
    max_weight_kg: float
    occupied_pallets: int = 0
    occupied_weight_kg: float = 0.0
    sku: str = ""
    blocked: bool = False

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each location needs an id")
        if self.zone not in VELOCITIES:
            raise ValueError(f"Location '{self.id}' zone must be {', '.join(VELOCITIES)}")
        if self.type not in LOCATION_TYPES:
            raise ValueError(f"Location '{self.id}' type must be {', '.join(LOCATION_TYPES)}")
        if min(self.aisle, self.bay, self.level) < 1:
            raise ValueError(f"Location '{self.id}' aisle, bay, and level must be at least 1")
        if self.temp not in TEMPS:
            raise ValueError(f"Location '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.max_pallets < 1:
            raise ValueError(f"Location '{self.id}' max_pallets must be at least 1")
        if self.max_height_mm <= 0:
            raise ValueError(f"Location '{self.id}' max_height_mm must be positive")
        if self.max_weight_kg <= 0:
            raise ValueError(f"Location '{self.id}' max_weight_kg must be positive")
        if self.occupied_pallets < 0:
            raise ValueError(f"Location '{self.id}' occupied_pallets cannot be negative")
        if self.occupied_pallets > self.max_pallets:
            raise ValueError(f"Location '{self.id}' occupied_pallets exceeds max_pallets")
        if self.occupied_weight_kg < 0:
            raise ValueError(f"Location '{self.id}' occupied_weight_kg cannot be negative")
        if self.occupied_weight_kg - self.max_weight_kg > 1e-9:
            raise ValueError(f"Location '{self.id}' occupied_weight_kg exceeds max_weight_kg")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "zone": self.zone,
            "type": self.type,
            "aisle": self.aisle,
            "bay": self.bay,
            "level": self.level,
            "temp": self.temp,
            "max_pallets": self.max_pallets,
            "max_height_mm": self.max_height_mm,
            "max_weight_kg": self.max_weight_kg,
            "occupied_pallets": self.occupied_pallets,
            "occupied_weight_kg": self.occupied_weight_kg,
            "sku": self.sku,
            "blocked": self.blocked,
        }


@dataclass
class Wave:
    policy: Policy
    inbound: list[Pallet]
    locations: list[Location]
    strategy: str = "priority"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.policy.max_labor_min

    def validate(self) -> None:
        self.policy.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.inbound:
            raise ValueError("Wave has no inbound pallets")
        if not self.locations:
            raise ValueError("Wave has no locations")
        seen_pallets: set[str] = set()
        for pallet in self.inbound:
            pallet.validate()
            if pallet.id in seen_pallets:
                raise ValueError(f"Duplicate pallet '{pallet.id}'")
            seen_pallets.add(pallet.id)
        seen_locations: set[str] = set()
        for location in self.locations:
            location.validate()
            if location.id in seen_locations:
                raise ValueError(f"Duplicate location '{location.id}'")
            seen_locations.add(location.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        inbound: list[Pallet] = []
        for raw in payload.get("inbound") or []:
            inbound.append(
                Pallet(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    qty=int(raw.get("qty", 0)),
                    pallets=int(raw.get("pallets", 1)),
                    height_mm=int(raw.get("height_mm", 0)),
                    weight_kg=float(raw.get("weight_kg", 0)),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    velocity=str(raw.get("velocity", "B")).strip() or "B",
                    priority=int(raw.get("priority", 2)),
                    home_aisle=_opt_int(raw.get("home_aisle")),
                )
            )
        locations: list[Location] = []
        for raw in payload.get("locations") or []:
            locations.append(
                Location(
                    id=str(raw.get("id", "")).strip(),
                    zone=str(raw.get("zone", "")).strip(),
                    type=str(raw.get("type", "reserve")).strip() or "reserve",
                    aisle=int(raw.get("aisle", 0)),
                    bay=int(raw.get("bay", 0)),
                    level=int(raw.get("level", 0)),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    max_pallets=int(raw.get("max_pallets", 0)),
                    max_height_mm=int(raw.get("max_height_mm", 0)),
                    max_weight_kg=float(raw.get("max_weight_kg", 0)),
                    occupied_pallets=int(raw.get("occupied_pallets", 0)),
                    occupied_weight_kg=float(raw.get("occupied_weight_kg", 0)),
                    sku=str(raw.get("sku", "")).strip(),
                    blocked=bool(raw.get("blocked", False)),
                )
            )
        labor = payload.get("labor_minutes")
        wave = cls(
            policy=get_policy(payload.get("policy") or {}),
            inbound=inbound,
            locations=locations,
            strategy=str(payload.get("strategy", "priority")).strip() or "priority",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        wave.validate()
        return wave
