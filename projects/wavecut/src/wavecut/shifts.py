"""Shift clocks and wave-slot capacities.

Hours and caps are typical working figures for a one-day outbound desk,
not a particular WMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


def parse_hhmm(value: str) -> int:
    text = str(value).strip()
    if text == "24:00":
        return 24 * 60
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"Time '{value}' must be HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    if hour == 24 and minute == 0:
        return 24 * 60
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time '{value}' is out of range")
    return hour * 60 + minute


def format_hhmm(total_min: int) -> str:
    if total_min >= 24 * 60:
        return "24:00"
    hour, minute = divmod(int(total_min), 60)
    return f"{hour:02d}:{minute:02d}"


@dataclass(frozen=True)
class Shift:
    id: str
    name: str
    open_min: int
    close_min: int
    wave_min: int
    max_orders: int
    max_lines: int
    max_cube_m3: float
    max_pick_min: int
    zone_pure: bool = False

    @property
    def open(self) -> str:
        return format_hhmm(self.open_min)

    @property
    def close(self) -> str:
        return format_hhmm(self.close_min)

    @property
    def span_min(self) -> int:
        return self.close_min - self.open_min

    def slots(self) -> list[tuple[int, int]]:
        if self.wave_min < 1:
            raise ValueError("Wave length must be at least 1 minute")
        starts: list[tuple[int, int]] = []
        start = self.open_min
        while start + self.wave_min <= self.close_min:
            starts.append((start, start + self.wave_min))
            start += self.wave_min
        return starts

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["open"] = self.open
        data["close"] = self.close
        data["wave_count"] = len(self.slots())
        return data


PRESETS: dict[str, Shift] = {
    "grocery_am": Shift(
        id="grocery_am",
        name="Grocery AM replenishment",
        open_min=5 * 60,
        close_min=12 * 60,
        wave_min=30,
        max_orders=3,
        max_lines=28,
        max_cube_m3=2.0,
        max_pick_min=70,
        zone_pure=False,
    ),
    "ecom_day": Shift(
        id="ecom_day",
        name="E-commerce day shift",
        open_min=8 * 60,
        close_min=20 * 60,
        wave_min=45,
        max_orders=4,
        max_lines=20,
        max_cube_m3=1.2,
        max_pick_min=50,
        zone_pure=False,
    ),
    "wholesale_pm": Shift(
        id="wholesale_pm",
        name="Wholesale PM dispatch",
        open_min=12 * 60,
        close_min=22 * 60,
        wave_min=60,
        max_orders=8,
        max_lines=120,
        max_cube_m3=16.0,
        max_pick_min=240,
        zone_pure=True,
    ),
    "mini_3": Shift(
        id="mini_3",
        name="Small demo shift",
        open_min=8 * 60,
        close_min=12 * 60,
        wave_min=60,
        max_orders=3,
        max_lines=20,
        max_cube_m3=2.0,
        max_pick_min=60,
        zone_pure=False,
    ),
}


def get_shift(raw: dict[str, object]) -> Shift:
    if "preset" in raw:
        key = str(raw["preset"])
        if key not in PRESETS:
            raise ValueError(f"Unknown shift preset '{key}'. Known: {', '.join(sorted(PRESETS))}")
        base = PRESETS[key]
        updates: dict[str, object] = {}
        if "open" in raw:
            updates["open_min"] = parse_hhmm(str(raw["open"]))
        if "close" in raw:
            updates["close_min"] = parse_hhmm(str(raw["close"]))
        if "wave_min" in raw:
            updates["wave_min"] = int(raw["wave_min"])  # type: ignore[arg-type]
        if "max_orders" in raw:
            updates["max_orders"] = int(raw["max_orders"])  # type: ignore[arg-type]
        if "max_lines" in raw:
            updates["max_lines"] = int(raw["max_lines"])  # type: ignore[arg-type]
        if "max_cube_m3" in raw:
            updates["max_cube_m3"] = float(raw["max_cube_m3"])  # type: ignore[arg-type]
        if "max_pick_min" in raw:
            updates["max_pick_min"] = int(raw["max_pick_min"])  # type: ignore[arg-type]
        if "zone_pure" in raw:
            updates["zone_pure"] = bool(raw["zone_pure"])
        if "name" in raw:
            updates["name"] = str(raw["name"])
        return Shift(
            id=base.id,
            name=str(updates.get("name", base.name)),
            open_min=int(updates.get("open_min", base.open_min)),
            close_min=int(updates.get("close_min", base.close_min)),
            wave_min=int(updates.get("wave_min", base.wave_min)),
            max_orders=int(updates.get("max_orders", base.max_orders)),
            max_lines=int(updates.get("max_lines", base.max_lines)),
            max_cube_m3=float(updates.get("max_cube_m3", base.max_cube_m3)),
            max_pick_min=int(updates.get("max_pick_min", base.max_pick_min)),
            zone_pure=bool(updates.get("zone_pure", base.zone_pure)),
        )

    doors = raw  # custom shift
    required = (
        "name",
        "open",
        "close",
        "wave_min",
        "max_orders",
        "max_lines",
        "max_cube_m3",
        "max_pick_min",
    )
    missing = [key for key in required if key not in doors]
    if missing:
        raise ValueError(f"Custom shift is missing: {', '.join(missing)}")
    return Shift(
        id=str(raw.get("id", "custom")),
        name=str(raw["name"]),
        open_min=parse_hhmm(str(raw["open"])),
        close_min=parse_hhmm(str(raw["close"])),
        wave_min=int(raw["wave_min"]),
        max_orders=int(raw["max_orders"]),
        max_lines=int(raw["max_lines"]),
        max_cube_m3=float(raw["max_cube_m3"]),
        max_pick_min=int(raw["max_pick_min"]),
        zone_pure=bool(raw.get("zone_pure", False)),
    )
