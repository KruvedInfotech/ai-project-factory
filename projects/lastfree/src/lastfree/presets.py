"""Typical terminal / line free-time clocks.

These are planning defaults, not a particular port tariff. Real free time is
in the line contract and the terminal schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RateTier:
    from_day: int
    to_day: int | None
    usd: float

    def as_dict(self) -> dict[str, object]:
        return {"from_day": self.from_day, "to_day": self.to_day, "usd": self.usd}


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    demurrage_free_days: int
    demurrage_day_type: str
    detention_free_days: int
    detention_day_type: str
    demurrage_rates: tuple[RateTier, ...]
    detention_rates: tuple[RateTier, ...]
    factor_20: float = 0.8
    factor_45: float = 1.15

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "demurrage_free_days": self.demurrage_free_days,
            "demurrage_day_type": self.demurrage_day_type,
            "detention_free_days": self.detention_free_days,
            "detention_day_type": self.detention_day_type,
            "demurrage_rates": [tier.as_dict() for tier in self.demurrage_rates],
            "detention_rates": [tier.as_dict() for tier in self.detention_rates],
            "factor_20": self.factor_20,
            "factor_45": self.factor_45,
        }


def _tiers(*rows: tuple[int, int | None, float]) -> tuple[RateTier, ...]:
    return tuple(RateTier(from_day=a, to_day=b, usd=c) for a, b, c in rows)


PRESETS: dict[str, Preset] = {
    "uswc_port": Preset(
        id="uswc_port",
        name="US West Coast terminal",
        demurrage_free_days=4,
        demurrage_day_type="business",
        detention_free_days=4,
        detention_day_type="calendar",
        demurrage_rates=_tiers((1, 5, 285.0), (6, None, 400.0)),
        detention_rates=_tiers((1, 4, 160.0), (5, None, 280.0)),
    ),
    "use_port": Preset(
        id="use_port",
        name="US East Coast terminal",
        demurrage_free_days=5,
        demurrage_day_type="business",
        detention_free_days=5,
        detention_day_type="calendar",
        demurrage_rates=_tiers((1, 4, 195.0), (5, None, 340.0)),
        detention_rates=_tiers((1, 4, 195.0), (5, None, 340.0)),
    ),
    "inland_ramp": Preset(
        id="inland_ramp",
        name="Inland rail ramp",
        demurrage_free_days=2,
        demurrage_day_type="business",
        detention_free_days=3,
        detention_day_type="calendar",
        demurrage_rates=_tiers((1, 3, 250.0), (4, None, 450.0)),
        detention_rates=_tiers((1, 3, 175.0), (4, None, 310.0)),
    ),
    "line_calendar": Preset(
        id="line_calendar",
        name="Steamship line (calendar days)",
        demurrage_free_days=7,
        demurrage_day_type="calendar",
        detention_free_days=7,
        detention_day_type="calendar",
        demurrage_rates=_tiers((1, 7, 150.0), (8, None, 275.0)),
        detention_rates=_tiers((1, 7, 150.0), (8, None, 275.0)),
    ),
}


def get_preset(payload: dict[str, Any]) -> Preset:
    raw_id = str(payload.get("preset") or payload.get("id") or "").strip()
    if not raw_id:
        raise ValueError("Choose a terminal preset")
    if raw_id not in PRESETS:
        known = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown preset '{raw_id}'. Known: {known}")
    base = PRESETS[raw_id]
    overrides = payload.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")

    demurrage_free = int(overrides.get("demurrage_free_days", base.demurrage_free_days))
    detention_free = int(overrides.get("detention_free_days", base.detention_free_days))
    demurrage_type = str(overrides.get("demurrage_day_type", base.demurrage_day_type))
    detention_type = str(overrides.get("detention_day_type", base.detention_day_type))
    if demurrage_free < 0 or detention_free < 0:
        raise ValueError("Free time cannot be negative")
    for label, value in (("demurrage", demurrage_type), ("detention", detention_type)):
        if value not in ("business", "calendar"):
            raise ValueError(f"{label} day type must be business or calendar")

    return Preset(
        id=base.id,
        name=base.name,
        demurrage_free_days=demurrage_free,
        demurrage_day_type=demurrage_type,
        detention_free_days=detention_free,
        detention_day_type=detention_type,
        demurrage_rates=base.demurrage_rates,
        detention_rates=base.detention_rates,
        factor_20=float(overrides.get("factor_20", base.factor_20)),
        factor_45=float(overrides.get("factor_45", base.factor_45)),
    )
