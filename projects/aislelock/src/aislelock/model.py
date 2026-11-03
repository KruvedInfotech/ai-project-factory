"""Wave input types: carts, walks, and a warehouse floor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .floors import STRATEGIES, TEMPS, Floor, get_floor


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
class WalkStep:
    aisle: str
    picks: int = 0

    def as_dict(self) -> dict[str, object]:
        return {"aisle": self.aisle, "picks": self.picks}


@dataclass(frozen=True)
class CartSpec:
    id: str
    walk: tuple[WalkStep, ...]
    priority: int = 2
    temp: str = "dry"
    bulky: bool = False
    ready_min: int = 0
    cutoff_min: int | None = None

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each cart needs an id")
        if self.priority < 1:
            raise ValueError(f"Cart '{self.id}' priority must be at least 1")
        if self.temp not in TEMPS:
            raise ValueError(f"Cart '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.ready_min < 0:
            raise ValueError(f"Cart '{self.id}' ready_min cannot be negative")
        if self.cutoff_min is not None and self.cutoff_min < 1:
            raise ValueError(f"Cart '{self.id}' cutoff_min must be at least 1")
        if not self.walk:
            raise ValueError(f"Cart '{self.id}' needs at least one aisle")
        seen: set[str] = set()
        for step in self.walk:
            if not step.aisle.strip():
                raise ValueError(f"Cart '{self.id}' has an empty aisle")
            if step.picks < 0:
                raise ValueError(f"Cart '{self.id}' picks cannot be negative")
            if step.aisle in seen:
                raise ValueError(f"Cart '{self.id}' repeats aisle '{step.aisle}'")
            seen.add(step.aisle)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "priority": self.priority,
            "temp": self.temp,
            "bulky": self.bulky,
            "ready_min": self.ready_min,
            "cutoff_min": self.cutoff_min,
            "walk": [step.as_dict() for step in self.walk],
        }


def parse_walk(raw: Any, cart_id: str) -> tuple[WalkStep, ...]:
    if raw in (None, ""):
        raise ValueError(f"Cart '{cart_id}' needs a walk")
    if isinstance(raw, str):
        tokens = [token for token in raw.replace(",", " ").split() if token]
        steps: list[WalkStep] = []
        for token in tokens:
            aisle, _, picks = token.partition(":")
            steps.append(WalkStep(aisle=aisle.strip().upper(), picks=_as_int(picks or 0, "picks", 0)))
        return tuple(steps)
    steps = []
    for item in raw:
        if isinstance(item, str):
            aisle, _, picks = item.partition(":")
            steps.append(WalkStep(aisle=aisle.strip().upper(), picks=_as_int(picks or 0, "picks", 0)))
            continue
        aisle = str(item.get("aisle", "")).strip().upper()
        steps.append(WalkStep(aisle=aisle, picks=_as_int(item.get("picks", 0), "picks", 0)))
    return tuple(steps)


@dataclass
class Wave:
    floor: Floor
    carts: list[CartSpec]
    strategy: str = "auto"
    labor_minutes: int | None = None
    exclusive_bulky: bool = True

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.floor.max_labor_min

    def validate(self) -> None:
        self.floor.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.carts:
            raise ValueError("Wave has no carts")
        seen: set[str] = set()
        for cart in self.carts:
            cart.validate()
            if cart.id in seen:
                raise ValueError(f"Duplicate cart id '{cart.id}'")
            seen.add(cart.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        floor = get_floor(payload.get("floor") or {})
        carts: list[CartSpec] = []
        for raw in payload.get("carts") or []:
            cart_id = str(raw.get("id", "")).strip()
            carts.append(
                CartSpec(
                    id=cart_id,
                    walk=parse_walk(raw.get("walk"), cart_id or "?"),
                    priority=_as_int(raw.get("priority", 2), "priority", 2),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    bulky=_as_bool(raw.get("bulky"), False),
                    ready_min=_as_int(raw.get("ready_min", 0), "ready_min", 0),
                    cutoff_min=_as_optional_int(raw.get("cutoff_min"), "cutoff_min"),
                )
            )
        labor = payload.get("labor_minutes")
        wave = cls(
            floor=floor,
            carts=carts,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
            exclusive_bulky=_as_bool(payload.get("exclusive_bulky"), True),
        )
        wave.validate()
        return wave
