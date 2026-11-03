"""Warehouse floor catalogs.

Aisle lengths, capacities, and traverse minutes are working figures for a
planner, not a particular rack OEM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPS = ("dry", "chill", "freeze")
STRATEGIES = ("auto", "cutoff", "cluster", "compact")


@dataclass(frozen=True)
class Aisle:
    id: str
    temp: str
    capacity: int
    minutes: int
    one_way: bool = False

    def accepts_temp(self, temp: str) -> bool:
        if self.temp == "mixed":
            return temp in TEMPS
        return temp == self.temp

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Aisle id cannot be empty")
        if self.temp not in (*TEMPS, "mixed"):
            raise ValueError(f"Aisle {self.id} temp must be dry, chill, freeze, or mixed")
        if self.capacity < 1:
            raise ValueError(f"Aisle {self.id} capacity must be at least 1")
        if self.minutes < 1:
            raise ValueError(f"Aisle {self.id} traverse minutes must be at least 1")


@dataclass(frozen=True)
class Floor:
    id: str
    name: str
    aisles: tuple[Aisle, ...]
    minutes_per_cart: int
    minutes_per_pick: int
    minutes_per_hop: int
    max_labor_min: int
    horizon_min: int
    max_carts: int

    @property
    def aisle_ids(self) -> tuple[str, ...]:
        return tuple(aisle.id for aisle in self.aisles)

    def aisle_map(self) -> dict[str, Aisle]:
        return {aisle.id: aisle for aisle in self.aisles}

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "aisles": [aisle.as_dict() for aisle in self.aisles],
            "minutes_per_cart": self.minutes_per_cart,
            "minutes_per_pick": self.minutes_per_pick,
            "minutes_per_hop": self.minutes_per_hop,
            "max_labor_min": self.max_labor_min,
            "horizon_min": self.horizon_min,
            "max_carts": self.max_carts,
        }

    def validate(self) -> None:
        if not self.aisles:
            raise ValueError("Floor has no aisles")
        seen: set[str] = set()
        for aisle in self.aisles:
            aisle.validate()
            if aisle.id in seen:
                raise ValueError(f"Duplicate aisle id '{aisle.id}'")
            seen.add(aisle.id)
        if min(self.minutes_per_cart, self.minutes_per_pick, self.minutes_per_hop) < 0:
            raise ValueError("Floor minute rates cannot be negative")
        if self.max_labor_min < 1:
            raise ValueError("Floor labor cap must be at least 1 minute")
        if self.horizon_min < 1:
            raise ValueError("Floor horizon must be at least 1 minute")
        if self.max_carts < 1:
            raise ValueError("Floor max_carts must be at least 1")


def _aisles(ids: str, *, capacity: int, minutes: int, temp: str, one_way: bool = False) -> tuple[Aisle, ...]:
    return tuple(
        Aisle(letter, temp=temp, capacity=capacity, minutes=minutes, one_way=one_way) for letter in ids
    )


FLOORS: dict[str, Floor] = {
    "grocery": Floor(
        id="grocery",
        name="6-aisle grocery",
        aisles=_aisles("ABCDEF", capacity=2, minutes=4, temp="dry"),
        minutes_per_cart=5,
        minutes_per_pick=1,
        minutes_per_hop=1,
        max_labor_min=90,
        horizon_min=120,
        max_carts=12,
    ),
    "vna": Floor(
        id="vna",
        name="VNA turret",
        aisles=_aisles("ABCD", capacity=1, minutes=10, temp="dry", one_way=True),
        minutes_per_cart=6,
        minutes_per_pick=1,
        minutes_per_hop=2,
        max_labor_min=80,
        horizon_min=100,
        max_carts=6,
    ),
    "ecom": Floor(
        id="ecom",
        name="8-aisle each-pick",
        aisles=_aisles("ABCDEFGH", capacity=3, minutes=3, temp="dry"),
        minutes_per_cart=4,
        minutes_per_pick=1,
        minutes_per_hop=1,
        max_labor_min=120,
        horizon_min=150,
        max_carts=16,
    ),
    "chill": Floor(
        id="chill",
        name="4-aisle chill",
        aisles=_aisles("ABCD", capacity=1, minutes=6, temp="chill"),
        minutes_per_cart=6,
        minutes_per_pick=1,
        minutes_per_hop=1,
        max_labor_min=48,
        horizon_min=80,
        max_carts=6,
    ),
}


def _as_aisle(raw: dict, fallback: Aisle | None = None) -> Aisle:
    aisle = Aisle(
        id=str(raw.get("id") or (fallback.id if fallback else "")).strip(),
        temp=str(raw.get("temp") or (fallback.temp if fallback else "dry")),
        capacity=int(raw["capacity"] if "capacity" in raw and raw["capacity"] not in (None, "") else (fallback.capacity if fallback else 1)),
        minutes=int(raw["minutes"] if "minutes" in raw and raw["minutes"] not in (None, "") else (fallback.minutes if fallback else 4)),
        one_way=bool(raw["one_way"] if "one_way" in raw and raw["one_way"] not in (None, "") else (fallback.one_way if fallback else False)),
    )
    aisle.validate()
    return aisle


def get_floor(payload: dict) -> Floor:
    rate_fields = (
        "minutes_per_cart",
        "minutes_per_pick",
        "minutes_per_hop",
        "max_labor_min",
        "horizon_min",
        "max_carts",
    )
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in FLOORS:
            known = ", ".join(sorted(FLOORS))
            raise ValueError(f"Unknown floor preset '{key}'. Known: {known}")
        preset = FLOORS[key]
        values = {field: getattr(preset, field) for field in rate_fields}
        for field in rate_fields:
            if field in payload and payload[field] not in (None, ""):
                values[field] = int(payload[field])
        if payload.get("aisles"):
            aisles = tuple(_as_aisle(raw) for raw in payload["aisles"])
        else:
            aisles = preset.aisles
        floor = Floor(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            aisles=aisles,
            minutes_per_cart=int(values["minutes_per_cart"]),
            minutes_per_pick=int(values["minutes_per_pick"]),
            minutes_per_hop=int(values["minutes_per_hop"]),
            max_labor_min=int(values["max_labor_min"]),
            horizon_min=int(values["horizon_min"]),
            max_carts=int(values["max_carts"]),
        )
        floor.validate()
        return floor
    raw_aisles = payload.get("aisles") or []
    if not raw_aisles:
        raise ValueError("Custom floor missing: aisles")
    floor = Floor(
        id="custom",
        name=str(payload.get("name") or "Custom floor"),
        aisles=tuple(_as_aisle(raw) for raw in raw_aisles),
        minutes_per_cart=int(payload.get("minutes_per_cart", 5)),
        minutes_per_pick=int(payload.get("minutes_per_pick", 1)),
        minutes_per_hop=int(payload.get("minutes_per_hop", 1)),
        max_labor_min=int(payload.get("max_labor_min", 90)),
        horizon_min=int(payload.get("horizon_min", 120)),
        max_carts=int(payload.get("max_carts", 12)),
    )
    floor.validate()
    return floor
