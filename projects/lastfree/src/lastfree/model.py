"""Job input for a single container clock."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .presets import Preset, get_preset

CONTAINER_RE = re.compile(r"^[A-Z]{4}[0-9]{6,7}$")
SIZES = {"20": 20, "40": 40, "40HC": 40, "45": 45}


def parse_date(value: object, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required (YYYY-MM-DD)")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def parse_optional_date(value: object, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    return parse_date(value, field_name)


@dataclass
class Job:
    container: str
    preset: Preset
    available_on: date
    as_of: date
    size: str = "40"
    gate_out_on: date | None = None
    empty_return_on: date | None = None
    holidays: list[date] = field(default_factory=list)

    @property
    def size_ft(self) -> int:
        return SIZES[self.size]

    @property
    def holiday_set(self) -> set[date]:
        return set(self.holidays)

    def size_factor(self) -> float:
        if self.size_ft == 20:
            return self.preset.factor_20
        if self.size_ft == 45:
            return self.preset.factor_45
        return 1.0

    def validate(self) -> None:
        code = self.container.strip().upper().replace(" ", "").replace("-", "")
        if not CONTAINER_RE.match(code):
            raise ValueError("Container needs 4 letters and 6–7 digits, e.g. MSCU1234567")
        self.container = code
        if self.size not in SIZES:
            raise ValueError("Size must be 20, 40, 40HC, or 45")
        if self.gate_out_on is not None and self.gate_out_on < self.available_on:
            raise ValueError("Gate-out cannot be before the container is available")
        if self.empty_return_on is not None:
            if self.gate_out_on is None:
                raise ValueError("Empty return needs a gate-out date")
            if self.empty_return_on < self.gate_out_on:
                raise ValueError("Empty return cannot be before gate-out")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Job:
        holidays_raw = payload.get("holidays") or []
        holidays = [parse_date(item, "holiday") for item in holidays_raw]
        as_of_raw = payload.get("as_of")
        as_of = parse_date(as_of_raw, "as_of") if as_of_raw not in (None, "") else date.today()
        job = cls(
            container=str(payload.get("container") or "").strip(),
            preset=get_preset(payload),
            size=str(payload.get("size") or "40").strip().upper().replace(" ", ""),
            available_on=parse_date(payload.get("available_on"), "available_on"),
            as_of=as_of,
            gate_out_on=parse_optional_date(payload.get("gate_out_on"), "gate_out_on"),
            empty_return_on=parse_optional_date(payload.get("empty_return_on"), "empty_return_on"),
            holidays=holidays,
        )
        job.validate()
        return job

    def as_dict(self) -> dict[str, object]:
        return {
            "container": self.container,
            "preset": self.preset.id,
            "size": self.size,
            "available_on": self.available_on.isoformat(),
            "as_of": self.as_of.isoformat(),
            "gate_out_on": self.gate_out_on.isoformat() if self.gate_out_on else None,
            "empty_return_on": self.empty_return_on.isoformat() if self.empty_return_on else None,
            "holidays": [item.isoformat() for item in self.holidays],
            "overrides": {
                "demurrage_free_days": self.preset.demurrage_free_days,
                "demurrage_day_type": self.preset.demurrage_day_type,
                "detention_free_days": self.preset.detention_free_days,
                "detention_day_type": self.preset.detention_day_type,
            },
        }
