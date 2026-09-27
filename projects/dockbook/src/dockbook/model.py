"""Day-plan input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .yards import DIRECTIONS, Yard, get_yard, parse_hhmm

STRATEGIES = ("auto", "earliest", "preferred", "spread")


@dataclass(frozen=True)
class Trailer:
    id: str
    carrier: str
    direction: str
    reefer: bool
    length_m: float
    duration_min: int
    window_start: str
    window_end: str
    prefer_door: str | None = None
    priority: int = 2

    @property
    def temp(self) -> str:
        return "reefer" if self.reefer else "dry"

    @property
    def start_min(self) -> int:
        return parse_hhmm(self.window_start)

    @property
    def end_min(self) -> int:
        return parse_hhmm(self.window_end)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each trailer needs an id")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"Trailer '{self.id}' direction must be inbound or outbound")
        if self.length_m <= 0:
            raise ValueError(f"Trailer '{self.id}' length must be positive")
        if self.duration_min < 1:
            raise ValueError(f"Trailer '{self.id}' duration must be at least 1 minute")
        if self.end_min <= self.start_min:
            raise ValueError(f"Trailer '{self.id}' window end must be after start")
        if self.end_min - self.start_min < self.duration_min:
            raise ValueError(f"Trailer '{self.id}' window is shorter than the dwell")
        if self.priority < 1:
            raise ValueError(f"Trailer '{self.id}' priority must be ≥ 1 (1 is first)")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "carrier": self.carrier,
            "direction": self.direction,
            "reefer": self.reefer,
            "temp": self.temp,
            "length_m": self.length_m,
            "duration_min": self.duration_min,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "prefer_door": self.prefer_door,
            "priority": self.priority,
        }


@dataclass
class DayPlan:
    yard: Yard
    trailers: list[Trailer]
    strategy: str = "auto"

    def validate(self) -> None:
        if self.yard.close_min <= self.yard.open_min:
            raise ValueError("Yard close must be after open")
        if self.yard.turnaround_min < 0:
            raise ValueError("Turnaround cannot be negative")
        if not self.yard.doors:
            raise ValueError("Yard has no doors")
        if not self.trailers:
            raise ValueError("Day plan has no trailers")
        if self.strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy '{self.strategy}'. Known: {', '.join(STRATEGIES)}")
        seen: set[str] = set()
        for trailer in self.trailers:
            trailer.validate()
            if trailer.id in seen:
                raise ValueError(f"Duplicate trailer id '{trailer.id}'")
            seen.add(trailer.id)
            if trailer.prefer_door and self.yard.door(trailer.prefer_door) is None:
                raise ValueError(
                    f"Trailer '{trailer.id}' prefers unknown door '{trailer.prefer_door}'"
                )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DayPlan:
        yard = get_yard(payload.get("yard") or {})
        trailers: list[Trailer] = []
        for raw in payload.get("trailers") or []:
            prefer = raw.get("prefer_door")
            trailers.append(
                Trailer(
                    id=str(raw.get("id", "")).strip(),
                    carrier=str(raw.get("carrier", "")).strip(),
                    direction=str(raw.get("direction", "")).strip().lower(),
                    reefer=bool(raw.get("reefer", False)),
                    length_m=float(raw["length_m"]),
                    duration_min=int(raw["duration_min"]),
                    window_start=str(raw["window_start"]),
                    window_end=str(raw["window_end"]),
                    prefer_door=str(prefer).strip() if prefer else None,
                    priority=int(raw.get("priority", 2)),
                )
            )
        plan = cls(
            yard=yard,
            trailers=trailers,
            strategy=str(payload.get("strategy", "auto")),
        )
        plan.validate()
        return plan
