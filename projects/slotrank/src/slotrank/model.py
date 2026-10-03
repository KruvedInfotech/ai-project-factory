"""Slotting-plan input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .warehouses import SLOT_TYPES, Warehouse, generate_locations, get_warehouse

STRATEGIES = ("auto", "velocity", "affinity", "heavy")
HEAVY_KG = 15.0


@dataclass(frozen=True)
class Location:
    id: str
    aisle: int
    bay: int
    slot_type: str
    max_cube: int
    allow_heavy: bool = False

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each location needs an id")
        if self.aisle < 1 or self.bay < 1:
            raise ValueError(f"Location '{self.id}' aisle and bay must be ≥ 1")
        if self.slot_type not in SLOT_TYPES:
            raise ValueError(
                f"Location '{self.id}' slot_type must be {', '.join(SLOT_TYPES)}"
            )
        if self.max_cube < 1:
            raise ValueError(f"Location '{self.id}' max_cube must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "aisle": self.aisle,
            "bay": self.bay,
            "slot_type": self.slot_type,
            "max_cube": self.max_cube,
            "allow_heavy": self.allow_heavy,
        }


@dataclass(frozen=True)
class Sku:
    sku: str
    picks: int
    cube: int
    weight_kg: float
    slot_type: str
    family: str = ""
    current: str = ""
    heavy: bool | None = None

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each SKU needs a sku")
        if self.picks < 0:
            raise ValueError(f"SKU '{self.sku}' picks cannot be negative")
        if self.cube < 1:
            raise ValueError(f"SKU '{self.sku}' cube must be at least 1")
        if self.weight_kg < 0:
            raise ValueError(f"SKU '{self.sku}' weight cannot be negative")
        if self.slot_type not in SLOT_TYPES:
            raise ValueError(
                f"SKU '{self.sku}' slot_type must be {', '.join(SLOT_TYPES)}"
            )

    @property
    def is_heavy(self) -> bool:
        if self.heavy is None:
            return self.weight_kg >= HEAVY_KG
        return self.heavy

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "picks": self.picks,
            "cube": self.cube,
            "weight_kg": self.weight_kg,
            "slot_type": self.slot_type,
            "family": self.family,
            "current": self.current,
            "heavy": self.is_heavy,
        }


@dataclass
class SlotPlan:
    warehouse: Warehouse
    skus: list[Sku]
    locations: list[Location]
    strategy: str = "auto"

    def validate(self) -> None:
        if self.warehouse.aisle_count < 1 or self.warehouse.bays_per_aisle < 1:
            raise ValueError("Warehouse layout must have at least one aisle and bay")
        if self.warehouse.golden_aisles < 1 or self.warehouse.golden_bays < 1:
            raise ValueError("Golden zone must have at least one aisle and bay")
        if self.warehouse.max_moves < 1:
            raise ValueError("max_moves must be at least 1")
        if self.warehouse.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")
        if self.warehouse.minutes_per_move < 1:
            raise ValueError("minutes_per_move must be at least 1")
        if self.warehouse.aisle_change_min < 0:
            raise ValueError("aisle_change_min cannot be negative")
        if not (0 < self.warehouse.a_share < 1):
            raise ValueError("a_share must be between 0 and 1")
        if not (0 < self.warehouse.b_share < 1):
            raise ValueError("b_share must be between 0 and 1")
        if self.warehouse.a_share + self.warehouse.b_share >= 1:
            raise ValueError("a_share + b_share must be less than 1")
        if not self.skus:
            raise ValueError("Slot plan has no SKUs")
        if not self.locations:
            raise ValueError("Slot plan has no locations")
        if self.strategy not in STRATEGIES:
            raise ValueError(
                f"Unknown strategy '{self.strategy}'. Known: {', '.join(STRATEGIES)}"
            )
        seen_skus: set[str] = set()
        seen_current: set[str] = set()
        for sku in self.skus:
            sku.validate()
            if sku.sku in seen_skus:
                raise ValueError(f"Duplicate sku '{sku.sku}'")
            seen_skus.add(sku.sku)
            if sku.current:
                if sku.current in seen_current:
                    raise ValueError(f"Two SKUs already sit in '{sku.current}'")
                seen_current.add(sku.current)
        seen_locs: set[str] = set()
        for loc in self.locations:
            loc.validate()
            if loc.id in seen_locs:
                raise ValueError(f"Duplicate location id '{loc.id}'")
            seen_locs.add(loc.id)
            if not self.warehouse.in_layout(loc.aisle, loc.bay):
                raise ValueError(
                    f"Location '{loc.id}' is outside the {self.warehouse.aisle_count}×"
                    f"{self.warehouse.bays_per_aisle} layout"
                )

    def location_map(self) -> dict[str, Location]:
        return {loc.id: loc for loc in self.locations}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SlotPlan:
        warehouse = get_warehouse(payload.get("warehouse") or {})
        skus: list[Sku] = []
        for raw in payload.get("skus") or []:
            heavy_raw = raw.get("heavy", None)
            heavy = None if heavy_raw is None else bool(heavy_raw)
            skus.append(
                Sku(
                    sku=str(raw.get("sku", "")).strip(),
                    picks=int(raw["picks"]),
                    cube=int(raw["cube"]),
                    weight_kg=float(raw.get("weight_kg", 0)),
                    slot_type=str(raw.get("slot_type", warehouse.default_slot_type)),
                    family=str(raw.get("family", "")).strip(),
                    current=str(raw.get("current", "")).strip(),
                    heavy=heavy,
                )
            )
        raw_locations = payload.get("locations")
        locations: list[Location] = []
        if raw_locations:
            for raw in raw_locations:
                locations.append(
                    Location(
                        id=str(raw.get("id", "")).strip(),
                        aisle=int(raw["aisle"]),
                        bay=int(raw["bay"]),
                        slot_type=str(raw.get("slot_type", warehouse.default_slot_type)),
                        max_cube=int(raw.get("max_cube", warehouse.default_max_cube)),
                        allow_heavy=bool(
                            raw.get("allow_heavy", warehouse.allows_heavy(int(raw["bay"])))
                        ),
                    )
                )
        else:
            locations = generate_locations(warehouse)
        plan = cls(
            warehouse=warehouse,
            skus=skus,
            locations=locations,
            strategy=str(payload.get("strategy", "auto")),
        )
        plan.validate()
        return plan
