"""Wave input types: pallets and an outbound staging yard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .yards import STRATEGIES, TEMPS, Yard, get_yard


def _as_int(value: Any, field: str, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _as_optional_int(value: Any, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _as_float(value: Any, field: str, default: float | None = None) -> float:
    if value in (None, "") and default is not None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def _as_bool(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


@dataclass(frozen=True)
class PalletSpec:
    id: str
    carrier: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    priority: int = 2
    temp: str = "dry"
    door: int | None = None
    ready_min: int = 0
    depart_min: int | None = None

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each pallet needs an id")
        if not self.carrier.strip():
            raise ValueError(f"Pallet '{self.id}' needs a carrier")
        if self.priority < 1:
            raise ValueError(f"Pallet '{self.id}' priority must be at least 1")
        if self.temp not in TEMPS:
            raise ValueError(f"Pallet '{self.id}' temp must be {', '.join(TEMPS)}")
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0:
            raise ValueError(f"Pallet '{self.id}' dimensions must be positive")
        if self.weight_kg < 0:
            raise ValueError(f"Pallet '{self.id}' weight cannot be negative")
        if self.door is not None and self.door < 1:
            raise ValueError(f"Pallet '{self.id}' door must be at least 1")
        if self.ready_min < 0:
            raise ValueError(f"Pallet '{self.id}' ready_min cannot be negative")
        if self.depart_min is not None and self.depart_min < 1:
            raise ValueError(f"Pallet '{self.id}' depart_min must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "carrier": self.carrier,
            "priority": self.priority,
            "temp": self.temp,
            "door": self.door,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "ready_min": self.ready_min,
            "depart_min": self.depart_min,
        }


@dataclass
class Wave:
    yard: Yard
    pallets: list[PalletSpec]
    strategy: str = "auto"
    labor_minutes: int | None = None
    mix_carriers: bool = False
    mix_doors: bool = False
    allow_stack: bool = False

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.yard.max_labor_min

    def validate(self) -> None:
        self.yard.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.pallets:
            raise ValueError("Wave has no pallets")
        seen: set[str] = set()
        for pallet in self.pallets:
            pallet.validate()
            if pallet.id in seen:
                raise ValueError(f"Duplicate pallet id '{pallet.id}'")
            seen.add(pallet.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        yard = get_yard(payload.get("yard") or payload.get("floor") or {})
        pallets: list[PalletSpec] = []
        for raw in payload.get("pallets") or []:
            pallet_id = str(raw.get("id", "")).strip()
            pallets.append(
                PalletSpec(
                    id=pallet_id,
                    carrier=str(raw.get("carrier", "")).strip().upper(),
                    length_mm=_as_int(raw.get("length_mm", 1200), "length_mm", 1200),
                    width_mm=_as_int(raw.get("width_mm", 1000), "width_mm", 1000),
                    height_mm=_as_int(raw.get("height_mm", 1400), "height_mm", 1400),
                    weight_kg=_as_float(raw.get("weight_kg", 400), "weight_kg", 400.0),
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    door=_as_optional_int(raw.get("door"), "door"),
                    ready_min=_as_int(raw.get("ready_min", 0), "ready_min", 0),
                    depart_min=_as_optional_int(raw.get("depart_min"), "depart_min"),
                )
            )
        labor = payload.get("labor_minutes")
        wave = cls(
            yard=yard,
            pallets=pallets,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
            mix_carriers=_as_bool(payload.get("mix_carriers"), False),
            mix_doors=_as_bool(payload.get("mix_doors"), False),
            allow_stack=_as_bool(payload.get("allow_stack"), False),
        )
        wave.validate()
        return wave
