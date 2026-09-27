"""Yard layouts: doors, hours, and turnaround.

Times are working-day clocks, not a particular WMS yard module. Door kinds
are capability flags (direction + temperature), not OEM dock equipment.
"""

from __future__ import annotations

from dataclasses import dataclass


def parse_hhmm(value: str) -> int:
    text = str(value).strip()
    if text == "24:00":
        return 24 * 60
    try:
        hour_s, minute_s = text.split(":")
        hour = int(hour_s)
        minute = int(minute_s)
    except ValueError as exc:
        raise ValueError(f"Time '{value}' must be HH:MM") from exc
    if hour == 24 and minute == 0:
        return 24 * 60
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time '{value}' is out of range")
    return hour * 60 + minute


def format_hhmm(minutes: int) -> str:
    if minutes >= 24 * 60:
        return "24:00"
    hour, minute = divmod(int(minutes), 60)
    return f"{hour:02d}:{minute:02d}"


DIRECTIONS = ("inbound", "outbound")
TEMPS = ("dry", "reefer")


@dataclass(frozen=True)
class Door:
    id: str
    name: str
    directions: tuple[str, ...]
    temps: tuple[str, ...]
    max_length_m: float

    def accepts(self, direction: str, temp: str, length_m: float) -> bool:
        return (
            direction in self.directions
            and temp in self.temps
            and length_m <= self.max_length_m + 1e-9
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "directions": list(self.directions),
            "temps": list(self.temps),
            "max_length_m": self.max_length_m,
        }


@dataclass(frozen=True)
class Yard:
    id: str
    name: str
    open_min: int
    close_min: int
    turnaround_min: int
    doors: tuple[Door, ...]

    @property
    def span_min(self) -> int:
        return max(0, self.close_min - self.open_min)

    def door(self, door_id: str) -> Door | None:
        for item in self.doors:
            if item.id == door_id:
                return item
        return None

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "open": format_hhmm(self.open_min),
            "close": format_hhmm(self.close_min),
            "turnaround_min": self.turnaround_min,
            "doors": [door.as_dict() for door in self.doors],
        }


def _door(
    door_id: str,
    name: str,
    directions: tuple[str, ...],
    temps: tuple[str, ...],
    max_length_m: float,
) -> Door:
    return Door(door_id, name, directions, temps, max_length_m)


PRESETS: dict[str, Yard] = {
    "fmcg_4": Yard(
        "fmcg_4",
        "FMCG DC · 4 doors",
        parse_hhmm("06:00"),
        parse_hhmm("20:00"),
        15,
        (
            _door("D1", "Door 1 inbound", ("inbound",), ("dry",), 14.0),
            _door("D2", "Door 2 inbound", ("inbound",), ("dry",), 14.0),
            _door("D3", "Door 3 outbound", ("outbound",), ("dry",), 14.0),
            _door("D4", "Door 4 mixed / reefer", ("inbound", "outbound"), ("dry", "reefer"), 13.6),
        ),
    ),
    "cold_3": Yard(
        "cold_3",
        "Cold store · 3 reefer doors",
        parse_hhmm("05:00"),
        parse_hhmm("18:00"),
        20,
        (
            _door("C1", "Cold 1", ("inbound", "outbound"), ("reefer",), 13.6),
            _door("C2", "Cold 2", ("inbound", "outbound"), ("reefer",), 13.6),
            _door("C3", "Cold 3", ("inbound", "outbound"), ("reefer",), 12.0),
        ),
    ),
    "crossdock_8": Yard(
        "crossdock_8",
        "Cross-dock · 8 doors",
        parse_hhmm("00:00"),
        parse_hhmm("24:00"),
        10,
        (
            _door("X1", "Inbound A", ("inbound",), ("dry",), 16.0),
            _door("X2", "Inbound B", ("inbound",), ("dry",), 16.0),
            _door("X3", "Inbound C", ("inbound",), ("dry", "reefer"), 13.6),
            _door("X4", "Outbound A", ("outbound",), ("dry",), 16.0),
            _door("X5", "Outbound B", ("outbound",), ("dry",), 16.0),
            _door("X6", "Outbound C", ("outbound",), ("dry", "reefer"), 13.6),
            _door("X7", "Flex 1", ("inbound", "outbound"), ("dry",), 14.0),
            _door("X8", "Flex 2", ("inbound", "outbound"), ("dry", "reefer"), 13.6),
        ),
    ),
    "mini_2": Yard(
        "mini_2",
        "Mini yard · 2 doors",
        parse_hhmm("08:00"),
        parse_hhmm("16:00"),
        10,
        (
            _door("A", "Door A mixed", ("inbound", "outbound"), ("dry", "reefer"), 14.0),
            _door("B", "Door B dry", ("inbound", "outbound"), ("dry",), 12.0),
        ),
    ),
}


def get_yard(payload: dict) -> Yard:
    if "preset" in payload and payload["preset"]:
        key = str(payload["preset"])
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"Unknown yard preset '{key}'. Known: {known}")
        preset = PRESETS[key]
        turnaround = payload.get("turnaround_min")
        open_s = payload.get("open")
        close_s = payload.get("close")
        if turnaround is None and open_s is None and close_s is None and "doors" not in payload:
            return preset
        doors = _parse_doors(payload["doors"]) if "doors" in payload else preset.doors
        return Yard(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            open_min=parse_hhmm(open_s) if open_s is not None else preset.open_min,
            close_min=parse_hhmm(close_s) if close_s is not None else preset.close_min,
            turnaround_min=int(turnaround) if turnaround is not None else preset.turnaround_min,
            doors=doors,
        )
    required = ("open", "close", "doors")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Custom yard missing: {', '.join(missing)}")
    return Yard(
        id="custom",
        name=str(payload.get("name") or "Custom yard"),
        open_min=parse_hhmm(payload["open"]),
        close_min=parse_hhmm(payload["close"]),
        turnaround_min=int(payload.get("turnaround_min", 15)),
        doors=_parse_doors(payload["doors"]),
    )


def _parse_doors(raw_doors: object) -> tuple[Door, ...]:
    if not isinstance(raw_doors, list) or not raw_doors:
        raise ValueError("Yard needs at least one door")
    doors: list[Door] = []
    seen: set[str] = set()
    for raw in raw_doors:
        if not isinstance(raw, dict):
            raise ValueError("Each door must be an object")
        door_id = str(raw.get("id", "")).strip()
        if not door_id:
            raise ValueError("Each door needs an id")
        if door_id in seen:
            raise ValueError(f"Duplicate door id '{door_id}'")
        seen.add(door_id)
        directions = tuple(str(item).lower() for item in (raw.get("directions") or DIRECTIONS))
        temps = tuple(str(item).lower() for item in (raw.get("temps") or TEMPS))
        for item in directions:
            if item not in DIRECTIONS:
                raise ValueError(f"Door '{door_id}' has unknown direction '{item}'")
        for item in temps:
            if item not in TEMPS:
                raise ValueError(f"Door '{door_id}' has unknown temp '{item}'")
        doors.append(
            Door(
                id=door_id,
                name=str(raw.get("name") or door_id),
                directions=directions,
                temps=temps,
                max_length_m=float(raw.get("max_length_m", 14)),
            )
        )
    return tuple(doors)
