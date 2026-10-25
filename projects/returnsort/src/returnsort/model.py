"""Returns batch input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .floors import TEMPS, Floor, get_floor

GRADES = ("sellable", "repairable", "damaged", "suspect", "vendor")
REASONS = (
    "unwanted",
    "wrong-item",
    "fit",
    "opened",
    "defective",
    "missing-parts",
    "damaged",
    "crushed",
    "wet",
    "rma",
    "vendor",
    "hold",
    "quality",
    "recall",
)
VELOCITIES = ("A", "B", "C")
DISPOSITIONS = ("restock", "refurb", "scrap", "rma", "hold")

RESTOCK_REASONS = {"unwanted", "wrong-item", "fit"}
REFURB_REASONS = {"opened", "defective", "missing-parts"}
SCRAP_REASONS = {"damaged", "crushed", "wet"}
RMA_REASONS = {"rma", "vendor"}
HOLD_REASONS = {"hold", "quality", "recall"}

DEFAULT_MINUTES = {
    "restock": 2,
    "refurb": 6,
    "scrap": 1,
    "rma": 3,
    "hold": 2,
}


@dataclass(frozen=True)
class ReturnUnit:
    ticket: str
    sku: str
    reason: str
    grade: str
    temp: str = "dry"
    velocity: str = "B"
    quantity: int = 1
    minutes: int | None = None
    remaining_life_days: int | None = None

    def validate(self) -> None:
        if not self.ticket.strip():
            raise ValueError("Each return needs a ticket")
        if not self.sku.strip():
            raise ValueError(f"Return '{self.ticket}' needs a sku")
        if self.reason not in REASONS:
            raise ValueError(f"Return '{self.ticket}' reason must be one of {REASONS}")
        if self.grade not in GRADES:
            raise ValueError(f"Return '{self.ticket}' grade must be one of {GRADES}")
        if self.temp not in TEMPS:
            raise ValueError(f"Return '{self.ticket}' temp must be one of {TEMPS}")
        if self.velocity not in VELOCITIES:
            raise ValueError(f"Return '{self.ticket}' velocity must be one of {VELOCITIES}")
        if self.quantity < 1:
            raise ValueError(f"Return '{self.ticket}' quantity must be at least 1")
        if self.minutes is not None and self.minutes < 1:
            raise ValueError(f"Return '{self.ticket}' minutes must be at least 1")
        if self.remaining_life_days is not None and self.remaining_life_days < 0:
            raise ValueError(f"Return '{self.ticket}' remaining_life_days cannot be negative")

    @property
    def disposition(self) -> str:
        if self.grade == "vendor" or self.reason in RMA_REASONS:
            return "rma"
        if self.grade == "suspect" or self.reason in HOLD_REASONS:
            return "hold"
        if self.grade == "damaged" or self.reason in SCRAP_REASONS:
            return "scrap"
        if self.grade == "repairable" or self.reason in REFURB_REASONS:
            if self.reason == "opened" and self.grade == "sellable":
                return "restock"
            return "refurb"
        if self.grade == "sellable" or self.reason in RESTOCK_REASONS:
            return "restock"
        return "hold"

    def labor_minutes(self) -> int:
        if self.minutes is not None:
            return self.minutes
        return DEFAULT_MINUTES[self.disposition]


@dataclass
class ReturnBatch:
    floor: Floor
    units: list[ReturnUnit]
    labor_minutes: int = 90

    def validate(self) -> None:
        if self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.floor.lanes:
            raise ValueError("Floor has no lanes")
        if not self.units:
            raise ValueError("Batch has no returns")
        seen: set[str] = set()
        for unit in self.units:
            unit.validate()
            if unit.ticket in seen:
                raise ValueError(f"Duplicate ticket '{unit.ticket}'")
            seen.add(unit.ticket)

    def expand(self) -> list[ReturnUnit]:
        """One spec per physical piece; ticket kept, quantity forced to 1."""
        pieces: list[ReturnUnit] = []
        for unit in self.units:
            for _ in range(unit.quantity):
                pieces.append(
                    ReturnUnit(
                        ticket=unit.ticket,
                        sku=unit.sku,
                        reason=unit.reason,
                        grade=unit.grade,
                        temp=unit.temp,
                        velocity=unit.velocity,
                        quantity=1,
                        minutes=unit.minutes,
                        remaining_life_days=unit.remaining_life_days,
                    )
                )
        return pieces

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReturnBatch:
        units = []
        for raw in payload.get("units") or []:
            minutes = raw.get("minutes")
            life = raw.get("remaining_life_days")
            units.append(
                ReturnUnit(
                    ticket=str(raw.get("ticket", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    reason=str(raw.get("reason", "")).strip(),
                    grade=str(raw.get("grade", "")).strip(),
                    temp=str(raw.get("temp", "dry")).strip(),
                    velocity=str(raw.get("velocity", "B")).strip().upper(),
                    quantity=int(raw.get("quantity", 1)),
                    minutes=int(minutes) if minutes is not None else None,
                    remaining_life_days=int(life) if life is not None else None,
                )
            )
        batch = cls(
            floor=get_floor(payload.get("floor") or {}),
            units=units,
            labor_minutes=int(payload.get("labor_minutes", 90)),
        )
        batch.validate()
        return batch
