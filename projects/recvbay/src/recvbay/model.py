"""Inbound board: ASNs and a receiving dock."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .docks import STRATEGIES, TEMPS, UNLOADS, Dock, get_dock


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
class LoadSpec:
    id: str
    vendor: str
    pallets: int
    priority: int = 2
    temp: str = "dry"
    unload: str = "live"
    floor_loaded: bool = False
    door: int | None = None
    eta_min: int = 0
    appointment_min: int | None = None
    trailer_height_mm: int = 4000

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each load needs an id")
        if not self.vendor.strip():
            raise ValueError(f"Load '{self.id}' needs a vendor")
        if self.pallets < 1:
            raise ValueError(f"Load '{self.id}' pallets must be at least 1")
        if self.priority < 1:
            raise ValueError(f"Load '{self.id}' priority must be at least 1")
        if self.temp not in TEMPS:
            raise ValueError(f"Load '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.unload not in UNLOADS:
            raise ValueError(f"Load '{self.id}' unload must be live or drop")
        if self.door is not None and self.door < 1:
            raise ValueError(f"Load '{self.id}' door must be at least 1")
        if self.eta_min < 0:
            raise ValueError(f"Load '{self.id}' eta_min cannot be negative")
        if self.appointment_min is not None and self.appointment_min < 1:
            raise ValueError(f"Load '{self.id}' appointment_min must be at least 1")
        if self.trailer_height_mm < 1:
            raise ValueError(f"Load '{self.id}' trailer_height_mm must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "vendor": self.vendor,
            "priority": self.priority,
            "temp": self.temp,
            "pallets": self.pallets,
            "unload": self.unload,
            "floor_loaded": self.floor_loaded,
            "door": self.door,
            "eta_min": self.eta_min,
            "appointment_min": self.appointment_min,
            "trailer_height_mm": self.trailer_height_mm,
        }


@dataclass
class Board:
    dock: Dock
    loads: list[LoadSpec]
    strategy: str = "auto"
    labor_minutes: int | None = None
    mix_doors: bool = False
    mix_vendors: bool = True

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.dock.max_labor_min

    def validate(self) -> None:
        self.dock.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.loads:
            raise ValueError("Board has no loads")
        seen: set[str] = set()
        for load in self.loads:
            load.validate()
            if load.id in seen:
                raise ValueError(f"Duplicate load id '{load.id}'")
            seen.add(load.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Board:
        dock = get_dock(payload.get("dock") or payload.get("yard") or {})
        loads: list[LoadSpec] = []
        for raw in payload.get("loads") or []:
            load_id = str(raw.get("id", "")).strip()
            loads.append(
                LoadSpec(
                    id=load_id,
                    vendor=str(raw.get("vendor", "")).strip().upper(),
                    pallets=_as_int(raw.get("pallets", 1), "pallets", 1),
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    unload=str(raw.get("unload", "live")).strip() or "live",
                    floor_loaded=_as_bool(raw.get("floor_loaded"), False),
                    door=_as_optional_int(raw.get("door"), "door"),
                    eta_min=_as_int(raw.get("eta_min", 0), "eta_min", 0),
                    appointment_min=_as_optional_int(raw.get("appointment_min"), "appointment_min"),
                    trailer_height_mm=_as_int(
                        raw.get("trailer_height_mm", 4000), "trailer_height_mm", 4000
                    ),
                )
            )
        labor = payload.get("labor_minutes")
        board = cls(
            dock=dock,
            loads=loads,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
            mix_doors=_as_bool(payload.get("mix_doors"), False),
            mix_vendors=_as_bool(payload.get("mix_vendors"), True),
        )
        board.validate()
        return board
