"""Single-block warehouse geometry and aisle-legal walking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    aisle: int = 1

    def manhattan(self, other: "Point") -> float:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def almost(self, other: "Point", eps: float = 1e-9) -> bool:
        return abs(self.x - other.x) < eps and abs(self.y - other.y) < eps

    def as_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 4), "y": round(self.y, 4), "aisle": self.aisle}


@dataclass(frozen=True)
class Warehouse:
    id: str
    name: str
    aisle_count: int
    bays_per_aisle: int
    bay_length_m: float
    aisle_width_m: float
    aisle_pitch_m: float
    has_rear: bool = True
    walk_speed_m_per_min: float = 75.0
    handling_s: float = 20.0

    @property
    def aisle_length_m(self) -> float:
        return self.bays_per_aisle * self.bay_length_m

    @property
    def rack_depth_m(self) -> float:
        return max(0.0, (self.aisle_pitch_m - self.aisle_width_m) / 2)

    @property
    def floor_width_m(self) -> float:
        last_right = self.center_x(self.aisle_count) + self.aisle_width_m / 2 + self.rack_depth_m
        return last_right - self.left_edge()

    def left_edge(self) -> float:
        return self.center_x(1) - self.aisle_width_m / 2 - self.rack_depth_m

    def center_x(self, aisle: int) -> float:
        return (aisle - 1) * self.aisle_pitch_m

    def face_x(self, aisle: int, side: str) -> float:
        offset = self.aisle_width_m / 2
        return self.center_x(aisle) + (-offset if side.upper() == "L" else offset)

    def bay_y(self, bay: int) -> float:
        return (bay - 0.5) * self.bay_length_m

    def depot(self) -> Point:
        return Point(self.center_x(1), 0.0, aisle=1)

    def front_node(self, aisle: int) -> Point:
        return Point(self.center_x(aisle), 0.0, aisle=aisle)

    def rear_node(self, aisle: int) -> Point:
        return Point(self.center_x(aisle), self.aisle_length_m, aisle=aisle)

    def pick_node(self, aisle: int, bay: int, side: str) -> Point:
        return Point(self.face_x(aisle, side), self.bay_y(bay), aisle=aisle)

    def in_range(self, aisle: int, bay: int) -> bool:
        return 1 <= aisle <= self.aisle_count and 1 <= bay <= self.bays_per_aisle

    def waypoints(self, start: Point, end: Point, force_front: bool = False) -> list[Point]:
        """Aisle-legal path: walk aisle centers and front/rear cross-aisles only."""
        pts = [start]
        acx = self.center_x(start.aisle)
        bcx = self.center_x(end.aisle)

        def add(x: float, y: float, aisle: int) -> None:
            node = Point(x, y, aisle)
            if not pts[-1].almost(node):
                pts.append(node)

        if start.aisle == end.aisle:
            add(acx, start.y, start.aisle)
            add(bcx, end.y, end.aisle)
            add(end.x, end.y, end.aisle)
            return pts

        add(acx, start.y, start.aisle)
        rear = self.aisle_length_m
        via_front = start.y + abs(acx - bcx) + end.y
        via_rear = (rear - start.y) + abs(acx - bcx) + (rear - end.y)
        use_rear = (
            self.has_rear
            and not force_front
            and via_rear + 1e-9 < via_front
        )
        if use_rear:
            add(acx, rear, start.aisle)
            add(bcx, rear, end.aisle)
        else:
            add(acx, 0.0, start.aisle)
            add(bcx, 0.0, end.aisle)
        add(bcx, end.y, end.aisle)
        add(end.x, end.y, end.aisle)
        return pts

    def walk_length(self, start: Point, end: Point, force_front: bool = False) -> float:
        pts = self.waypoints(start, end, force_front=force_front)
        return sum(pts[i].manhattan(pts[i + 1]) for i in range(len(pts) - 1))

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "aisle_count": self.aisle_count,
            "bays_per_aisle": self.bays_per_aisle,
            "bay_length_m": self.bay_length_m,
            "aisle_width_m": self.aisle_width_m,
            "aisle_pitch_m": self.aisle_pitch_m,
            "has_rear": self.has_rear,
            "walk_speed_m_per_min": self.walk_speed_m_per_min,
            "handling_s": self.handling_s,
            "aisle_length_m": round(self.aisle_length_m, 4),
            "rack_depth_m": round(self.rack_depth_m, 4),
            "floor_width_m": round(self.floor_width_m, 4),
            "left_edge": round(self.left_edge(), 4),
        }


PRESETS: dict[str, Warehouse] = {
    "grocery_6x20": Warehouse(
        "grocery_6x20",
        "Grocery 6×20",
        aisle_count=6,
        bays_per_aisle=20,
        bay_length_m=1.0,
        aisle_width_m=2.4,
        aisle_pitch_m=4.0,
        has_rear=True,
        walk_speed_m_per_min=75.0,
        handling_s=20.0,
    ),
    "bulk_8x12": Warehouse(
        "bulk_8x12",
        "Bulk 8×12",
        aisle_count=8,
        bays_per_aisle=12,
        bay_length_m=1.4,
        aisle_width_m=3.2,
        aisle_pitch_m=5.6,
        has_rear=True,
        walk_speed_m_per_min=60.0,
        handling_s=35.0,
    ),
    "mini_4x8": Warehouse(
        "mini_4x8",
        "Mini 4×8",
        aisle_count=4,
        bays_per_aisle=8,
        bay_length_m=1.0,
        aisle_width_m=2.0,
        aisle_pitch_m=3.6,
        has_rear=True,
        walk_speed_m_per_min=75.0,
        handling_s=15.0,
    ),
    "front_only_5x10": Warehouse(
        "front_only_5x10",
        "Front-aisle only 5×10",
        aisle_count=5,
        bays_per_aisle=10,
        bay_length_m=1.2,
        aisle_width_m=2.6,
        aisle_pitch_m=4.4,
        has_rear=False,
        walk_speed_m_per_min=70.0,
        handling_s=18.0,
    ),
}


def get_warehouse(payload: dict) -> Warehouse:
    speed = payload.get("walk_speed_m_per_min")
    handling = payload.get("handling_s")
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"Unknown warehouse preset '{key}'. Known: {known}")
        preset = PRESETS[key]
        fields = (
            "aisle_count",
            "bays_per_aisle",
            "bay_length_m",
            "aisle_width_m",
            "aisle_pitch_m",
            "has_rear",
            "walk_speed_m_per_min",
            "handling_s",
            "name",
        )
        overrides = {field: payload[field] for field in fields if field in payload and payload[field] is not None}
        if not overrides:
            return preset
        return Warehouse(
            id=preset.id,
            name=str(overrides.get("name", preset.name)),
            aisle_count=int(overrides.get("aisle_count", preset.aisle_count)),
            bays_per_aisle=int(overrides.get("bays_per_aisle", preset.bays_per_aisle)),
            bay_length_m=float(overrides.get("bay_length_m", preset.bay_length_m)),
            aisle_width_m=float(overrides.get("aisle_width_m", preset.aisle_width_m)),
            aisle_pitch_m=float(overrides.get("aisle_pitch_m", preset.aisle_pitch_m)),
            has_rear=bool(overrides.get("has_rear", preset.has_rear)),
            walk_speed_m_per_min=float(overrides.get("walk_speed_m_per_min", preset.walk_speed_m_per_min)),
            handling_s=float(overrides.get("handling_s", preset.handling_s)),
        )
    required = ("aisle_count", "bays_per_aisle", "bay_length_m", "aisle_width_m", "aisle_pitch_m")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Custom warehouse missing: {', '.join(missing)}")
    return Warehouse(
        id="custom",
        name=str(payload.get("name") or "Custom warehouse"),
        aisle_count=int(payload["aisle_count"]),
        bays_per_aisle=int(payload["bays_per_aisle"]),
        bay_length_m=float(payload["bay_length_m"]),
        aisle_width_m=float(payload["aisle_width_m"]),
        aisle_pitch_m=float(payload["aisle_pitch_m"]),
        has_rear=bool(payload.get("has_rear", True)),
        walk_speed_m_per_min=float(speed if speed is not None else 75.0),
        handling_s=float(handling if handling is not None else 20.0),
    )
