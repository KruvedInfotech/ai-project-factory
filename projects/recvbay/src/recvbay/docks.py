"""Inbound dock catalogs.

Door counts, staging pads, and shift lengths are working figures for a
planner, not a particular warehouse drawing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPS = ("dry", "chill", "freeze")
UNLOADS = ("live", "drop")
STRATEGIES = ("auto", "eta", "cluster", "compact")
TEMP_RANK = {"freeze": 0, "chill": 1, "dry": 2, "mixed": 2}
FLOOR_LOAD_NUM = 3
FLOOR_LOAD_DEN = 2


@dataclass(frozen=True)
class Door:
    id: str
    number: int
    temp: str
    has_leveler: bool
    has_reefer: bool
    staging_pallets: int
    height_mm: int

    def accepts_temp(self, temp: str) -> bool:
        if self.temp == "mixed":
            return temp in TEMPS
        return temp == self.temp

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Door id cannot be empty")
        if self.number < 1:
            raise ValueError(f"Door {self.id} number must be at least 1")
        if self.temp not in (*TEMPS, "mixed"):
            raise ValueError(f"Door {self.id} temp must be dry, chill, freeze, or mixed")
        if self.staging_pallets < 1:
            raise ValueError(f"Door {self.id} staging_pallets must be at least 1")
        if self.height_mm < 1:
            raise ValueError(f"Door {self.id} height_mm must be positive")


@dataclass(frozen=True)
class Dock:
    id: str
    name: str
    doors: tuple[Door, ...]
    minutes_per_pallet: int
    max_labor_min: int
    shift_end_min: int
    max_wait_min: int

    @property
    def door_ids(self) -> tuple[str, ...]:
        return tuple(door.id for door in self.doors)

    def door_map(self) -> dict[str, Door]:
        return {door.id: door for door in self.doors}

    def door_time_min(self) -> int:
        return len(self.doors) * self.shift_end_min

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "doors": [door.as_dict() for door in self.doors],
            "minutes_per_pallet": self.minutes_per_pallet,
            "max_labor_min": self.max_labor_min,
            "shift_end_min": self.shift_end_min,
            "max_wait_min": self.max_wait_min,
        }

    def validate(self) -> None:
        if not self.doors:
            raise ValueError("Dock has no doors")
        seen_ids: set[str] = set()
        seen_numbers: set[int] = set()
        for door in self.doors:
            door.validate()
            if door.id in seen_ids:
                raise ValueError(f"Duplicate door id '{door.id}'")
            if door.number in seen_numbers:
                raise ValueError(f"Duplicate door number {door.number}")
            seen_ids.add(door.id)
            seen_numbers.add(door.number)
        if self.minutes_per_pallet < 1:
            raise ValueError("Dock minutes_per_pallet must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("Dock labor cap must be at least 1 minute")
        if self.shift_end_min < 1:
            raise ValueError("Dock shift_end_min must be at least 1")
        if self.max_wait_min < 0:
            raise ValueError("Dock max_wait_min cannot be negative")


def duration_min(pallets: int, rate: int, floor_loaded: bool) -> int:
    """Unload minutes. Floor-loaded trailers take 1.5× the palletized rate."""
    base = pallets * rate
    if not floor_loaded:
        return base
    return (base * FLOOR_LOAD_NUM + FLOOR_LOAD_DEN - 1) // FLOOR_LOAD_DEN


def _doors(
    prefix: str,
    count: int,
    *,
    temp: str,
    number_start: int,
    has_leveler: bool,
    has_reefer: bool,
    staging_pallets: int,
    height_mm: int,
) -> tuple[Door, ...]:
    return tuple(
        Door(
            id=f"{prefix}{number_start + i - 1}",
            number=number_start + i - 1,
            temp=temp,
            has_leveler=has_leveler,
            has_reefer=has_reefer,
            staging_pallets=staging_pallets,
            height_mm=height_mm,
        )
        for i in range(1, count + 1)
    )


DOCKS: dict[str, Dock] = {
    "grocery": Dock(
        id="grocery",
        name="6-door grocery inbound",
        doors=(
            *_doors(
                "D",
                4,
                temp="dry",
                number_start=1,
                has_leveler=True,
                has_reefer=False,
                staging_pallets=24,
                height_mm=4500,
            ),
            *_doors(
                "D",
                2,
                temp="chill",
                number_start=5,
                has_leveler=True,
                has_reefer=True,
                staging_pallets=16,
                height_mm=4500,
            ),
        ),
        minutes_per_pallet=8,
        max_labor_min=240,
        shift_end_min=480,
        max_wait_min=30,
    ),
    "produce": Dock(
        id="produce",
        name="4-door produce inbound",
        doors=(
            *_doors(
                "C",
                2,
                temp="chill",
                number_start=1,
                has_leveler=True,
                has_reefer=True,
                staging_pallets=12,
                height_mm=4200,
            ),
            *_doors(
                "F",
                2,
                temp="freeze",
                number_start=3,
                has_leveler=True,
                has_reefer=True,
                staging_pallets=10,
                height_mm=4200,
            ),
        ),
        minutes_per_pallet=10,
        max_labor_min=160,
        shift_end_min=360,
        max_wait_min=20,
    ),
    "dc": Dock(
        id="dc",
        name="8-door store DC inbound",
        doors=_doors(
            "S",
            8,
            temp="dry",
            number_start=11,
            has_leveler=True,
            has_reefer=False,
            staging_pallets=32,
            height_mm=4500,
        ),
        minutes_per_pallet=6,
        max_labor_min=360,
        shift_end_min=600,
        max_wait_min=45,
    ),
    "parcel": Dock(
        id="parcel",
        name="4-door parcel inbound",
        doors=_doors(
            "P",
            4,
            temp="mixed",
            number_start=1,
            has_leveler=False,
            has_reefer=False,
            staging_pallets=8,
            height_mm=4500,
        ),
        minutes_per_pallet=4,
        max_labor_min=80,
        shift_end_min=240,
        max_wait_min=15,
    ),
}


def _as_bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _as_door(raw: dict, fallback: Door | None = None) -> Door:
    def pick(key: str, default):
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
        return default

    door = Door(
        id=str(pick("id", fallback.id if fallback else "")).strip(),
        number=int(pick("number", fallback.number if fallback else 1)),
        temp=str(pick("temp", fallback.temp if fallback else "dry")),
        has_leveler=_as_bool(pick("has_leveler", fallback.has_leveler if fallback else True), True),
        has_reefer=_as_bool(pick("has_reefer", fallback.has_reefer if fallback else False), False),
        staging_pallets=int(pick("staging_pallets", fallback.staging_pallets if fallback else 24)),
        height_mm=int(pick("height_mm", fallback.height_mm if fallback else 4500)),
    )
    door.validate()
    return door


def get_dock(payload: dict) -> Dock:
    rate_fields = ("minutes_per_pallet", "max_labor_min", "shift_end_min", "max_wait_min")
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in DOCKS:
            known = ", ".join(sorted(DOCKS))
            raise ValueError(f"Unknown dock preset '{key}'. Known: {known}")
        preset = DOCKS[key]
        values = {field: getattr(preset, field) for field in rate_fields}
        for field in rate_fields:
            if field in payload and payload[field] not in (None, ""):
                values[field] = int(payload[field])
        if payload.get("doors"):
            doors = tuple(_as_door(raw) for raw in payload["doors"])
        else:
            doors = preset.doors
        dock = Dock(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            doors=doors,
            minutes_per_pallet=int(values["minutes_per_pallet"]),
            max_labor_min=int(values["max_labor_min"]),
            shift_end_min=int(values["shift_end_min"]),
            max_wait_min=int(values["max_wait_min"]),
        )
        dock.validate()
        return dock
    raw_doors = payload.get("doors") or []
    if not raw_doors:
        raise ValueError("Custom dock missing: doors")
    dock = Dock(
        id="custom",
        name=str(payload.get("name") or "Custom inbound dock"),
        doors=tuple(_as_door(raw) for raw in raw_doors),
        minutes_per_pallet=int(payload.get("minutes_per_pallet", 8)),
        max_labor_min=int(payload.get("max_labor_min", 240)),
        shift_end_min=int(payload.get("shift_end_min", 480)),
        max_wait_min=int(payload.get("max_wait_min", 30)),
    )
    dock.validate()
    return dock
