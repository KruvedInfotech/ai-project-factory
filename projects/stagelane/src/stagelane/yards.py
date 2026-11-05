"""Outbound staging-yard catalogs.

Lane lengths, doors, and floor loads are working figures for a planner,
not a particular warehouse drawing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPS = ("dry", "chill", "freeze")
STRATEGIES = ("auto", "cutoff", "cluster", "compact")
TEMP_RANK = {"freeze": 0, "chill": 1, "dry": 2, "mixed": 2}


@dataclass(frozen=True)
class Lane:
    id: str
    temp: str
    length_mm: int
    width_mm: int
    max_weight_kg: float
    max_height_mm: int
    door: int | None = None

    def accepts_temp(self, temp: str) -> bool:
        if self.temp == "mixed":
            return temp in TEMPS
        return temp == self.temp

    def is_warmer_than(self, temp: str) -> bool:
        return TEMP_RANK.get(self.temp, 2) > TEMP_RANK.get(temp, 2)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Lane id cannot be empty")
        if self.temp not in (*TEMPS, "mixed"):
            raise ValueError(f"Lane {self.id} temp must be dry, chill, freeze, or mixed")
        if self.length_mm < 1 or self.width_mm < 1 or self.max_height_mm < 1:
            raise ValueError(f"Lane {self.id} dimensions must be positive")
        if self.max_weight_kg <= 0:
            raise ValueError(f"Lane {self.id} max_weight_kg must be positive")
        if self.door is not None and self.door < 1:
            raise ValueError(f"Lane {self.id} door must be at least 1")


@dataclass(frozen=True)
class Yard:
    id: str
    name: str
    lanes: tuple[Lane, ...]
    minutes_per_pallet: int
    max_labor_min: int
    max_pallets: int
    max_dwell_min: int

    @property
    def lane_ids(self) -> tuple[str, ...]:
        return tuple(lane.id for lane in self.lanes)

    def lane_map(self) -> dict[str, Lane]:
        return {lane.id: lane for lane in self.lanes}

    @property
    def length_mm(self) -> int:
        return sum(lane.length_mm for lane in self.lanes)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "lanes": [lane.as_dict() for lane in self.lanes],
            "minutes_per_pallet": self.minutes_per_pallet,
            "max_labor_min": self.max_labor_min,
            "max_pallets": self.max_pallets,
            "max_dwell_min": self.max_dwell_min,
        }

    def validate(self) -> None:
        if not self.lanes:
            raise ValueError("Yard has no lanes")
        seen: set[str] = set()
        for lane in self.lanes:
            lane.validate()
            if lane.id in seen:
                raise ValueError(f"Duplicate lane id '{lane.id}'")
            seen.add(lane.id)
        if self.minutes_per_pallet < 0:
            raise ValueError("Yard minutes_per_pallet cannot be negative")
        if self.max_labor_min < 1:
            raise ValueError("Yard labor cap must be at least 1 minute")
        if self.max_pallets < 1:
            raise ValueError("Yard max_pallets must be at least 1")
        if self.max_dwell_min < 0:
            raise ValueError("Yard max_dwell_min cannot be negative")


def _lanes(
    prefix: str,
    count: int,
    *,
    temp: str,
    length_mm: int,
    width_mm: int,
    max_weight_kg: float,
    max_height_mm: int,
    door_start: int,
) -> tuple[Lane, ...]:
    return tuple(
        Lane(
            id=f"{prefix}{i}",
            temp=temp,
            length_mm=length_mm,
            width_mm=width_mm,
            max_weight_kg=max_weight_kg,
            max_height_mm=max_height_mm,
            door=door_start + i - 1,
        )
        for i in range(1, count + 1)
    )


YARDS: dict[str, Yard] = {
    "grocery": Yard(
        id="grocery",
        name="6-lane grocery dock",
        lanes=_lanes(
            "L",
            6,
            temp="dry",
            length_mm=9600,
            width_mm=1200,
            max_weight_kg=8000,
            max_height_mm=1800,
            door_start=1,
        ),
        minutes_per_pallet=6,
        max_labor_min=90,
        max_pallets=48,
        max_dwell_min=0,
    ),
    "parcel": Yard(
        id="parcel",
        name="4-lane parcel cages",
        lanes=_lanes(
            "P",
            4,
            temp="mixed",
            length_mm=3600,
            width_mm=1200,
            max_weight_kg=2000,
            max_height_mm=1800,
            door_start=1,
        ),
        minutes_per_pallet=4,
        max_labor_min=60,
        max_pallets=16,
        max_dwell_min=20,
    ),
    "dc": Yard(
        id="dc",
        name="4-lane store DC",
        lanes=_lanes(
            "S",
            4,
            temp="dry",
            length_mm=14400,
            width_mm=1200,
            max_weight_kg=12000,
            max_height_mm=2000,
            door_start=11,
        ),
        minutes_per_pallet=8,
        max_labor_min=120,
        max_pallets=48,
        max_dwell_min=0,
    ),
    "chill": Yard(
        id="chill",
        name="4-lane chill dock",
        lanes=_lanes(
            "C",
            4,
            temp="chill",
            length_mm=7200,
            width_mm=1200,
            max_weight_kg=6000,
            max_height_mm=1600,
            door_start=1,
        ),
        minutes_per_pallet=7,
        max_labor_min=48,
        max_pallets=24,
        max_dwell_min=25,
    ),
}


def _as_lane(raw: dict, fallback: Lane | None = None) -> Lane:
    def pick(key: str, default):
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
        return default

    door_raw = pick("door", fallback.door if fallback else None)
    lane = Lane(
        id=str(pick("id", fallback.id if fallback else "")).strip(),
        temp=str(pick("temp", fallback.temp if fallback else "dry")),
        length_mm=int(pick("length_mm", fallback.length_mm if fallback else 9600)),
        width_mm=int(pick("width_mm", fallback.width_mm if fallback else 1200)),
        max_weight_kg=float(pick("max_weight_kg", fallback.max_weight_kg if fallback else 8000)),
        max_height_mm=int(pick("max_height_mm", fallback.max_height_mm if fallback else 1800)),
        door=None if door_raw in (None, "") else int(door_raw),
    )
    lane.validate()
    return lane


def get_yard(payload: dict) -> Yard:
    rate_fields = ("minutes_per_pallet", "max_labor_min", "max_pallets", "max_dwell_min")
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in YARDS:
            known = ", ".join(sorted(YARDS))
            raise ValueError(f"Unknown yard preset '{key}'. Known: {known}")
        preset = YARDS[key]
        values = {field: getattr(preset, field) for field in rate_fields}
        for field in rate_fields:
            if field in payload and payload[field] not in (None, ""):
                values[field] = int(payload[field])
        if payload.get("lanes"):
            lanes = tuple(_as_lane(raw) for raw in payload["lanes"])
        else:
            lanes = preset.lanes
        yard = Yard(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            lanes=lanes,
            minutes_per_pallet=int(values["minutes_per_pallet"]),
            max_labor_min=int(values["max_labor_min"]),
            max_pallets=int(values["max_pallets"]),
            max_dwell_min=int(values["max_dwell_min"]),
        )
        yard.validate()
        return yard
    raw_lanes = payload.get("lanes") or []
    if not raw_lanes:
        raise ValueError("Custom yard missing: lanes")
    yard = Yard(
        id="custom",
        name=str(payload.get("name") or "Custom yard"),
        lanes=tuple(_as_lane(raw) for raw in raw_lanes),
        minutes_per_pallet=int(payload.get("minutes_per_pallet", 6)),
        max_labor_min=int(payload.get("max_labor_min", 90)),
        max_pallets=int(payload.get("max_pallets", 48)),
        max_dwell_min=int(payload.get("max_dwell_min", 0)),
    )
    yard.validate()
    return yard
