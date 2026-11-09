"""Task board: forklift work and a warehouse floor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .floors import KINDS, STRATEGIES, TEMPS, Floor, get_floor


def _as_int(value: Any, field: str, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


@dataclass(frozen=True)
class TaskSpec:
    id: str
    kind: str
    origin: str
    dest: str
    pallets: int
    weight_kg: int
    height_mm: int
    temp: str = "dry"
    priority: int = 2
    ready_min: int = 0

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each task needs an id")
        if self.kind not in KINDS:
            raise ValueError(f"Task '{self.id}' kind must be {', '.join(KINDS)}")
        if not self.origin.strip():
            raise ValueError(f"Task '{self.id}' needs a from location")
        if not self.dest.strip():
            raise ValueError(f"Task '{self.id}' needs a to location")
        if self.origin == self.dest:
            raise ValueError(f"Task '{self.id}' from and to cannot be the same")
        if self.pallets < 1:
            raise ValueError(f"Task '{self.id}' pallets must be at least 1")
        if self.weight_kg < 1:
            raise ValueError(f"Task '{self.id}' weight_kg must be at least 1")
        if self.height_mm < 1:
            raise ValueError(f"Task '{self.id}' height_mm must be positive")
        if self.temp not in TEMPS:
            raise ValueError(f"Task '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.priority < 1:
            raise ValueError(f"Task '{self.id}' priority must be at least 1")
        if self.ready_min < 0:
            raise ValueError(f"Task '{self.id}' ready_min cannot be negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "from": self.origin,
            "to": self.dest,
            "pallets": self.pallets,
            "weight_kg": self.weight_kg,
            "height_mm": self.height_mm,
            "temp": self.temp,
            "priority": self.priority,
            "ready_min": self.ready_min,
        }


@dataclass
class Board:
    floor: Floor
    tasks: list[TaskSpec]
    strategy: str = "auto"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.floor.max_labor_min

    def validate(self) -> None:
        self.floor.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.tasks:
            raise ValueError("Board has no tasks")
        seen: set[str] = set()
        locations = self.floor.location_map()
        for task in self.tasks:
            task.validate()
            if task.id in seen:
                raise ValueError(f"Duplicate task id '{task.id}'")
            seen.add(task.id)
            if task.origin not in locations:
                raise ValueError(f"Task '{task.id}' from '{task.origin}' is not on the floor")
            if task.dest not in locations:
                raise ValueError(f"Task '{task.id}' to '{task.dest}' is not on the floor")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Board:
        floor = get_floor(payload.get("floor") or payload.get("dock") or {})
        tasks: list[TaskSpec] = []
        for raw in payload.get("tasks") or []:
            origin = str(raw.get("from") or raw.get("origin") or "").strip()
            dest = str(raw.get("to") or raw.get("dest") or "").strip()
            tasks.append(
                TaskSpec(
                    id=str(raw.get("id", "")).strip(),
                    kind=str(raw.get("kind", "putaway")).strip() or "putaway",
                    origin=origin,
                    dest=dest,
                    pallets=_as_int(raw.get("pallets", 1), "pallets", 1),
                    weight_kg=_as_int(raw.get("weight_kg", 400), "weight_kg", 400),
                    height_mm=_as_int(raw.get("height_mm", 1400), "height_mm", 1400),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                    ready_min=_as_int(raw.get("ready_min", 0), "ready_min", 0),
                )
            )
        labor = payload.get("labor_minutes")
        board = cls(
            floor=floor,
            tasks=tasks,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        board.validate()
        return board
