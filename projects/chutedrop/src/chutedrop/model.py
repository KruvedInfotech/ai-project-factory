"""Wave input types: sortation bank and destination cartons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .banks import STRATEGIES, TEMPS, Bank, get_bank


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
class Carton:
    id: str
    dest: str
    carrier: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    temp: str
    priority: int

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each carton needs an id")
        if not self.dest.strip():
            raise ValueError(f"Carton '{self.id}' needs a dest")
        if not self.carrier.strip():
            raise ValueError(f"Carton '{self.id}' needs a carrier")
        if self.length_mm < 1 or self.width_mm < 1 or self.height_mm < 1:
            raise ValueError(f"Carton '{self.id}' dimensions must be at least 1 mm")
        if self.weight_kg <= 0:
            raise ValueError(f"Carton '{self.id}' weight must be positive")
        if self.temp not in TEMPS:
            raise ValueError(f"Carton '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.priority < 1:
            raise ValueError(f"Carton '{self.id}' priority must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "dest": self.dest,
            "carrier": self.carrier,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "temp": self.temp,
            "priority": self.priority,
        }


@dataclass
class Wave:
    bank: Bank
    cartons: list[Carton]
    strategy: str = "auto"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.bank.max_labor_min

    def validate(self) -> None:
        self.bank.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.cartons:
            raise ValueError("Wave has no cartons")
        seen: set[str] = set()
        for carton in self.cartons:
            carton.validate()
            if carton.id in seen:
                raise ValueError(f"Duplicate carton '{carton.id}'")
            seen.add(carton.id)

    def as_dict(self) -> dict[str, object]:
        return {
            "bank": self.bank.as_dict(),
            "strategy": self.strategy,
            "labor_minutes": self.labor_cap(),
            "cartons": [carton.as_dict() for carton in self.cartons],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        cartons: list[Carton] = []
        for raw in payload.get("cartons") or []:
            cartons.append(
                Carton(
                    id=str(raw.get("id", "")).strip(),
                    dest=str(raw.get("dest", "")).strip(),
                    carrier=str(raw.get("carrier", "")).strip() or "OWN",
                    length_mm=_as_int(raw.get("length_mm"), "length_mm"),
                    width_mm=_as_int(raw.get("width_mm"), "width_mm"),
                    height_mm=_as_int(raw.get("height_mm"), "height_mm"),
                    weight_kg=_as_float(raw.get("weight_kg"), "weight_kg"),
                    temp=str(raw.get("temp", "ambient")).strip() or "ambient",
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                )
            )
        labor = payload.get("labor_minutes")
        wave = cls(
            bank=get_bank(payload.get("bank") or {}),
            cartons=cartons,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        wave.validate()
        return wave
