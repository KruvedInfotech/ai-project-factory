"""Trailer decks: pallet rows from nose to doors.

Figures are typical inner working numbers, not a particular OEM spec sheet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STRATEGIES = ("auto", "lifo", "heavy", "no-mix")
TEMPS = ("dry", "reefer")
TRAILER_TEMPS = ("dry", "reefer", "mixed")


@dataclass(frozen=True)
class Trailer:
    id: str
    name: str
    rows: int
    cols: int
    stack_levels: int
    max_height_mm: int
    max_weight_kg: float
    temp: str
    minutes_per_pallet: int
    max_labor_min: int

    @property
    def slot_count(self) -> int:
        return self.rows * self.cols * self.stack_levels

    def side_of(self, col: int) -> str:
        if self.cols == 1:
            return "C"
        if col == 1:
            return "L"
        if col == 2:
            return "R"
        return str(col)

    def accepts_temp(self, pallet_temp: str) -> bool:
        if self.temp == "mixed":
            return True
        return pallet_temp == self.temp

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Trailer needs a name")
        if self.rows < 1:
            raise ValueError("rows must be at least 1")
        if self.cols < 1:
            raise ValueError("cols must be at least 1")
        if self.stack_levels not in (1, 2):
            raise ValueError("stack_levels must be 1 or 2")
        if self.max_height_mm < 1:
            raise ValueError("max_height_mm must be at least 1")
        if self.max_weight_kg <= 0:
            raise ValueError("max_weight_kg must be positive")
        if self.temp not in TRAILER_TEMPS:
            raise ValueError(f"trailer temp must be {', '.join(TRAILER_TEMPS)}")
        if self.minutes_per_pallet < 1:
            raise ValueError("minutes_per_pallet must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["slot_count"] = self.slot_count
        data["stack"] = "2-high" if self.stack_levels == 2 else "floor"
        return data


PRESETS: dict[str, Trailer] = {
    "grocery_12m": Trailer(
        id="grocery_12m",
        name="12 m grocery box",
        rows=11,
        cols=2,
        stack_levels=2,
        max_height_mm=2400,
        max_weight_kg=18000,
        temp="dry",
        minutes_per_pallet=3,
        max_labor_min=90,
    ),
    "city_van": Trailer(
        id="city_van",
        name="City van",
        rows=4,
        cols=2,
        stack_levels=1,
        max_height_mm=1800,
        max_weight_kg=2500,
        temp="dry",
        minutes_per_pallet=2,
        max_labor_min=30,
    ),
    "reefer_13m": Trailer(
        id="reefer_13m",
        name="13 m reefer",
        rows=12,
        cols=2,
        stack_levels=1,
        max_height_mm=2200,
        max_weight_kg=16000,
        temp="reefer",
        minutes_per_pallet=4,
        max_labor_min=80,
    ),
    "mini_6": Trailer(
        id="mini_6",
        name="Small demo trailer",
        rows=3,
        cols=2,
        stack_levels=2,
        max_height_mm=2400,
        max_weight_kg=4000,
        temp="mixed",
        minutes_per_pallet=2,
        max_labor_min=20,
    ),
}


def _int_or(raw: dict[str, Any], key: str, default: int) -> int:
    return int(raw[key]) if key in raw else default


def _float_or(raw: dict[str, Any], key: str, default: float) -> float:
    return float(raw[key]) if key in raw else default


def _trailer_from_parts(raw: dict[str, Any], default: Trailer | None = None) -> Trailer:
    return Trailer(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom trailer")),
        rows=_int_or(raw, "rows", default.rows if default else 6),
        cols=_int_or(raw, "cols", default.cols if default else 2),
        stack_levels=_int_or(raw, "stack_levels", default.stack_levels if default else 1),
        max_height_mm=_int_or(raw, "max_height_mm", default.max_height_mm if default else 2400),
        max_weight_kg=_float_or(
            raw, "max_weight_kg", default.max_weight_kg if default else 8000
        ),
        temp=str(raw.get("temp") or (default.temp if default else "dry")).strip() or "dry",
        minutes_per_pallet=_int_or(
            raw, "minutes_per_pallet", default.minutes_per_pallet if default else 3
        ),
        max_labor_min=_int_or(
            raw, "max_labor_min", default.max_labor_min if default else 60
        ),
    )


def get_trailer(raw: dict[str, Any] | None) -> Trailer:
    payload = dict(raw or {})
    preset = payload.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown trailer preset '{preset}'")
        trailer = _trailer_from_parts(payload, PRESETS[preset])
        if "id" not in payload:
            trailer = Trailer(
                id=str(preset),
                name=trailer.name,
                rows=trailer.rows,
                cols=trailer.cols,
                stack_levels=trailer.stack_levels,
                max_height_mm=trailer.max_height_mm,
                max_weight_kg=trailer.max_weight_kg,
                temp=trailer.temp,
                minutes_per_pallet=trailer.minutes_per_pallet,
                max_labor_min=trailer.max_labor_min,
            )
        return trailer
    return _trailer_from_parts(payload)
