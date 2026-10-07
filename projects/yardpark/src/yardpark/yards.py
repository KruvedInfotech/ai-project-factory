"""Yard layouts: parking spots, hours, and hostler labor.

Spot sizes and clock figures are typical desk-side values, not a
particular YMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SPOT_KINDS = ("dry", "reefer", "power")
TEMPS = ("dry", "reefer")
TRAILER_KINDS = ("inbound", "outbound", "empty")


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
class Spot:
    id: str
    row: str
    bay: int
    kind: str
    door: str
    walk_min: int
    max_ft: int = 53

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each spot needs an id")
        if not self.row.strip():
            raise ValueError(f"Spot '{self.id}' needs a row")
        if self.bay < 1:
            raise ValueError(f"Spot '{self.id}' bay must be at least 1")
        if self.kind not in SPOT_KINDS:
            raise ValueError(f"Spot '{self.id}' kind must be {', '.join(SPOT_KINDS)}")
        if not self.door.strip():
            raise ValueError(f"Spot '{self.id}' needs a nearest door")
        if self.walk_min < 1:
            raise ValueError(f"Spot '{self.id}' walk_min must be at least 1")
        if self.max_ft < 1:
            raise ValueError(f"Spot '{self.id}' max_ft must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Yard:
    id: str
    name: str
    open: str
    close: str
    minutes_per_move: int
    row_change_min: int
    pull_lead_min: int
    max_moves: int
    max_labor_min: int
    spots: tuple[Spot, ...]

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
        if self.minutes_per_move < 1:
            raise ValueError("minutes_per_move must be at least 1")
        if self.row_change_min < 0:
            raise ValueError("row_change_min cannot be negative")
        if self.pull_lead_min < 0:
            raise ValueError("pull_lead_min cannot be negative")
        if self.max_moves < 1:
            raise ValueError("max_moves must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")
        if not self.spots:
            raise ValueError("Yard has no parking spots")
        seen: set[str] = set()
        for spot in self.spots:
            spot.validate()
            if spot.id in seen:
                raise ValueError(f"Duplicate spot '{spot.id}'")
            seen.add(spot.id)

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["spots"] = [spot.as_dict() for spot in self.spots]
        data["spot_count"] = len(self.spots)
        data["reefer_spots"] = sum(1 for spot in self.spots if spot.kind in {"reefer", "power"})
        return data

    def spot(self, spot_id: str) -> Spot | None:
        for item in self.spots:
            if item.id == spot_id:
                return item
        return None


def _spots(*rows: tuple[object, ...]) -> tuple[Spot, ...]:
    built: list[Spot] = []
    for row in rows:
        if len(row) == 6:
            ident, aisle, bay, kind, door, walk_min = row
            built.append(
                Spot(
                    id=str(ident),
                    row=str(aisle),
                    bay=int(bay),
                    kind=str(kind),
                    door=str(door),
                    walk_min=int(walk_min),
                )
            )
        else:
            ident, aisle, bay, kind, door, walk_min, max_ft = row
            built.append(
                Spot(
                    id=str(ident),
                    row=str(aisle),
                    bay=int(bay),
                    kind=str(kind),
                    door=str(door),
                    walk_min=int(walk_min),
                    max_ft=int(max_ft),
                )
            )
    return tuple(built)


PRESETS: dict[str, Yard] = {
    "mini_6": Yard(
        id="mini_6",
        name="Small demo yard",
        open="08:00",
        close="16:00",
        minutes_per_move=8,
        row_change_min=4,
        pull_lead_min=20,
        max_moves=6,
        max_labor_min=45,
        spots=_spots(
            ("Y1-1", "Y1", 1, "dry", "D1", 4),
            ("Y1-2", "Y1", 2, "dry", "D1", 6),
            ("Y2-1", "Y2", 1, "dry", "D2", 4),
            ("Y2-2", "Y2", 2, "dry", "D2", 6),
            ("Y3-1", "Y3", 1, "reefer", "D3", 5),
            ("Y3-2", "Y3", 2, "reefer", "D3", 7),
        ),
    ),
    "metro_10": Yard(
        id="metro_10",
        name="City DC yard",
        open="07:00",
        close="19:00",
        minutes_per_move=7,
        row_change_min=3,
        pull_lead_min=25,
        max_moves=10,
        max_labor_min=120,
        spots=_spots(
            ("A1", "A", 1, "dry", "D1", 3),
            ("A2", "A", 2, "dry", "D1", 4),
            ("A3", "A", 3, "dry", "D1", 5),
            ("A4", "A", 4, "dry", "D1", 6, 28),
            ("B1", "B", 1, "dry", "D2", 3),
            ("B2", "B", 2, "dry", "D2", 5),
            ("B3", "B", 3, "dry", "D2", 7),
            ("C1", "C", 1, "reefer", "D3", 4),
            ("C2", "C", 2, "reefer", "D3", 6),
            ("C3", "C", 3, "power", "D3", 3),
        ),
    ),
    "dc_20": Yard(
        id="dc_20",
        name="Regional DC yard",
        open="05:00",
        close="22:00",
        minutes_per_move=8,
        row_change_min=4,
        pull_lead_min=30,
        max_moves=18,
        max_labor_min=240,
        spots=_spots(
            ("A1", "A", 1, "dry", "D1", 3),
            ("A2", "A", 2, "dry", "D1", 4),
            ("A3", "A", 3, "dry", "D1", 5),
            ("A4", "A", 4, "dry", "D1", 6),
            ("A5", "A", 5, "dry", "D1", 7),
            ("B1", "B", 1, "dry", "D2", 3),
            ("B2", "B", 2, "dry", "D2", 4),
            ("B3", "B", 3, "dry", "D2", 5),
            ("B4", "B", 4, "dry", "D2", 6),
            ("B5", "B", 5, "dry", "D2", 7),
            ("C1", "C", 1, "dry", "D3", 4),
            ("C2", "C", 2, "dry", "D3", 5),
            ("C3", "C", 3, "dry", "D3", 6),
            ("C4", "C", 4, "reefer", "D3", 5),
            ("C5", "C", 5, "reefer", "D3", 6),
            ("D1", "D", 1, "reefer", "D4", 4),
            ("D2", "D", 2, "reefer", "D4", 5),
            ("D3", "D", 3, "reefer", "D4", 6),
            ("D4", "D", 4, "power", "D4", 3),
            ("D5", "D", 5, "power", "D4", 4),
        ),
    ),
    "cold_8": Yard(
        id="cold_8",
        name="Cold-campus yard",
        open="04:00",
        close="20:00",
        minutes_per_move=10,
        row_change_min=5,
        pull_lead_min=25,
        max_moves=8,
        max_labor_min=150,
        spots=_spots(
            ("R1", "R", 1, "reefer", "C1", 4),
            ("R2", "R", 2, "reefer", "C1", 5),
            ("R3", "R", 3, "reefer", "C1", 6),
            ("R4", "R", 4, "reefer", "C2", 4),
            ("R5", "R", 5, "reefer", "C2", 5),
            ("R6", "R", 6, "reefer", "C2", 7),
            ("P1", "P", 1, "power", "C1", 3),
            ("P2", "P", 2, "power", "C1", 4),
        ),
    ),
}


def _spot_from_dict(raw: dict[str, Any]) -> Spot:
    return Spot(
        id=str(raw.get("id", "")).strip(),
        row=str(raw.get("row", "")).strip(),
        bay=int(raw["bay"]),
        kind=str(raw.get("kind", "dry")).strip(),
        door=str(raw.get("door", "")).strip(),
        walk_min=int(raw["walk_min"]),
        max_ft=int(raw.get("max_ft", 53)),
    )


def _int_or(raw: dict[str, Any], key: str, default: int) -> int:
    return int(raw[key]) if key in raw else default


def _yard_from_parts(raw: dict[str, Any], default: Yard | None = None) -> Yard:
    spots_raw = raw.get("spots")
    if spots_raw is None and default is not None:
        spots = default.spots
    else:
        spots = tuple(_spot_from_dict(item) for item in spots_raw or [])
    return Yard(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom yard")),
        open=str(raw.get("open") or (default.open if default else "08:00")),
        close=str(raw.get("close") or (default.close if default else "16:00")),
        minutes_per_move=_int_or(raw, "minutes_per_move", default.minutes_per_move if default else 8),
        row_change_min=_int_or(raw, "row_change_min", default.row_change_min if default else 4),
        pull_lead_min=_int_or(raw, "pull_lead_min", default.pull_lead_min if default else 20),
        max_moves=_int_or(raw, "max_moves", default.max_moves if default else 8),
        max_labor_min=_int_or(raw, "max_labor_min", default.max_labor_min if default else 60),
        spots=spots,
    )


def get_yard(raw: dict[str, Any] | None) -> Yard:
    payload = dict(raw or {})
    preset = payload.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown yard preset '{preset}'")
        yard = _yard_from_parts(payload, PRESETS[preset])
        if "id" not in payload:
            yard = Yard(**{**asdict(yard), "id": str(preset), "spots": yard.spots})
        return yard
    return _yard_from_parts(payload)
