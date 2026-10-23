"""Sortation banks: grids of destination chutes off an induction belt.

Figures are typical chute-mouth numbers, not a particular sorter OEM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STRATEGIES = ("auto", "dest", "carrier", "compact")
TEMPS = ("ambient", "chill")
BANK_TEMPS = ("ambient", "chill", "mixed")


@dataclass(frozen=True)
class Bank:
    id: str
    name: str
    rows: int
    cols: int
    length_mm: int
    width_mm: int
    height_mm: int
    max_weight_kg: float
    max_cartons: int
    temp: str
    minutes_per_carton: int
    max_labor_min: int

    @property
    def chute_count(self) -> int:
        return self.rows * self.cols

    @property
    def mouth_volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    @property
    def induction_row(self) -> int:
        return 1

    @property
    def mid_col(self) -> float:
        return (self.cols + 1) / 2

    def chute_id(self, row: int, col: int) -> str:
        return f"R{row}C{col}"

    def zone_of(self, row: int) -> str:
        if self.rows == 1 or row == self.induction_row:
            return "induction"
        if row == self.rows:
            return "far"
        return "mid"

    def golden_score(self, row: int, col: int) -> float:
        return abs(row - self.induction_row) * 2 + abs(col - self.mid_col)

    def raster_index(self, row: int, col: int) -> int:
        return (row - 1) * self.cols + (col - 1)

    def accepts_temp(self, carton_temp: str) -> bool:
        if self.temp == "mixed":
            return True
        return carton_temp == self.temp

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Bank needs a name")
        if self.rows < 1:
            raise ValueError("rows must be at least 1")
        if self.cols < 1:
            raise ValueError("cols must be at least 1")
        if self.length_mm < 1 or self.width_mm < 1 or self.height_mm < 1:
            raise ValueError("chute mouth dimensions must be at least 1 mm")
        if self.max_weight_kg <= 0:
            raise ValueError("max_weight_kg must be positive")
        if self.max_cartons < 1:
            raise ValueError("max_cartons must be at least 1")
        if self.temp not in BANK_TEMPS:
            raise ValueError(f"bank temp must be {', '.join(BANK_TEMPS)}")
        if self.minutes_per_carton < 1:
            raise ValueError("minutes_per_carton must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["chute_count"] = self.chute_count
        data["mouth_volume_mm3"] = self.mouth_volume_mm3
        data["induction_row"] = self.induction_row
        return data


PRESETS: dict[str, Bank] = {
    "bank_1x6": Bank(
        id="bank_1x6",
        name="6-chute induction",
        rows=1,
        cols=6,
        length_mm=600,
        width_mm=400,
        height_mm=400,
        max_weight_kg=25,
        max_cartons=12,
        temp="mixed",
        minutes_per_carton=1,
        max_labor_min=48,
    ),
    "bank_2x5": Bank(
        id="bank_2x5",
        name="2×5 sorter bank",
        rows=2,
        cols=5,
        length_mm=550,
        width_mm=380,
        height_mm=380,
        max_weight_kg=20,
        max_cartons=10,
        temp="mixed",
        minutes_per_carton=1,
        max_labor_min=80,
    ),
    "chill_1x4": Bank(
        id="chill_1x4",
        name="4-chute chill sorter",
        rows=1,
        cols=4,
        length_mm=500,
        width_mm=350,
        height_mm=350,
        max_weight_kg=15,
        max_cartons=8,
        temp="chill",
        minutes_per_carton=1,
        max_labor_min=24,
    ),
    "mini_1x3": Bank(
        id="mini_1x3",
        name="Demo 1×3 bank",
        rows=1,
        cols=3,
        length_mm=600,
        width_mm=400,
        height_mm=400,
        max_weight_kg=18,
        max_cartons=6,
        temp="mixed",
        minutes_per_carton=1,
        max_labor_min=12,
    ),
}


def _int_or(raw: dict[str, Any], key: str, default: int) -> int:
    return int(raw[key]) if key in raw else default


def _float_or(raw: dict[str, Any], key: str, default: float) -> float:
    return float(raw[key]) if key in raw else default


def _bank_from_parts(raw: dict[str, Any], default: Bank | None = None) -> Bank:
    return Bank(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom bank")),
        rows=_int_or(raw, "rows", default.rows if default else 1),
        cols=_int_or(raw, "cols", default.cols if default else 6),
        length_mm=_int_or(raw, "length_mm", default.length_mm if default else 600),
        width_mm=_int_or(raw, "width_mm", default.width_mm if default else 400),
        height_mm=_int_or(raw, "height_mm", default.height_mm if default else 400),
        max_weight_kg=_float_or(
            raw, "max_weight_kg", default.max_weight_kg if default else 25
        ),
        max_cartons=_int_or(raw, "max_cartons", default.max_cartons if default else 12),
        temp=str(raw.get("temp") or (default.temp if default else "mixed")).strip()
        or "mixed",
        minutes_per_carton=_int_or(
            raw, "minutes_per_carton", default.minutes_per_carton if default else 1
        ),
        max_labor_min=_int_or(
            raw, "max_labor_min", default.max_labor_min if default else 48
        ),
    )


def get_bank(raw: dict[str, Any] | None) -> Bank:
    payload = dict(raw or {})
    preset = payload.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown bank preset '{preset}'")
        bank = _bank_from_parts(payload, PRESETS[preset])
        if "id" not in payload:
            bank = Bank(
                id=str(preset),
                name=bank.name,
                rows=bank.rows,
                cols=bank.cols,
                length_mm=bank.length_mm,
                width_mm=bank.width_mm,
                height_mm=bank.height_mm,
                max_weight_kg=bank.max_weight_kg,
                max_cartons=bank.max_cartons,
                temp=bank.temp,
                minutes_per_carton=bank.minutes_per_carton,
                max_labor_min=bank.max_labor_min,
            )
        return bank
    return _bank_from_parts(payload)
