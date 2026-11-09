"""Warehouse floor catalogs.

Aisle counts, cell sizes, and truck speeds are working figures for a
planner, not a particular warehouse drawing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


KINDS = ("putaway", "replen", "pick", "relocate")
INBOUND = ("putaway", "replen")
OUTBOUND = ("pick",)
EQUIPMENT = ("reach", "sitdown", "jack")
TEMPS = ("dry", "chill", "freeze")
LOCATION_KINDS = ("dock", "staging", "aisle", "reserve")
STRATEGIES = ("auto", "nearest", "dual", "fifo")

# Reach is slow in the rack; sit-down is quicker on the apron; jacks
# shuffle dock to staging. Mast heights are typical inner clearances.
KIND_MAST_MM = {"jack": 1800, "sitdown": 2800, "reach": 12000}
KIND_CELLS_PER_MIN = {"jack": 10, "sitdown": 16, "reach": 8}
KIND_PALLETS = {"jack": 1, "sitdown": 2, "reach": 1}
KIND_WEIGHT_KG = {"jack": 800, "sitdown": 2000, "reach": 1200}
KIND_LOCATIONS = {
    "jack": frozenset({"dock", "staging"}),
    "sitdown": frozenset({"dock", "staging", "aisle"}),
    "reach": frozenset({"dock", "staging", "aisle", "reserve"}),
}


@dataclass(frozen=True)
class Location:
    id: str
    kind: str
    x: int
    y: int
    temp: str
    max_height_mm: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Location id cannot be empty")
        if self.kind not in LOCATION_KINDS:
            raise ValueError(f"Location {self.id} kind must be {', '.join(LOCATION_KINDS)}")
        if self.temp not in (*TEMPS, "mixed"):
            raise ValueError(f"Location {self.id} temp must be dry, chill, freeze, or mixed")
        if self.max_height_mm < 1:
            raise ValueError(f"Location {self.id} max_height_mm must be positive")


@dataclass(frozen=True)
class Truck:
    id: str
    kind: str
    start: str
    temp: str
    pallets: int
    max_weight_kg: int
    mast_mm: int
    cells_per_min: int

    def accepts_temp(self, temp: str) -> bool:
        if self.temp == "mixed":
            return temp in TEMPS
        return temp == self.temp

    def accepts_location(self, location: Location) -> bool:
        return location.kind in KIND_LOCATIONS[self.kind]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Truck id cannot be empty")
        if self.kind not in EQUIPMENT:
            raise ValueError(f"Truck {self.id} kind must be {', '.join(EQUIPMENT)}")
        if not self.start.strip():
            raise ValueError(f"Truck {self.id} needs a start location")
        if self.temp not in (*TEMPS, "mixed"):
            raise ValueError(f"Truck {self.id} temp must be dry, chill, freeze, or mixed")
        if self.pallets < 1:
            raise ValueError(f"Truck {self.id} pallets must be at least 1")
        if self.max_weight_kg < 1:
            raise ValueError(f"Truck {self.id} max_weight_kg must be at least 1")
        if self.mast_mm < 1:
            raise ValueError(f"Truck {self.id} mast_mm must be positive")
        if self.cells_per_min < 1:
            raise ValueError(f"Truck {self.id} cells_per_min must be at least 1")


@dataclass(frozen=True)
class Floor:
    id: str
    name: str
    locations: tuple[Location, ...]
    trucks: tuple[Truck, ...]
    handling_min: int
    max_labor_min: int
    shift_end_min: int
    cell_m: int

    def location_map(self) -> dict[str, Location]:
        return {item.id: item for item in self.locations}

    def truck_map(self) -> dict[str, Truck]:
        return {item.id: item for item in self.trucks}

    def bounds(self) -> tuple[int, int, int, int]:
        xs = [item.x for item in self.locations]
        ys = [item.y for item in self.locations]
        return min(xs), min(ys), max(xs), max(ys)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "locations": [item.as_dict() for item in self.locations],
            "trucks": [item.as_dict() for item in self.trucks],
            "handling_min": self.handling_min,
            "max_labor_min": self.max_labor_min,
            "shift_end_min": self.shift_end_min,
            "cell_m": self.cell_m,
        }

    def validate(self) -> None:
        if not self.locations:
            raise ValueError("Floor has no locations")
        if not self.trucks:
            raise ValueError("Floor has no trucks")
        seen_locs: set[str] = set()
        for item in self.locations:
            item.validate()
            if item.id in seen_locs:
                raise ValueError(f"Duplicate location id '{item.id}'")
            seen_locs.add(item.id)
        seen_trucks: set[str] = set()
        for truck in self.trucks:
            truck.validate()
            if truck.id in seen_trucks:
                raise ValueError(f"Duplicate truck id '{truck.id}'")
            seen_trucks.add(truck.id)
            if truck.start not in seen_locs:
                raise ValueError(f"Truck {truck.id} start '{truck.start}' is not on the floor")
        if self.handling_min < 1:
            raise ValueError("Floor handling_min must be at least 1")
        if self.max_labor_min < 1:
            raise ValueError("Floor labor cap must be at least 1 minute")
        if self.shift_end_min < 1:
            raise ValueError("Floor shift_end_min must be at least 1")
        if self.cell_m < 1:
            raise ValueError("Floor cell_m must be at least 1")


def manhattan(a: Location, b: Location) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def travel_min(a: Location, b: Location, cells_per_min: int) -> int:
    """Ceiling of Manhattan cells / truck speed. Already-there is free."""
    dist = manhattan(a, b)
    if dist == 0:
        return 0
    return (dist + cells_per_min - 1) // cells_per_min


def opposite_flow(previous: str | None, kind: str) -> bool:
    if previous is None:
        return False
    return (previous in INBOUND and kind in OUTBOUND) or (previous in OUTBOUND and kind in INBOUND)


def _loc(loc_id: str, kind: str, x: int, y: int, temp: str = "dry", max_height_mm: int = 12000) -> Location:
    return Location(id=loc_id, kind=kind, x=x, y=y, temp=temp, max_height_mm=max_height_mm)


def _aisles(count: int, bays: int, *, x0: int = 0, dx: int = 2, y0: int = 2, temp: str = "dry") -> tuple[Location, ...]:
    return tuple(
        _loc(f"A{aisle}-{bay}", "aisle", x0 + (aisle - 1) * dx, y0 + (bay - 1), temp)
        for aisle in range(1, count + 1)
        for bay in range(1, bays + 1)
    )


def _truck(
    truck_id: str,
    kind: str,
    start: str,
    *,
    temp: str = "mixed",
    pallets: int | None = None,
    max_weight_kg: int | None = None,
    mast_mm: int | None = None,
    cells_per_min: int | None = None,
) -> Truck:
    return Truck(
        id=truck_id,
        kind=kind,
        start=start,
        temp=temp,
        pallets=KIND_PALLETS[kind] if pallets is None else pallets,
        max_weight_kg=KIND_WEIGHT_KG[kind] if max_weight_kg is None else max_weight_kg,
        mast_mm=KIND_MAST_MM[kind] if mast_mm is None else mast_mm,
        cells_per_min=KIND_CELLS_PER_MIN[kind] if cells_per_min is None else cells_per_min,
    )


def _grocery_locations() -> tuple[Location, ...]:
    return (
        _loc("D1", "dock", 0, 0),
        _loc("D2", "dock", 3, 0),
        _loc("D3", "dock", 6, 0),
        _loc("S1", "staging", 9, 0),
        _loc("S2", "staging", 12, 0),
        *_aisles(6, 6),
        _loc("R1", "reserve", 2, 9),
        _loc("R2", "reserve", 8, 9),
    )


def _produce_locations() -> tuple[Location, ...]:
    chill = _aisles(3, 5, x0=0, y0=2, temp="chill")
    # Freeze aisles are numbered A4–A6 so they do not collide with chill A1–A3.
    freeze = tuple(
        Location(id=f"A{aisle}-{bay}", kind="aisle", x=8 + (aisle - 4) * 2, y=1 + bay, temp="freeze", max_height_mm=12000)
        for aisle in range(4, 7)
        for bay in range(1, 6)
    )
    return (
        _loc("C1", "dock", 0, 0, "chill"),
        _loc("C2", "dock", 3, 0, "chill"),
        _loc("F3", "dock", 10, 0, "freeze"),
        _loc("S1", "staging", 6, 0, "chill"),
        _loc("S2", "staging", 13, 0, "freeze"),
        *chill,
        *freeze,
        _loc("R1", "reserve", 2, 8, "chill"),
        _loc("R2", "reserve", 10, 8, "freeze"),
    )


def _dc_locations() -> tuple[Location, ...]:
    return (
        _loc("D11", "dock", 0, 0),
        _loc("D12", "dock", 3, 0),
        _loc("D13", "dock", 6, 0),
        _loc("D14", "dock", 9, 0),
        _loc("S11", "staging", 12, 0),
        _loc("S12", "staging", 15, 0),
        *_aisles(8, 6, x0=0, dx=2, y0=2),
        _loc("R11", "reserve", 3, 9),
        _loc("R12", "reserve", 9, 9),
        _loc("R13", "reserve", 15, 9),
    )


def _parcel_locations() -> tuple[Location, ...]:
    return (
        _loc("P1", "dock", 0, 0, "mixed"),
        _loc("P2", "dock", 3, 0, "mixed"),
        _loc("T1", "staging", 6, 0, "mixed"),
        _loc("T2", "staging", 9, 0, "mixed"),
        _loc("A1-1", "aisle", 0, 3, "mixed", 1800),
        _loc("A1-2", "aisle", 3, 3, "mixed", 1800),
    )


FLOORS: dict[str, Floor] = {
    "grocery": Floor(
        id="grocery",
        name="6-aisle grocery DC",
        locations=_grocery_locations(),
        trucks=(
            _truck("RT-1", "reach", "D1"),
            _truck("RT-2", "reach", "D2"),
            _truck("SD-1", "sitdown", "D3", temp="dry"),
        ),
        handling_min=2,
        max_labor_min=240,
        shift_end_min=480,
        cell_m=4,
    ),
    "produce": Floor(
        id="produce",
        name="6-aisle produce cold chain",
        locations=_produce_locations(),
        trucks=(
            _truck("RT-C", "reach", "C1", temp="chill"),
            _truck("RT-F", "reach", "F3", temp="freeze"),
        ),
        handling_min=3,
        max_labor_min=160,
        shift_end_min=360,
        cell_m=4,
    ),
    "dc": Floor(
        id="dc",
        name="8-aisle store DC",
        locations=_dc_locations(),
        trucks=(
            _truck("RT-11", "reach", "D11"),
            _truck("RT-12", "reach", "D12"),
            _truck("RT-13", "reach", "D13"),
            _truck("SD-11", "sitdown", "D14", temp="dry"),
            _truck("SD-12", "sitdown", "S11", temp="dry"),
        ),
        handling_min=2,
        max_labor_min=360,
        shift_end_min=600,
        cell_m=4,
    ),
    "parcel": Floor(
        id="parcel",
        name="4-door parcel inbound",
        locations=_parcel_locations(),
        trucks=(
            _truck("JK-1", "jack", "P1"),
            _truck("JK-2", "jack", "P2"),
        ),
        handling_min=1,
        max_labor_min=80,
        shift_end_min=240,
        cell_m=3,
    ),
}


def _as_location(raw: dict, fallback: Location | None = None) -> Location:
    def pick(key: str, default):
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
        return default

    location = Location(
        id=str(pick("id", fallback.id if fallback else "")).strip(),
        kind=str(pick("kind", fallback.kind if fallback else "aisle")),
        x=int(pick("x", fallback.x if fallback else 0)),
        y=int(pick("y", fallback.y if fallback else 0)),
        temp=str(pick("temp", fallback.temp if fallback else "dry")),
        max_height_mm=int(pick("max_height_mm", fallback.max_height_mm if fallback else 12000)),
    )
    location.validate()
    return location


def _as_truck(raw: dict, fallback: Truck | None = None) -> Truck:
    kind = str(raw.get("kind") or (fallback.kind if fallback else "reach")).strip() or "reach"
    if kind not in EQUIPMENT:
        raise ValueError(f"Truck kind must be {', '.join(EQUIPMENT)}")
    def pick(key: str, default):
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
        return default

    truck = Truck(
        id=str(pick("id", fallback.id if fallback else "")).strip(),
        kind=kind,
        start=str(pick("start", fallback.start if fallback else "")).strip(),
        temp=str(pick("temp", fallback.temp if fallback else "mixed")),
        pallets=int(pick("pallets", fallback.pallets if fallback else KIND_PALLETS[kind])),
        max_weight_kg=int(pick("max_weight_kg", fallback.max_weight_kg if fallback else KIND_WEIGHT_KG[kind])),
        mast_mm=int(pick("mast_mm", fallback.mast_mm if fallback else KIND_MAST_MM[kind])),
        cells_per_min=int(pick("cells_per_min", fallback.cells_per_min if fallback else KIND_CELLS_PER_MIN[kind])),
    )
    truck.validate()
    return truck


def get_floor(payload: dict) -> Floor:
    rate_fields = ("handling_min", "max_labor_min", "shift_end_min", "cell_m")
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
        if payload.get("locations"):
            locations = tuple(_as_location(raw) for raw in payload["locations"])
        else:
            locations = preset.locations
        if payload.get("trucks"):
            trucks = tuple(_as_truck(raw) for raw in payload["trucks"])
        else:
            trucks = preset.trucks
        floor = Floor(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            locations=locations,
            trucks=trucks,
            handling_min=int(values["handling_min"]),
            max_labor_min=int(values["max_labor_min"]),
            shift_end_min=int(values["shift_end_min"]),
            cell_m=int(values["cell_m"]),
        )
        floor.validate()
        return floor
    raw_locations = payload.get("locations") or []
    raw_trucks = payload.get("trucks") or []
    if not raw_locations:
        raise ValueError("Custom floor missing: locations")
    if not raw_trucks:
        raise ValueError("Custom floor missing: trucks")
    floor = Floor(
        id="custom",
        name=str(payload.get("name") or "Custom warehouse floor"),
        locations=tuple(_as_location(raw) for raw in raw_locations),
        trucks=tuple(_as_truck(raw) for raw in raw_trucks),
        handling_min=int(payload.get("handling_min", 2)),
        max_labor_min=int(payload.get("max_labor_min", 240)),
        shift_end_min=int(payload.get("shift_end_min", 480)),
        cell_m=int(payload.get("cell_m", 4)),
    )
    floor.validate()
    return floor
