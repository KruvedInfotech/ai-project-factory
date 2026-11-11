"""Staffing board: demand curve and a crew roster."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .sites import EQUIPMENT, KINDS, SKILLS, STRATEGIES, TEMPS, Site, get_site


def _as_int(value: Any, field: str, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _as_float(value: Any, field: str, default: float | None = None) -> float:
    if value in (None, "") and default is not None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return tuple(str(item).strip() for item in value if str(item).strip())


@dataclass(frozen=True)
class DemandSlot:
    hour: int
    skill: str
    heads: int
    temp: str = "dry"
    equipment: str = ""
    priority: int = 2

    def validate(self) -> None:
        if not 0 <= self.hour <= 23:
            raise ValueError("Demand hour must be 0–23")
        if self.skill not in SKILLS:
            raise ValueError(f"Demand skill must be {', '.join(SKILLS)}")
        if self.heads < 1:
            raise ValueError("Demand heads must be at least 1")
        if self.temp not in TEMPS or self.temp == "mixed":
            raise ValueError("Demand temp must be dry, chill, or freeze")
        if self.priority < 1:
            raise ValueError("Demand priority must be at least 1")
        if self.equipment:
            if self.skill != "forklift":
                raise ValueError("equipment is only valid on forklift demand")
            if self.equipment not in EQUIPMENT:
                raise ValueError(f"equipment must be {', '.join(EQUIPMENT)}")

    def as_dict(self) -> dict[str, object]:
        row: dict[str, object] = {
            "hour": self.hour,
            "skill": self.skill,
            "heads": self.heads,
            "temp": self.temp,
            "priority": self.priority,
        }
        if self.equipment:
            row["equipment"] = self.equipment
        return row


@dataclass(frozen=True)
class Associate:
    id: str
    name: str
    kind: str
    skills: tuple[str, ...]
    rate_per_hour: float
    available_start: int
    available_end: int
    ot_cap_hours: int = 0
    temp: str = "dry"
    certs: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each associate needs an id")
        if self.kind not in KINDS:
            raise ValueError(f"Associate '{self.id}' kind must be {', '.join(KINDS)}")
        if not self.skills:
            raise ValueError(f"Associate '{self.id}' needs at least one skill")
        unknown = [skill for skill in self.skills if skill not in SKILLS]
        if unknown:
            raise ValueError(f"Associate '{self.id}' unknown skill '{unknown[0]}'")
        if self.rate_per_hour <= 0:
            raise ValueError(f"Associate '{self.id}' rate_per_hour must be positive")
        for value, label in (
            (self.available_start, "available_start"),
            (self.available_end, "available_end"),
        ):
            if not 0 <= value <= 23:
                raise ValueError(f"Associate '{self.id}' {label} must be an hour 0–23")
        if self.ot_cap_hours < 0:
            raise ValueError(f"Associate '{self.id}' ot_cap_hours cannot be negative")
        if self.temp not in TEMPS:
            raise ValueError(f"Associate '{self.id}' temp must be {', '.join(TEMPS)}")
        bad_cert = [item for item in self.certs if item not in EQUIPMENT]
        if bad_cert:
            raise ValueError(f"Associate '{self.id}' unknown cert '{bad_cert[0]}'")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "skills": list(self.skills),
            "rate_per_hour": self.rate_per_hour,
            "available_start": self.available_start,
            "available_end": self.available_end,
            "ot_cap_hours": self.ot_cap_hours,
            "temp": self.temp,
            "certs": list(self.certs),
        }


@dataclass
class Board:
    site: Site
    demand: list[DemandSlot]
    crew: list[Associate]
    strategy: str = "auto"
    labor_dollars: float | None = None
    head_cap: int | None = None

    def labor_cap(self) -> float:
        return self.labor_dollars if self.labor_dollars is not None else self.site.labor_dollars

    def heads_cap(self) -> int:
        return self.head_cap if self.head_cap is not None else self.site.head_cap

    def validate(self) -> None:
        self.site.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_dollars is not None and self.labor_dollars <= 0:
            raise ValueError("labor_dollars must be positive")
        if self.head_cap is not None and self.head_cap < 1:
            raise ValueError("head_cap must be at least 1")
        if not self.demand:
            raise ValueError("Board has no demand")
        if not self.crew:
            raise ValueError("Board has no crew")
        seen: set[str] = set()
        for person in self.crew:
            person.validate()
            if person.id in seen:
                raise ValueError(f"Duplicate associate id '{person.id}'")
            seen.add(person.id)
        for slot in self.demand:
            slot.validate()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Board:
        site = get_site(payload.get("site") or payload.get("floor") or {})
        demand: list[DemandSlot] = []
        for raw in payload.get("demand") or []:
            demand.append(
                DemandSlot(
                    hour=_as_int(raw.get("hour"), "hour"),
                    skill=str(raw.get("skill", "pick")).strip() or "pick",
                    heads=_as_int(raw.get("heads", 1), "heads", 1),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    equipment=str(raw.get("equipment", "")).strip(),
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                )
            )
        crew: list[Associate] = []
        for raw in payload.get("crew") or []:
            ident = str(raw.get("id", "")).strip()
            crew.append(
                Associate(
                    id=ident,
                    name=str(raw.get("name") or ident).strip() or ident,
                    kind=str(raw.get("kind", "regular")).strip() or "regular",
                    skills=_as_tuple(raw.get("skills")),
                    rate_per_hour=_as_float(raw.get("rate_per_hour"), "rate_per_hour"),
                    available_start=_as_int(raw.get("available_start"), "available_start"),
                    available_end=_as_int(raw.get("available_end"), "available_end"),
                    ot_cap_hours=_as_int(raw.get("ot_cap_hours", 0), "ot_cap_hours", 0),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    certs=_as_tuple(raw.get("certs")),
                )
            )
        labor = payload.get("labor_dollars")
        heads = payload.get("head_cap")
        board = cls(
            site=site,
            demand=demand,
            crew=crew,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_dollars=None if labor in (None, "") else float(labor),
            head_cap=None if heads in (None, "") else int(heads),
        )
        board.validate()
        return board
