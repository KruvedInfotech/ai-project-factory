"""Yard-plan input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .yards import TEMPS, TRAILER_KINDS, Yard, clock_to_min, get_yard

STRATEGIES = ("auto", "door", "dwell", "pull")


@dataclass(frozen=True)
class Trailer:
    id: str
    kind: str
    temp: str = "dry"
    length_ft: int = 53
    eta: str = "08:00"
    door: str = ""
    dwell_h: float = 0.0
    priority: int = 2
    appointment: str = ""
    needs_power: bool = False

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each trailer needs an id")
        if self.kind not in TRAILER_KINDS:
            raise ValueError(f"Trailer '{self.id}' kind must be {', '.join(TRAILER_KINDS)}")
        if self.temp not in TEMPS:
            raise ValueError(f"Trailer '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.length_ft < 1:
            raise ValueError(f"Trailer '{self.id}' length_ft must be at least 1")
        clock_to_min(self.eta)
        if self.appointment:
            clock_to_min(self.appointment)
        if self.dwell_h < 0:
            raise ValueError(f"Trailer '{self.id}' dwell_h cannot be negative")
        if self.priority < 1:
            raise ValueError(f"Trailer '{self.id}' priority must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "temp": self.temp,
            "length_ft": self.length_ft,
            "eta": self.eta,
            "door": self.door,
            "dwell_h": self.dwell_h,
            "priority": self.priority,
            "appointment": self.appointment,
            "needs_power": self.needs_power,
        }


@dataclass
class YardPlan:
    yard: Yard
    trailers: list[Trailer]
    strategy: str = "auto"

    def validate(self) -> None:
        self.yard.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if not self.trailers:
            raise ValueError("Yard plan has no trailers")
        seen: set[str] = set()
        for trailer in self.trailers:
            trailer.validate()
            if trailer.id in seen:
                raise ValueError(f"Duplicate trailer '{trailer.id}'")
            seen.add(trailer.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> YardPlan:
        trailers = []
        for raw in payload.get("trailers") or []:
            trailers.append(
                Trailer(
                    id=str(raw.get("id", "")).strip(),
                    kind=str(raw.get("kind", "")).strip(),
                    temp=str(raw.get("temp", "dry")).strip(),
                    length_ft=int(raw.get("length_ft", 53)),
                    eta=str(raw.get("eta", "")).strip() or "08:00",
                    door=str(raw.get("door", "")).strip(),
                    dwell_h=float(raw.get("dwell_h", 0)),
                    priority=int(raw.get("priority", 2)),
                    appointment=str(raw.get("appointment", "")).strip(),
                    needs_power=bool(raw.get("needs_power", False)),
                )
            )
        plan = cls(
            yard=get_yard(payload.get("yard") or {}),
            trailers=trailers,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
        )
        plan.validate()
        return plan
