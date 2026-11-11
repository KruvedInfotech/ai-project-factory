"""Shift-site catalogs.

Hours are clock hours 0–23. A site with shift_end before shift_start is overnight.
Rates, headcounts, and break rules are working figures, not a particular WFM policy.
"""

from __future__ import annotations

from dataclasses import dataclass


SKILLS = ("pick", "pack", "receive", "replen", "forklift")
KINDS = ("regular", "temp")
TEMPS = ("dry", "chill", "freeze", "mixed")
STRATEGIES = ("auto", "regular", "temp", "overtime")
EQUIPMENT = ("reach", "jack", "sitdown")


def hour_range(start: int, end: int) -> list[int]:
    """Clock hours in a shift. `end` is exclusive. Wraps past midnight."""
    start = int(start) % 24
    end = int(end) % 24
    if start == end:
        return list(range(24))
    if start < end:
        return list(range(start, end))
    return list(range(start, 24)) + list(range(0, end))


def hour_in_span(hour: int, start: int, end: int) -> bool:
    return (int(hour) % 24) in set(hour_range(start, end))


def fmt_hour(hour: int) -> str:
    return f"{int(hour) % 24:02d}:00"


def shift_label(start: int, end: int) -> str:
    return f"{fmt_hour(start)}–{fmt_hour(end)}"


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    shift_start: int
    shift_end: int
    labor_dollars: float
    head_cap: int
    break_after: int = 4

    @property
    def hours(self) -> list[int]:
        return hour_range(self.shift_start, self.shift_end)

    def hour_index(self, hour: int) -> int:
        hours = self.hours
        clock = int(hour) % 24
        if clock in hours:
            return hours.index(clock)
        return 1000 + clock

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "shift_start": self.shift_start,
            "shift_end": self.shift_end,
            "shift": shift_label(self.shift_start, self.shift_end),
            "hours": self.hours,
            "labor_dollars": self.labor_dollars,
            "head_cap": self.head_cap,
            "break_after": self.break_after,
        }

    def validate(self) -> None:
        for value, label in (
            (self.shift_start, "shift_start"),
            (self.shift_end, "shift_end"),
        ):
            if not 0 <= int(value) <= 23:
                raise ValueError(f"{label} must be an hour 0–23")
        if self.labor_dollars <= 0:
            raise ValueError("labor_dollars must be positive")
        if self.head_cap < 1:
            raise ValueError("head_cap must be at least 1")
        if self.break_after < 1:
            raise ValueError("break_after must be at least 1")


PRESETS: dict[str, Site] = {
    "grocery": Site("grocery", "Grocery DC day", 6, 14, 1600, 12, 4),
    "produce": Site("produce", "Produce night cold chain", 22, 6, 1400, 8, 4),
    "dc": Site("dc", "Store DC", 5, 15, 2800, 16, 4),
    "parcel": Site("parcel", "Parcel inbound", 8, 16, 900, 8, 4),
}


def get_site(payload: dict) -> Site:
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"Unknown site preset '{key}'. Known: {known}")
        preset = PRESETS[key]
        fields = ("shift_start", "shift_end", "labor_dollars", "head_cap", "break_after", "name")
        overrides = {field: payload[field] for field in fields if field in payload and payload[field] is not None}
        if not overrides:
            return preset
        return Site(
            id=preset.id,
            name=str(overrides.get("name", preset.name)),
            shift_start=int(overrides.get("shift_start", preset.shift_start)),
            shift_end=int(overrides.get("shift_end", preset.shift_end)),
            labor_dollars=float(overrides.get("labor_dollars", preset.labor_dollars)),
            head_cap=int(overrides.get("head_cap", preset.head_cap)),
            break_after=int(overrides.get("break_after", preset.break_after)),
        )
    required = ("shift_start", "shift_end", "labor_dollars", "head_cap")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Custom site missing: {', '.join(missing)}")
    return Site(
        id="custom",
        name=str(payload.get("name") or "Custom site"),
        shift_start=int(payload["shift_start"]),
        shift_end=int(payload["shift_end"]),
        labor_dollars=float(payload["labor_dollars"]),
        head_cap=int(payload["head_cap"]),
        break_after=int(payload.get("break_after") or 4),
    )
