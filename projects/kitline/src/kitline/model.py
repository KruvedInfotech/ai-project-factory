"""Wave input types: line, kit catalog, inventory, and build orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .lines import STRATEGIES, TEMPS, Line, get_line


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
class BomLine:
    sku: str
    quantity: int

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each BOM line needs a sku")
        if self.quantity < 1:
            raise ValueError(f"BOM '{self.sku}' quantity must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {"sku": self.sku, "quantity": self.quantity}


@dataclass(frozen=True)
class Kit:
    sku: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    temp: str
    bom: list[BomLine]

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    @property
    def bom_units(self) -> int:
        return sum(line.quantity for line in self.bom)

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each kit needs a sku")
        if self.length_mm < 1 or self.width_mm < 1 or self.height_mm < 1:
            raise ValueError(f"Kit '{self.sku}' dimensions must be at least 1 mm")
        if self.weight_kg <= 0:
            raise ValueError(f"Kit '{self.sku}' weight must be positive")
        if self.temp not in TEMPS:
            raise ValueError(f"Kit '{self.sku}' temp must be {', '.join(TEMPS)}")
        if not self.bom:
            raise ValueError(f"Kit '{self.sku}' has no BOM")
        seen: set[str] = set()
        for line in self.bom:
            line.validate()
            if line.sku in seen:
                raise ValueError(f"Kit '{self.sku}' has duplicate BOM sku '{line.sku}'")
            seen.add(line.sku)

    def need_for(self, quantity: int) -> dict[str, int]:
        return {line.sku: line.quantity * quantity for line in self.bom}

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "temp": self.temp,
            "bom": [item.as_dict() for item in self.bom],
        }


@dataclass(frozen=True)
class Build:
    id: str
    kit_sku: str
    quantity: int
    priority: int

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each build needs an id")
        if not self.kit_sku.strip():
            raise ValueError(f"Build '{self.id}' needs a kit_sku")
        if self.quantity < 1:
            raise ValueError(f"Build '{self.id}' quantity must be at least 1")
        if self.priority < 1:
            raise ValueError(f"Build '{self.id}' priority must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kit_sku": self.kit_sku,
            "quantity": self.quantity,
            "priority": self.priority,
        }


@dataclass
class Wave:
    line: Line
    kits: list[Kit]
    inventory: dict[str, int]
    builds: list[Build]
    strategy: str = "auto"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.line.max_labor_min

    def kit_map(self) -> dict[str, Kit]:
        return {kit.sku: kit for kit in self.kits}

    def validate(self) -> None:
        self.line.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.kits:
            raise ValueError("Wave has no kits")
        if not self.builds:
            raise ValueError("Wave has no builds")
        seen_kits: set[str] = set()
        for kit in self.kits:
            kit.validate()
            if kit.sku in seen_kits:
                raise ValueError(f"Duplicate kit '{kit.sku}'")
            seen_kits.add(kit.sku)
        for sku, on_hand in self.inventory.items():
            if not sku.strip():
                raise ValueError("Each inventory row needs a sku")
            if on_hand < 0:
                raise ValueError(f"Inventory '{sku}' on_hand cannot be negative")
        seen_builds: set[str] = set()
        known = self.kit_map()
        for build in self.builds:
            build.validate()
            if build.id in seen_builds:
                raise ValueError(f"Duplicate build '{build.id}'")
            seen_builds.add(build.id)
            if build.kit_sku not in known:
                raise ValueError(f"Build '{build.id}' kit '{build.kit_sku}' is not in the catalog")

    def as_dict(self) -> dict[str, object]:
        return {
            "line": self.line.as_dict(),
            "strategy": self.strategy,
            "labor_minutes": self.labor_cap(),
            "kits": [kit.as_dict() for kit in self.kits],
            "inventory": [{"sku": sku, "on_hand": qty} for sku, qty in self.inventory.items()],
            "builds": [build.as_dict() for build in self.builds],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        kits: list[Kit] = []
        for raw in payload.get("kits") or []:
            bom: list[BomLine] = []
            for item in raw.get("bom") or []:
                bom.append(
                    BomLine(
                        sku=str(item.get("sku", "")).strip(),
                        quantity=_as_int(item.get("quantity", 1), "bom quantity", 1),
                    )
                )
            kits.append(
                Kit(
                    sku=str(raw.get("sku", "")).strip(),
                    length_mm=_as_int(raw.get("length_mm"), "length_mm"),
                    width_mm=_as_int(raw.get("width_mm"), "width_mm"),
                    height_mm=_as_int(raw.get("height_mm"), "height_mm"),
                    weight_kg=_as_float(raw.get("weight_kg"), "weight_kg"),
                    temp=str(raw.get("temp", "ambient")).strip() or "ambient",
                    bom=bom,
                )
            )
        inventory: dict[str, int] = {}
        for raw in payload.get("inventory") or []:
            sku = str(raw.get("sku", "")).strip()
            if sku in inventory:
                raise ValueError(f"Duplicate inventory sku '{sku}'")
            inventory[sku] = _as_int(raw.get("on_hand"), "on_hand")
        builds: list[Build] = []
        for raw in payload.get("builds") or []:
            builds.append(
                Build(
                    id=str(raw.get("id", "")).strip(),
                    kit_sku=str(raw.get("kit_sku", "")).strip(),
                    quantity=_as_int(raw.get("quantity", 1), "quantity", 1),
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                )
            )
        labor = payload.get("labor_minutes")
        wave = cls(
            line=get_line(payload.get("line") or {}),
            kits=kits,
            inventory=inventory,
            builds=builds,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        wave.validate()
        return wave
