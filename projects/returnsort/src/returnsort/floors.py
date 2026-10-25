"""Returns-room layouts.

Lane sizes are working slot counts for a dock planner, not a particular
WMS location master.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


DISPOSITIONS = ("restock", "refurb", "scrap", "rma", "hold")
TEMPS = ("dry", "chill", "freeze")
ZONES = ("pick_face", "reserve", "shop", "cage", "dock", "quarantine")


@dataclass(frozen=True)
class Lane:
    id: str
    name: str
    dispositions: tuple[str, ...]
    temp: str
    slots: int
    zone: str
    door_adjacent: bool
    col: int
    row: int

    def accepts(self, disposition: str, temp: str) -> bool:
        return disposition in self.dispositions and self.temp == temp

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["dispositions"] = list(self.dispositions)
        return data


@dataclass(frozen=True)
class Floor:
    id: str
    name: str
    lanes: tuple[Lane, ...]

    @property
    def slot_count(self) -> int:
        return sum(lane.slots for lane in self.lanes)

    def lane(self, lane_id: str) -> Lane:
        for item in self.lanes:
            if item.id == lane_id:
                return item
        raise KeyError(lane_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "slot_count": self.slot_count,
            "lanes": [lane.as_dict() for lane in self.lanes],
        }


def _lane(
    lane_id: str,
    name: str,
    dispositions: tuple[str, ...],
    temp: str,
    slots: int,
    zone: str,
    col: int,
    row: int,
    door_adjacent: bool = False,
) -> Lane:
    return Lane(
        id=lane_id,
        name=name,
        dispositions=dispositions,
        temp=temp,
        slots=slots,
        zone=zone,
        door_adjacent=door_adjacent,
        col=col,
        row=row,
    )


PRESETS: dict[str, Floor] = {
    "dc_returns": Floor(
        "dc_returns",
        "DC returns room",
        (
            _lane("FACE-A", "Pick-face A", ("restock",), "dry", 8, "pick_face", 0, 0),
            _lane("FACE-B", "Pick-face B", ("restock",), "dry", 8, "pick_face", 1, 0),
            _lane("CHILL-1", "Chill restock", ("restock", "hold"), "chill", 6, "pick_face", 2, 0),
            _lane("RESERVE", "Reserve restock", ("restock",), "dry", 12, "reserve", 0, 1),
            _lane("REFURB", "Refurb bench", ("refurb",), "dry", 8, "shop", 1, 1),
            _lane("SCRAP", "Scrap cage", ("scrap",), "dry", 10, "cage", 2, 1),
            _lane("RMA", "Vendor RMA dock", ("rma",), "dry", 6, "dock", 0, 2, door_adjacent=True),
            _lane("HOLD", "Quality hold", ("hold",), "dry", 6, "quarantine", 1, 2),
        ),
    ),
    "3pl_mixed": Floor(
        "3pl_mixed",
        "3PL multi-client returns",
        (
            _lane("FACE-A", "Client A face", ("restock",), "dry", 10, "pick_face", 0, 0),
            _lane("FACE-B", "Client B face", ("restock",), "dry", 10, "pick_face", 1, 0),
            _lane("CHILL-1", "Chill face", ("restock", "hold"), "chill", 8, "pick_face", 2, 0),
            _lane("FREEZE-1", "Freeze cage", ("restock", "hold"), "freeze", 4, "reserve", 3, 0),
            _lane("RESERVE", "Shared reserve", ("restock",), "dry", 14, "reserve", 0, 1),
            _lane("REFURB", "Refurb cells", ("refurb",), "dry", 10, "shop", 1, 1),
            _lane("SCRAP", "Scrap cage", ("scrap",), "dry", 12, "cage", 2, 1),
            _lane("RMA", "Vendor RMA", ("rma",), "dry", 8, "dock", 0, 2, door_adjacent=True),
            _lane("HOLD", "Quarantine", ("hold",), "dry", 8, "quarantine", 1, 2),
        ),
    ),
    "store_backroom": Floor(
        "store_backroom",
        "Store backroom returns",
        (
            _lane("FACE", "Floor restock", ("restock",), "dry", 6, "pick_face", 0, 0),
            _lane("CHILL", "Cooler", ("restock", "hold"), "chill", 4, "pick_face", 1, 0),
            _lane("REFURB", "Repair table", ("refurb",), "dry", 4, "shop", 0, 1),
            _lane("SCRAP", "Damage bin", ("scrap",), "dry", 6, "cage", 1, 1),
            _lane("HOLD", "Manager hold", ("hold", "rma"), "dry", 4, "quarantine", 0, 2),
        ),
    ),
}


def get_floor(payload: dict) -> Floor:
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"Unknown floor preset '{key}'. Known: {known}")
        preset = PRESETS[key]
        raw_lanes = payload.get("lanes")
        if not raw_lanes:
            return preset
        return Floor(id=preset.id, name=payload.get("name", preset.name), lanes=_parse_lanes(raw_lanes))
    raw_lanes = payload.get("lanes")
    if not raw_lanes:
        raise ValueError("Custom floor needs lanes, or set floor.preset")
    return Floor(
        id=str(payload.get("id") or "custom"),
        name=str(payload.get("name") or "Custom returns floor"),
        lanes=_parse_lanes(raw_lanes),
    )


def _parse_lanes(raw_lanes: list) -> tuple[Lane, ...]:
    lanes: list[Lane] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_lanes):
        lane_id = str(raw.get("id", "")).strip()
        if not lane_id:
            raise ValueError("Each lane needs an id")
        if lane_id in seen:
            raise ValueError(f"Duplicate lane id '{lane_id}'")
        seen.add(lane_id)
        dispositions = tuple(str(item).strip() for item in (raw.get("dispositions") or ()))
        if not dispositions or any(item not in DISPOSITIONS for item in dispositions):
            raise ValueError(f"Lane '{lane_id}' needs dispositions from {DISPOSITIONS}")
        temp = str(raw.get("temp", "dry")).strip()
        if temp not in TEMPS:
            raise ValueError(f"Lane '{lane_id}' temp must be one of {TEMPS}")
        zone = str(raw.get("zone", "reserve")).strip()
        if zone not in ZONES:
            raise ValueError(f"Lane '{lane_id}' zone must be one of {ZONES}")
        slots = int(raw.get("slots", 0))
        if slots < 1:
            raise ValueError(f"Lane '{lane_id}' slots must be at least 1")
        lanes.append(
            Lane(
                id=lane_id,
                name=str(raw.get("name") or lane_id),
                dispositions=dispositions,
                temp=temp,
                slots=slots,
                zone=zone,
                door_adjacent=bool(raw.get("door_adjacent", False)),
                col=int(raw.get("col", index % 4)),
                row=int(raw.get("row", index // 4)),
            )
        )
    return tuple(lanes)
