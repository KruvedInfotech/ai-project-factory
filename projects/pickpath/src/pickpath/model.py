"""Pick-wave input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .warehouse import Warehouse, get_warehouse

STRATEGIES = ("auto", "s_shape", "return", "nearest")


@dataclass(frozen=True)
class Pick:
    sku: str
    aisle: int
    bay: int
    side: str
    qty: int = 1
    index: int = 0

    def validate_shape(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each pick needs a sku")
        if self.side.upper() not in {"L", "R"}:
            raise ValueError(f"Pick '{self.sku}' side must be L or R")
        if self.qty < 1:
            raise ValueError(f"Pick '{self.sku}' qty must be at least 1")
        if self.aisle < 1 or self.bay < 1:
            raise ValueError(f"Pick '{self.sku}' aisle and bay must be ≥ 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "aisle": self.aisle,
            "bay": self.bay,
            "side": self.side.upper(),
            "qty": self.qty,
            "index": self.index,
        }


@dataclass
class Wave:
    warehouse: Warehouse
    picks: list[Pick]
    strategy: str = "auto"

    def validate(self) -> None:
        if self.warehouse.aisle_count < 1 or self.warehouse.bays_per_aisle < 1:
            raise ValueError("Warehouse must have at least one aisle and one bay")
        if self.warehouse.bay_length_m <= 0 or self.warehouse.aisle_width_m <= 0:
            raise ValueError("Warehouse bay length and aisle width must be positive")
        if self.warehouse.aisle_pitch_m <= 0:
            raise ValueError("Warehouse aisle pitch must be positive")
        if self.warehouse.walk_speed_m_per_min <= 0:
            raise ValueError("Walk speed must be positive")
        if self.warehouse.handling_s < 0:
            raise ValueError("Handling time cannot be negative")
        if not self.picks:
            raise ValueError("Wave has no picks")
        if self.strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy '{self.strategy}'. Known: {', '.join(STRATEGIES)}")
        for pick in self.picks:
            pick.validate_shape()

    def split(self) -> tuple[list[Pick], list[dict[str, object]]]:
        routable: list[Pick] = []
        skipped: list[dict[str, object]] = []
        for pick in self.picks:
            if self.warehouse.in_range(pick.aisle, pick.bay):
                routable.append(pick)
            else:
                item = pick.as_dict()
                item["reason"] = (
                    f"location {pick.aisle}-{pick.bay} is outside "
                    f"{self.warehouse.aisle_count}×{self.warehouse.bays_per_aisle}"
                )
                skipped.append(item)
        return routable, skipped

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        warehouse = get_warehouse(payload.get("warehouse") or {})
        picks: list[Pick] = []
        for i, raw in enumerate(payload.get("picks") or []):
            picks.append(
                Pick(
                    sku=str(raw.get("sku", "")).strip(),
                    aisle=int(raw["aisle"]),
                    bay=int(raw["bay"]),
                    side=str(raw.get("side", "L")).strip().upper() or "L",
                    qty=int(raw.get("qty", raw.get("quantity", 1))),
                    index=i,
                )
            )
        wave = cls(
            warehouse=warehouse,
            picks=picks,
            strategy=str(payload.get("strategy", "auto")),
        )
        wave.validate()
        return wave
