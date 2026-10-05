"""Cross-dock yards: hours, staging lanes, and labor caps.

Lane sizes and clock figures are typical desk-side values, not a
particular WMS or YMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


TEMPS = ("dry", "reefer")


def clock_to_min(value: str) -> int:
    text = str(value).strip()
    if text in {"24:00", "24:00:00"}:
        return 24 * 60
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError(f"Time '{value}' must be HH:MM")
    hours, minutes = int(parts[0]), int(parts[1])
    total = hours * 60 + minutes
    if total < 0 or total > 24 * 60:
        raise ValueError(f"Time '{value}' is out of range")
    return total


def min_to_clock(total: int) -> str:
    total = max(0, int(total))
    hours, minutes = divmod(total, 60)
    if hours >= 24 and minutes == 0:
        return "24:00"
    return f"{hours:02d}:{minutes:02d}"


@dataclass(frozen=True)
class Lane:
    id: str
    temp: str
    max_pallets: int
    door: str
    row: int = 1

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each lane needs an id")
        if self.temp not in TEMPS:
            raise ValueError(f"Lane '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.max_pallets < 1:
            raise ValueError(f"Lane '{self.id}' max_pallets must be at least 1")
        if not self.door.strip():
            raise ValueError(f"Lane '{self.id}' needs a door")
        if self.row < 1:
            raise ValueError(f"Lane '{self.id}' row must be ≥ 1")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Yard:
    id: str
    name: str
    open: str
    close: str
    live_min: int
    unload_min: int
    load_min: int
    stage_min: int
    minutes_per_match: int
    lane_change_min: int
    max_matches: int
    max_labor_min: int
    lanes: tuple[Lane, ...]

    @property
    def open_min(self) -> int:
        return clock_to_min(self.open)

    @property
    def close_min(self) -> int:
        return clock_to_min(self.close)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Yard needs a name")
        if self.close_min <= self.open_min:
            raise ValueError("Yard close must be after open")
        if self.live_min < 1:
            raise ValueError("live_min must be at least 1")
        for field in ("unload_min", "load_min", "stage_min", "minutes_per_match"):
            if getattr(self, field) < 1:
                raise ValueError(f"{field} must be at least 1")
        if self.lane_change_min < 0:
            raise ValueError("lane_change_min cannot be negative")
        if self.max_matches < 1:
            raise ValueError("max_matches must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")
        if not self.lanes:
            raise ValueError("Yard has no staging lanes")
        seen: set[str] = set()
        for lane in self.lanes:
            lane.validate()
            if lane.id in seen:
                raise ValueError(f"Duplicate lane '{lane.id}'")
            seen.add(lane.id)

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["lanes"] = [lane.as_dict() for lane in self.lanes]
        data["lane_count"] = len(self.lanes)
        data["pallet_capacity"] = sum(lane.max_pallets for lane in self.lanes)
        return data

    def lane(self, lane_id: str) -> Lane | None:
        for item in self.lanes:
            if item.id == lane_id:
                return item
        return None


def _lanes(*rows: tuple[str, str, int, str, int]) -> tuple[Lane, ...]:
    return tuple(Lane(*row) for row in rows)


PRESETS: dict[str, Yard] = {
    "fmcg_6": Yard(
        id="fmcg_6",
        name="FMCG cross-dock",
        open="05:00",
        close="20:00",
        live_min=45,
        unload_min=20,
        load_min=20,
        stage_min=15,
        minutes_per_match=8,
        lane_change_min=4,
        max_matches=16,
        max_labor_min=180,
        lanes=_lanes(
            ("S1", "dry", 8, "D1", 1),
            ("S2", "dry", 8, "D1", 1),
            ("S3", "dry", 8, "D2", 2),
            ("S4", "dry", 8, "D2", 2),
            ("R1", "reefer", 6, "C1", 3),
            ("R2", "reefer", 6, "C1", 3),
        ),
    ),
    "ecom_4": Yard(
        id="ecom_4",
        name="E-comm parcel flow",
        open="08:00",
        close="22:00",
        live_min=30,
        unload_min=12,
        load_min=12,
        stage_min=10,
        minutes_per_match=6,
        lane_change_min=3,
        max_matches=12,
        max_labor_min=120,
        lanes=_lanes(
            ("L1", "dry", 6, "A", 1),
            ("L2", "dry", 6, "A", 1),
            ("L3", "dry", 6, "B", 2),
            ("L4", "dry", 6, "B", 2),
        ),
    ),
    "cold_4": Yard(
        id="cold_4",
        name="Cold-chain cross-dock",
        open="04:00",
        close="18:00",
        live_min=40,
        unload_min=25,
        load_min=25,
        stage_min=15,
        minutes_per_match=10,
        lane_change_min=5,
        max_matches=10,
        max_labor_min=150,
        lanes=_lanes(
            ("C1", "reefer", 6, "R1", 1),
            ("C2", "reefer", 6, "R1", 1),
            ("C3", "reefer", 6, "R2", 2),
            ("C4", "reefer", 6, "R2", 2),
        ),
    ),
    "mini_3": Yard(
        id="mini_3",
        name="Small demo dock",
        open="08:00",
        close="16:00",
        live_min=30,
        unload_min=15,
        load_min=15,
        stage_min=10,
        minutes_per_match=6,
        lane_change_min=3,
        max_matches=6,
        max_labor_min=40,
        lanes=_lanes(
            ("L1", "dry", 2, "D1", 1),
            ("L2", "dry", 2, "D2", 1),
            ("R1", "reefer", 2, "C1", 2),
        ),
    ),
}


def _lane_from_dict(raw: dict[str, Any]) -> Lane:
    return Lane(
        id=str(raw.get("id", "")).strip(),
        temp=str(raw.get("temp", "dry")).strip(),
        max_pallets=int(raw["max_pallets"]),
        door=str(raw.get("door", "")).strip(),
        row=int(raw.get("row", 1)),
    )


def _yard_from_parts(raw: dict[str, Any], default: Yard | None = None) -> Yard:
    base = default
    lanes_raw = raw.get("lanes")
    if lanes_raw is None and base is not None:
        lanes = base.lanes
    else:
        lanes = tuple(_lane_from_dict(item) for item in lanes_raw or [])
    return Yard(
        id=str(raw.get("id") or (base.id if base else "custom")),
        name=str(raw.get("name") or (base.name if base else "Custom yard")),
        open=str(raw.get("open") or (base.open if base else "08:00")),
        close=str(raw.get("close") or (base.close if base else "16:00")),
        live_min=int(raw["live_min"] if "live_min" in raw else (base.live_min if base else 30)),
        unload_min=int(raw["unload_min"] if "unload_min" in raw else (base.unload_min if base else 15)),
        load_min=int(raw["load_min"] if "load_min" in raw else (base.load_min if base else 15)),
        stage_min=int(raw["stage_min"] if "stage_min" in raw else (base.stage_min if base else 10)),
        minutes_per_match=int(
            raw["minutes_per_match"] if "minutes_per_match" in raw else (base.minutes_per_match if base else 6)
        ),
        lane_change_min=int(
            raw["lane_change_min"] if "lane_change_min" in raw else (base.lane_change_min if base else 3)
        ),
        max_matches=int(raw["max_matches"] if "max_matches" in raw else (base.max_matches if base else 8)),
        max_labor_min=int(
            raw["max_labor_min"] if "max_labor_min" in raw else (base.max_labor_min if base else 60)
        ),
        lanes=lanes,
    )


def get_yard(raw: dict[str, Any] | None) -> Yard:
    payload = dict(raw or {})
    preset = payload.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown yard preset '{preset}'")
        yard = _yard_from_parts(payload, PRESETS[preset])
        if "id" not in payload:
            yard = Yard(**{**asdict(yard), "id": str(preset), "lanes": yard.lanes})
        return yard
    return _yard_from_parts(payload)
