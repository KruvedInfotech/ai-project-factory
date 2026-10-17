"""Load input types: trailer, stops, and pallet lines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .trailers import STRATEGIES, TEMPS, Trailer, get_trailer


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
class PalletLine:
    id: str
    sku: str
    weight_kg: float
    height_mm: int
    temp: str = "dry"
    quantity: int = 1

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each pallet needs an id")
        if not self.sku.strip():
            raise ValueError(f"Pallet '{self.id}' needs a sku")
        if self.weight_kg <= 0:
            raise ValueError(f"Pallet '{self.id}' weight must be positive")
        if self.height_mm < 1:
            raise ValueError(f"Pallet '{self.id}' height_mm must be at least 1")
        if self.temp not in TEMPS:
            raise ValueError(f"Pallet '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.quantity < 1:
            raise ValueError(f"Pallet '{self.id}' quantity must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sku": self.sku,
            "weight_kg": self.weight_kg,
            "height_mm": self.height_mm,
            "temp": self.temp,
            "quantity": self.quantity,
        }


@dataclass(frozen=True)
class Pallet:
    id: str
    sku: str
    weight_kg: float
    height_mm: int
    temp: str
    stop_id: str
    stop_seq: int
    stop_name: str


@dataclass(frozen=True)
class Stop:
    id: str
    seq: int
    name: str
    pallets: list[PalletLine]

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each stop needs an id")
        if self.seq < 1:
            raise ValueError(f"Stop '{self.id}' seq must be at least 1")
        if not self.name.strip():
            raise ValueError(f"Stop '{self.id}' needs a name")
        if not self.pallets:
            raise ValueError(f"Stop '{self.id}' has no pallets")
        seen: set[str] = set()
        for pallet in self.pallets:
            pallet.validate()
            if pallet.id in seen:
                raise ValueError(f"Duplicate pallet '{pallet.id}' on stop '{self.id}'")
            seen.add(pallet.id)

    def expand(self) -> list[Pallet]:
        pieces: list[Pallet] = []
        for line in self.pallets:
            for index in range(line.quantity):
                piece_id = line.id if line.quantity == 1 else f"{line.id}-{index + 1}"
                pieces.append(
                    Pallet(
                        id=piece_id,
                        sku=line.sku,
                        weight_kg=line.weight_kg,
                        height_mm=line.height_mm,
                        temp=line.temp,
                        stop_id=self.id,
                        stop_seq=self.seq,
                        stop_name=self.name,
                    )
                )
        return pieces

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "seq": self.seq,
            "name": self.name,
            "pallets": [item.as_dict() for item in self.pallets],
        }


@dataclass
class Load:
    trailer: Trailer
    stops: list[Stop]
    strategy: str = "auto"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.trailer.max_labor_min

    def validate(self) -> None:
        self.trailer.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.stops:
            raise ValueError("Load has no stops")
        stop_ids: set[str] = set()
        seqs: set[int] = set()
        pallet_ids: set[str] = set()
        for stop in self.stops:
            stop.validate()
            if stop.id in stop_ids:
                raise ValueError(f"Duplicate stop '{stop.id}'")
            stop_ids.add(stop.id)
            if stop.seq in seqs:
                raise ValueError(f"Duplicate stop seq {stop.seq}")
            seqs.add(stop.seq)
            for pallet in stop.expand():
                if pallet.id in pallet_ids:
                    raise ValueError(f"Duplicate pallet '{pallet.id}'")
                pallet_ids.add(pallet.id)

    def expand(self) -> list[Pallet]:
        pieces: list[Pallet] = []
        for stop in self.stops:
            pieces.extend(stop.expand())
        return pieces

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Load:
        stops: list[Stop] = []
        for raw in payload.get("stops") or []:
            lines: list[PalletLine] = []
            for item in raw.get("pallets") or []:
                lines.append(
                    PalletLine(
                        id=str(item.get("id", "")).strip(),
                        sku=str(item.get("sku", "")).strip(),
                        weight_kg=_as_float(item.get("weight_kg"), "weight_kg"),
                        height_mm=_as_int(item.get("height_mm"), "height_mm"),
                        temp=str(item.get("temp", "dry")).strip() or "dry",
                        quantity=_as_int(item.get("quantity", 1), "quantity", 1),
                    )
                )
            stops.append(
                Stop(
                    id=str(raw.get("id", "")).strip(),
                    seq=_as_int(raw.get("seq"), "seq"),
                    name=str(raw.get("name", "")).strip() or str(raw.get("id", "")).strip(),
                    pallets=lines,
                )
            )
        labor = payload.get("labor_minutes")
        load = cls(
            trailer=get_trailer(payload.get("trailer") or {}),
            stops=stops,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        load.validate()
        return load
