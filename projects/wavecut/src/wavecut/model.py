"""Wave-plan input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .shifts import Shift, get_shift, parse_hhmm

STRATEGIES = ("auto", "cutoff", "zone", "cube")
ZONES = ("ambient", "chill", "freezer", "bulk")
CHANNELS = ("store", "ecom", "wholesale", "other")


@dataclass(frozen=True)
class Order:
    id: str
    channel: str
    zone: str
    lines: int
    units: int
    cube_m3: float
    pick_min: int
    cutoff: str
    priority: int = 2

    @property
    def cutoff_min(self) -> int:
        return parse_hhmm(self.cutoff)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each order needs an id")
        if self.channel not in CHANNELS:
            raise ValueError(
                f"Order '{self.id}' channel must be one of: {', '.join(CHANNELS)}"
            )
        if self.zone not in ZONES:
            raise ValueError(f"Order '{self.id}' zone must be one of: {', '.join(ZONES)}")
        if self.lines < 1:
            raise ValueError(f"Order '{self.id}' needs at least 1 line")
        if self.units < 1:
            raise ValueError(f"Order '{self.id}' needs at least 1 unit")
        if self.cube_m3 <= 0:
            raise ValueError(f"Order '{self.id}' cube must be positive")
        if self.pick_min < 1:
            raise ValueError(f"Order '{self.id}' pick time must be at least 1 minute")
        if self.priority < 1:
            raise ValueError(f"Order '{self.id}' priority must be ≥ 1 (1 is first)")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "channel": self.channel,
            "zone": self.zone,
            "lines": self.lines,
            "units": self.units,
            "cube_m3": self.cube_m3,
            "pick_min": self.pick_min,
            "cutoff": self.cutoff,
            "priority": self.priority,
        }


@dataclass
class WavePlan:
    shift: Shift
    orders: list[Order]
    strategy: str = "auto"

    def validate(self) -> None:
        if self.shift.close_min <= self.shift.open_min:
            raise ValueError("Shift close must be after open")
        if self.shift.wave_min < 1:
            raise ValueError("Wave length must be at least 1 minute")
        if not self.shift.slots():
            raise ValueError("Shift is shorter than one wave")
        if self.shift.max_orders < 1:
            raise ValueError("max_orders must be at least 1")
        if self.shift.max_lines < 1:
            raise ValueError("max_lines must be at least 1")
        if self.shift.max_cube_m3 <= 0:
            raise ValueError("max_cube_m3 must be positive")
        if self.shift.max_pick_min < 1:
            raise ValueError("max_pick_min must be at least 1")
        if not self.orders:
            raise ValueError("Wave plan has no orders")
        if self.strategy not in STRATEGIES:
            raise ValueError(
                f"Unknown strategy '{self.strategy}'. Known: {', '.join(STRATEGIES)}"
            )
        seen: set[str] = set()
        for order in self.orders:
            order.validate()
            if order.id in seen:
                raise ValueError(f"Duplicate order id '{order.id}'")
            seen.add(order.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WavePlan:
        shift = get_shift(payload.get("shift") or {})
        orders: list[Order] = []
        for raw in payload.get("orders") or []:
            orders.append(
                Order(
                    id=str(raw.get("id", "")).strip(),
                    channel=str(raw.get("channel", "other")).strip().lower(),
                    zone=str(raw.get("zone", "")).strip().lower(),
                    lines=int(raw["lines"]),
                    units=int(raw.get("units", raw["lines"])),
                    cube_m3=float(raw["cube_m3"]),
                    pick_min=int(raw["pick_min"]),
                    cutoff=str(raw["cutoff"]),
                    priority=int(raw.get("priority", 2)),
                )
            )
        plan = cls(
            shift=shift,
            orders=orders,
            strategy=str(payload.get("strategy", "auto")),
        )
        plan.validate()
        return plan
