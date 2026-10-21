"""Kitting-line decks: workbench grids a builder stands in front of.

Figures are typical inner bench numbers, not a particular fixture brand.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STRATEGIES = ("auto", "priority", "family", "compact")
TEMPS = ("ambient", "chill")
LINE_TEMPS = ("ambient", "chill", "mixed")


@dataclass(frozen=True)
class Line:
    id: str
    name: str
    rows: int
    cols: int
    length_mm: int
    width_mm: int
    height_mm: int
    max_weight_kg: float
    max_run: int
    temp: str
    minutes_per_kit: int
    max_labor_min: int

    @property
    def bench_count(self) -> int:
        return self.rows * self.cols

    @property
    def bench_volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    @property
    def aisle_row(self) -> int:
        return self.rows

    @property
    def mid_col(self) -> float:
        return (self.cols + 1) / 2

    def bench_id(self, row: int, col: int) -> str:
        return f"R{row}C{col}"

    def zone_of(self, row: int) -> str:
        if self.rows == 1 or row == self.aisle_row:
            return "aisle"
        if row == 1:
            return "back"
        return "mid"

    def golden_score(self, row: int, col: int) -> float:
        return abs(row - self.aisle_row) * 2 + abs(col - self.mid_col)

    def raster_index(self, row: int, col: int) -> int:
        return (row - 1) * self.cols + (col - 1)

    def accepts_temp(self, kit_temp: str) -> bool:
        if self.temp == "mixed":
            return True
        return kit_temp == self.temp

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Line needs a name")
        if self.rows < 1:
            raise ValueError("rows must be at least 1")
        if self.cols < 1:
            raise ValueError("cols must be at least 1")
        if self.length_mm < 1 or self.width_mm < 1 or self.height_mm < 1:
            raise ValueError("bench dimensions must be at least 1 mm")
        if self.max_weight_kg <= 0:
            raise ValueError("max_weight_kg must be positive")
        if self.max_run < 1:
            raise ValueError("max_run must be at least 1")
        if self.temp not in LINE_TEMPS:
            raise ValueError(f"line temp must be {', '.join(LINE_TEMPS)}")
        if self.minutes_per_kit < 1:
            raise ValueError("minutes_per_kit must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["bench_count"] = self.bench_count
        data["bench_volume_mm3"] = self.bench_volume_mm3
        data["aisle_row"] = self.aisle_row
        return data


PRESETS: dict[str, Line] = {
    "line_1x4": Line(
        id="line_1x4",
        name="4-bench aisle",
        rows=1,
        cols=4,
        length_mm=600,
        width_mm=500,
        height_mm=400,
        max_weight_kg=12,
        max_run=12,
        temp="ambient",
        minutes_per_kit=2,
        max_labor_min=48,
    ),
    "cell_2x3": Line(
        id="cell_2x3",
        name="2×3 kitting cell",
        rows=2,
        cols=3,
        length_mm=700,
        width_mm=600,
        height_mm=450,
        max_weight_kg=18,
        max_run=16,
        temp="ambient",
        minutes_per_kit=3,
        max_labor_min=90,
    ),
    "chill_1x3": Line(
        id="chill_1x3",
        name="3-bench chill line",
        rows=1,
        cols=3,
        length_mm=650,
        width_mm=500,
        height_mm=400,
        max_weight_kg=10,
        max_run=10,
        temp="chill",
        minutes_per_kit=3,
        max_labor_min=36,
    ),
    "mini_1x3": Line(
        id="mini_1x3",
        name="Demo 1×3 line",
        rows=1,
        cols=3,
        length_mm=600,
        width_mm=500,
        height_mm=400,
        max_weight_kg=12,
        max_run=8,
        temp="mixed",
        minutes_per_kit=2,
        max_labor_min=16,
    ),
}


def _int_or(raw: dict[str, Any], key: str, default: int) -> int:
    return int(raw[key]) if key in raw else default


def _float_or(raw: dict[str, Any], key: str, default: float) -> float:
    return float(raw[key]) if key in raw else default


def _line_from_parts(raw: dict[str, Any], default: Line | None = None) -> Line:
    return Line(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom line")),
        rows=_int_or(raw, "rows", default.rows if default else 1),
        cols=_int_or(raw, "cols", default.cols if default else 4),
        length_mm=_int_or(raw, "length_mm", default.length_mm if default else 600),
        width_mm=_int_or(raw, "width_mm", default.width_mm if default else 500),
        height_mm=_int_or(raw, "height_mm", default.height_mm if default else 400),
        max_weight_kg=_float_or(
            raw, "max_weight_kg", default.max_weight_kg if default else 12
        ),
        max_run=_int_or(raw, "max_run", default.max_run if default else 12),
        temp=str(raw.get("temp") or (default.temp if default else "ambient")).strip()
        or "ambient",
        minutes_per_kit=_int_or(
            raw, "minutes_per_kit", default.minutes_per_kit if default else 2
        ),
        max_labor_min=_int_or(
            raw, "max_labor_min", default.max_labor_min if default else 48
        ),
    )


def get_line(raw: dict[str, Any] | None) -> Line:
    payload = dict(raw or {})
    preset = payload.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown line preset '{preset}'")
        line = _line_from_parts(payload, PRESETS[preset])
        if "id" not in payload:
            line = Line(
                id=str(preset),
                name=line.name,
                rows=line.rows,
                cols=line.cols,
                length_mm=line.length_mm,
                width_mm=line.width_mm,
                height_mm=line.height_mm,
                max_weight_kg=line.max_weight_kg,
                max_run=line.max_run,
                temp=line.temp,
                minutes_per_kit=line.minutes_per_kit,
                max_labor_min=line.max_labor_min,
            )
        return line
    return _line_from_parts(payload)
