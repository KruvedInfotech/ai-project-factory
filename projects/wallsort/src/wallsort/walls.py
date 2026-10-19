"""Put-wall decks: cubby grids a packer stands in front of.

Figures are typical inner cubby numbers, not a particular fixture brand.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STRATEGIES = ("auto", "priority", "carrier", "compact")
TEMPS = ("ambient", "chill")
WALL_TEMPS = ("ambient", "chill", "mixed")


@dataclass(frozen=True)
class Wall:
    id: str
    name: str
    rows: int
    cols: int
    length_mm: int
    width_mm: int
    height_mm: int
    max_weight_kg: float
    temp: str
    minutes_per_unit: int
    max_labor_min: int

    @property
    def cubby_count(self) -> int:
        return self.rows * self.cols

    @property
    def cubby_volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    @property
    def golden_row(self) -> int:
        return (self.rows + 1) // 2

    @property
    def mid_col(self) -> float:
        return (self.cols + 1) / 2

    def cubby_id(self, row: int, col: int) -> str:
        return f"R{row}C{col}"

    def zone_of(self, row: int) -> str:
        if self.rows == 1 or row == self.golden_row:
            return "waist"
        if row < self.golden_row:
            return "stretch"
        return "stoop"

    def golden_score(self, row: int, col: int) -> float:
        return abs(row - self.golden_row) * 2 + abs(col - self.mid_col)

    def raster_index(self, row: int, col: int) -> int:
        return (row - 1) * self.cols + (col - 1)

    def accepts_temp(self, unit_temp: str) -> bool:
        if self.temp == "mixed":
            return True
        return unit_temp == self.temp

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Wall needs a name")
        if self.rows < 1:
            raise ValueError("rows must be at least 1")
        if self.cols < 1:
            raise ValueError("cols must be at least 1")
        if self.length_mm < 1 or self.width_mm < 1 or self.height_mm < 1:
            raise ValueError("cubby dimensions must be at least 1 mm")
        if self.max_weight_kg <= 0:
            raise ValueError("max_weight_kg must be positive")
        if self.temp not in WALL_TEMPS:
            raise ValueError(f"wall temp must be {', '.join(WALL_TEMPS)}")
        if self.minutes_per_unit < 1:
            raise ValueError("minutes_per_unit must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["cubby_count"] = self.cubby_count
        data["cubby_volume_mm3"] = self.cubby_volume_mm3
        data["golden_row"] = self.golden_row
        return data


PRESETS: dict[str, Wall] = {
    "wall_3x4": Wall(
        id="wall_3x4",
        name="3×4 pack wall",
        rows=3,
        cols=4,
        length_mm=400,
        width_mm=300,
        height_mm=350,
        max_weight_kg=8,
        temp="ambient",
        minutes_per_unit=1,
        max_labor_min=30,
    ),
    "pack_2x6": Wall(
        id="pack_2x6",
        name="2×6 pack bench",
        rows=2,
        cols=6,
        length_mm=350,
        width_mm=250,
        height_mm=300,
        max_weight_kg=6,
        temp="ambient",
        minutes_per_unit=1,
        max_labor_min=20,
    ),
    "chill_2x4": Wall(
        id="chill_2x4",
        name="2×4 chill wall",
        rows=2,
        cols=4,
        length_mm=450,
        width_mm=350,
        height_mm=400,
        max_weight_kg=12,
        temp="chill",
        minutes_per_unit=1,
        max_labor_min=16,
    ),
    "mini_2x3": Wall(
        id="mini_2x3",
        name="Demo 2×3 wall",
        rows=2,
        cols=3,
        length_mm=400,
        width_mm=300,
        height_mm=350,
        max_weight_kg=8,
        temp="mixed",
        minutes_per_unit=1,
        max_labor_min=8,
    ),
}


def _int_or(raw: dict[str, Any], key: str, default: int) -> int:
    return int(raw[key]) if key in raw else default


def _float_or(raw: dict[str, Any], key: str, default: float) -> float:
    return float(raw[key]) if key in raw else default


def _wall_from_parts(raw: dict[str, Any], default: Wall | None = None) -> Wall:
    return Wall(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom wall")),
        rows=_int_or(raw, "rows", default.rows if default else 3),
        cols=_int_or(raw, "cols", default.cols if default else 4),
        length_mm=_int_or(raw, "length_mm", default.length_mm if default else 400),
        width_mm=_int_or(raw, "width_mm", default.width_mm if default else 300),
        height_mm=_int_or(raw, "height_mm", default.height_mm if default else 350),
        max_weight_kg=_float_or(
            raw, "max_weight_kg", default.max_weight_kg if default else 8
        ),
        temp=str(raw.get("temp") or (default.temp if default else "ambient")).strip()
        or "ambient",
        minutes_per_unit=_int_or(
            raw, "minutes_per_unit", default.minutes_per_unit if default else 1
        ),
        max_labor_min=_int_or(
            raw, "max_labor_min", default.max_labor_min if default else 20
        ),
    )


def get_wall(raw: dict[str, Any] | None) -> Wall:
    payload = dict(raw or {})
    preset = payload.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown wall preset '{preset}'")
        wall = _wall_from_parts(payload, PRESETS[preset])
        if "id" not in payload:
            wall = Wall(
                id=str(preset),
                name=wall.name,
                rows=wall.rows,
                cols=wall.cols,
                length_mm=wall.length_mm,
                width_mm=wall.width_mm,
                height_mm=wall.height_mm,
                max_weight_kg=wall.max_weight_kg,
                temp=wall.temp,
                minutes_per_unit=wall.minutes_per_unit,
                max_labor_min=wall.max_labor_min,
            )
        return wall
    return _wall_from_parts(payload)
