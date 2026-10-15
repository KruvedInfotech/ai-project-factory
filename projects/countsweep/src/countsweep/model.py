"""Wave input types: locations, as-of date, and cycle-count policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .policies import ABC_CLASSES, LOCATION_TYPES, STRATEGIES, Policy, get_policy


def _opt_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _parse_date(value: Any, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required (YYYY-MM-DD)")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _opt_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"", "0", "false", "no", "off"}:
        return False
    raise ValueError("boolean fields must be true or false")


@dataclass(frozen=True)
class Location:
    id: str
    sku: str
    book_qty: int
    abc: str
    aisle: int
    bay: int
    level: int
    last_counted: date | None = None
    counted_qty: int | None = None
    high_shrink: bool = False
    blocked: bool = False
    type: str = "pick"

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each location needs an id")
        if self.book_qty < 0:
            raise ValueError(f"Location '{self.id}' book_qty cannot be negative")
        if self.book_qty > 0 and not self.sku.strip():
            raise ValueError(f"Location '{self.id}' needs a sku when book_qty is positive")
        if self.abc not in ABC_CLASSES:
            raise ValueError(f"Location '{self.id}' abc must be {', '.join(ABC_CLASSES)}")
        if min(self.aisle, self.bay, self.level) < 1:
            raise ValueError(f"Location '{self.id}' aisle, bay, and level must be at least 1")
        if self.counted_qty is not None and self.counted_qty < 0:
            raise ValueError(f"Location '{self.id}' counted_qty cannot be negative")
        if self.type not in LOCATION_TYPES:
            raise ValueError(f"Location '{self.id}' type must be {', '.join(LOCATION_TYPES)}")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sku": self.sku,
            "book_qty": self.book_qty,
            "counted_qty": self.counted_qty,
            "abc": self.abc,
            "aisle": self.aisle,
            "bay": self.bay,
            "level": self.level,
            "last_counted": self.last_counted.isoformat() if self.last_counted else None,
            "high_shrink": self.high_shrink,
            "blocked": self.blocked,
            "type": self.type,
        }


@dataclass
class Wave:
    policy: Policy
    locations: list[Location]
    as_of: date
    strategy: str = "overdue"
    labor_minutes: int | None = None

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.policy.max_labor_min

    def validate(self) -> None:
        self.policy.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.locations:
            raise ValueError("Wave has no locations")
        seen: set[str] = set()
        for location in self.locations:
            location.validate()
            if location.id in seen:
                raise ValueError(f"Duplicate location '{location.id}'")
            seen.add(location.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        locations: list[Location] = []
        for raw in payload.get("locations") or []:
            locations.append(
                Location(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    book_qty=int(raw.get("book_qty", 0)),
                    abc=str(raw.get("abc", "B")).strip() or "B",
                    aisle=int(raw.get("aisle", 0)),
                    bay=int(raw.get("bay", 0)),
                    level=int(raw.get("level", 0)),
                    last_counted=_opt_date(raw.get("last_counted"), "last_counted"),
                    counted_qty=_opt_int(raw.get("counted_qty")),
                    high_shrink=_as_bool(raw.get("high_shrink", False)),
                    blocked=_as_bool(raw.get("blocked", False)),
                    type=str(raw.get("type", "pick")).strip() or "pick",
                )
            )
        labor = payload.get("labor_minutes")
        wave = cls(
            policy=get_policy(payload.get("policy") or {}),
            locations=locations,
            as_of=_parse_date(payload.get("as_of"), "as_of"),
            strategy=str(payload.get("strategy", "overdue")).strip() or "overdue",
            labor_minutes=None if labor in (None, "") else int(labor),
        )
        wave.validate()
        return wave
