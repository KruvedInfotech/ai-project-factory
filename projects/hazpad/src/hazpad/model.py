"""Shipment input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .matrix import UN_PRESETS, normalize_class


@dataclass(frozen=True)
class Pad:
    id: str
    bays: int
    compartments: int = 1
    away_bays: int = 1
    empty_as_partition: bool = True

    def compartment_of(self, bay: int) -> int:
        if self.compartments <= 1:
            return 0
        split = max(1, self.bays // self.compartments)
        return min(bay // split, self.compartments - 1)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Pad id is required")
        if self.bays < 1:
            raise ValueError("Pad must have at least 1 bay")
        if self.compartments < 1:
            raise ValueError("compartments must be at least 1")
        if self.compartments > self.bays:
            raise ValueError("compartments cannot exceed bays")
        if self.away_bays < 0:
            raise ValueError("away_bays cannot be negative")


@dataclass(frozen=True)
class Lot:
    lot: str
    clazz: str
    kg: float
    un: str = ""
    description: str = ""
    limited_qty: bool = False
    foodstuff: bool = False

    def validate(self) -> None:
        if not self.lot.strip():
            raise ValueError("Each lot needs an id")
        normalize_class(self.clazz)
        if self.kg <= 0:
            raise ValueError(f"Lot '{self.lot}' weight must be positive")


@dataclass
class Shipment:
    pad: Pad
    lots: list[Lot]
    allow_limited_qty_ease: bool = True

    def validate(self) -> None:
        self.pad.validate()
        if not self.lots:
            raise ValueError("Shipment has no lots")
        seen: set[str] = set()
        for lot in self.lots:
            lot.validate()
            if lot.lot in seen:
                raise ValueError(f"Duplicate lot '{lot.lot}'")
            seen.add(lot.lot)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Shipment:
        if not isinstance(payload, dict):
            raise ValueError("Shipment must be an object")
        shipment = cls(
            pad=_pad(payload.get("pad") or {}),
            lots=[_lot(raw) for raw in payload.get("lots") or []],
            allow_limited_qty_ease=bool(payload.get("allow_limited_qty_ease", True)),
        )
        shipment.validate()
        return shipment


def _pad(raw: object) -> Pad:
    if not isinstance(raw, dict):
        raise ValueError("pad must be an object")
    return Pad(
        id=str(raw.get("id") or "PAD").strip(),
        bays=_int(raw.get("bays"), "bays", 8),
        compartments=_int(raw.get("compartments"), "compartments", 1),
        away_bays=_int(raw.get("away_bays"), "away_bays", 1),
        empty_as_partition=bool(raw.get("empty_as_partition", True)),
    )


def _lot(raw: object) -> Lot:
    if not isinstance(raw, dict):
        raise ValueError("Each lot must be an object")
    un = str(raw.get("un") or "").strip().upper()
    preset = UN_PRESETS.get(un, {})
    clazz_raw = raw.get("class") or preset.get("class")
    if not clazz_raw:
        raise ValueError("Each lot needs a class (or a known UN number)")
    foodstuff = bool(raw.get("foodstuff", False)) or str(clazz_raw).strip().upper() == "FOOD"
    description = str(raw.get("description") or preset.get("description") or "").strip()
    return Lot(
        lot=str(raw.get("lot") or "").strip(),
        clazz=normalize_class(str(clazz_raw)),
        kg=_number(raw.get("kg"), "kg"),
        un=un,
        description=description,
        limited_qty=bool(raw.get("limited_qty", False)),
        foodstuff=foodstuff,
    )


def _int(raw: object, field: str, default: int | None = None) -> int:
    if raw is None or raw == "":
        if default is None:
            raise ValueError(f"{field} is required")
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _number(raw: object, field: str) -> float:
    if raw is None or raw == "":
        raise ValueError(f"{field} is required")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
