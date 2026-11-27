"""Floor input types: homes, carts, and stations with empty-tote piles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .totes import HOME_KINDS, STATION_KINDS, TOTES, default_accepts


@dataclass(frozen=True)
class Pile:
    tote: str
    count: int

    def validate(self) -> None:
        if self.tote not in TOTES:
            known = ", ".join(sorted(TOTES))
            raise ValueError(f"Unknown tote type '{self.tote}'. Known: {known}")
        if self.count < 1:
            raise ValueError(f"Pile of '{self.tote}' must have at least 1 tote")

    def as_dict(self) -> dict[str, object]:
        return {"tote": self.tote, "count": self.count}


@dataclass(frozen=True)
class Home:
    id: str
    name: str
    kind: str
    x_m: float
    y_m: float
    accepts: tuple[str, ...]
    drop_sec_per_stack: int

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each home needs an id")
        if self.kind not in HOME_KINDS:
            known = ", ".join(sorted(HOME_KINDS))
            raise ValueError(f"Home '{self.id}' has unknown kind '{self.kind}'. Known: {known}")
        if not self.accepts:
            raise ValueError(f"Home '{self.id}' accepts no tote types")
        for tote in self.accepts:
            if tote not in TOTES:
                known = ", ".join(sorted(TOTES))
                raise ValueError(f"Home '{self.id}' accepts unknown tote '{tote}'. Known: {known}")
        if self.drop_sec_per_stack < 0:
            raise ValueError(f"Home '{self.id}' drop time cannot be negative")

    @property
    def pos(self) -> tuple[float, float]:
        return (self.x_m, self.y_m)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "accepts": list(self.accepts),
            "drop_sec_per_stack": self.drop_sec_per_stack,
        }


@dataclass(frozen=True)
class Cart:
    id: str
    name: str
    stack_cap: int
    speed_m_per_min: float
    load_sec_per_stack: int
    shift_min: int

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each cart needs an id")
        if self.stack_cap < 1:
            raise ValueError(f"Cart '{self.id}' stack_cap must be at least 1")
        if self.speed_m_per_min <= 0:
            raise ValueError(f"Cart '{self.id}' speed must be positive")
        if self.load_sec_per_stack < 0:
            raise ValueError(f"Cart '{self.id}' load time cannot be negative")
        if self.shift_min < 1:
            raise ValueError(f"Cart '{self.id}' shift_min must be at least 1")

    @property
    def shift_sec(self) -> int:
        return self.shift_min * 60

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "stack_cap": self.stack_cap,
            "speed_m_per_min": self.speed_m_per_min,
            "load_sec_per_stack": self.load_sec_per_stack,
            "shift_min": self.shift_min,
        }


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    kind: str
    x_m: float
    y_m: float
    threshold: int
    cap: int
    minutes_since_pickup: int
    piles: tuple[Pile, ...]

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each station needs an id")
        if self.kind not in STATION_KINDS:
            known = ", ".join(STATION_KINDS)
            raise ValueError(f"Station '{self.id}' has unknown kind '{self.kind}'. Known: {known}")
        if self.threshold < 1:
            raise ValueError(f"Station '{self.id}' threshold must be at least 1")
        if self.cap < 1:
            raise ValueError(f"Station '{self.id}' cap must be at least 1")
        if self.minutes_since_pickup < 0:
            raise ValueError(f"Station '{self.id}' minutes_since_pickup cannot be negative")
        if not self.piles:
            raise ValueError(f"Station '{self.id}' has no tote piles")
        seen: set[str] = set()
        for pile in self.piles:
            pile.validate()
            if pile.tote in seen:
                raise ValueError(f"Station '{self.id}' has duplicate pile '{pile.tote}'")
            seen.add(pile.tote)

    @property
    def pos(self) -> tuple[float, float]:
        return (self.x_m, self.y_m)

    @property
    def total(self) -> int:
        return sum(pile.count for pile in self.piles)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "threshold": self.threshold,
            "cap": self.cap,
            "minutes_since_pickup": self.minutes_since_pickup,
            "piles": [pile.as_dict() for pile in self.piles],
        }


@dataclass
class Floor:
    homes: list[Home]
    carts: list[Cart]
    stations: list[Station]

    def validate(self) -> None:
        if not self.homes:
            raise ValueError("Floor has no homes")
        if not self.carts:
            raise ValueError("Floor has no carts")
        if not self.stations:
            raise ValueError("Floor has no stations")
        _unique([home.id for home in self.homes], "home")
        _unique([cart.id for cart in self.carts], "cart")
        _unique([station.id for station in self.stations], "station")
        for home in self.homes:
            home.validate()
        for cart in self.carts:
            cart.validate()
        for station in self.stations:
            station.validate()

    def station(self, station_id: str) -> Station:
        for item in self.stations:
            if item.id == station_id:
                return item
        raise KeyError(station_id)

    def home(self, home_id: str) -> Home:
        for item in self.homes:
            if item.id == home_id:
                return item
        raise KeyError(home_id)

    def start_home(self) -> Home:
        induction = [home for home in self.homes if home.kind == "induction"]
        pool = induction or list(self.homes)
        return min(pool, key=lambda item: (item.x_m, item.y_m, item.id))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Floor:
        homes = [_parse_home(raw) for raw in payload.get("homes") or []]
        carts = [_parse_cart(raw) for raw in payload.get("carts") or []]
        stations = [_parse_station(raw) for raw in payload.get("stations") or []]
        floor = cls(homes=homes, carts=carts, stations=stations)
        floor.validate()
        return floor


def _unique(ids: list[str], kind: str) -> None:
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise ValueError(f"Duplicate {kind} id '{item}'")
        seen.add(item)


def _parse_home(raw: dict[str, Any]) -> Home:
    kind = str(raw.get("kind", "")).strip()
    accepts_raw = raw.get("accepts")
    if accepts_raw is None:
        accepts = default_accepts(kind) if kind in HOME_KINDS else []
    else:
        accepts = [str(item).strip() for item in accepts_raw]
    return Home(
        id=str(raw.get("id", "")).strip(),
        name=str(raw.get("name") or raw.get("id") or "").strip(),
        kind=kind,
        x_m=float(raw["x_m"]),
        y_m=float(raw["y_m"]),
        accepts=tuple(accepts),
        drop_sec_per_stack=int(raw.get("drop_sec_per_stack", 10)),
    )


def _parse_cart(raw: dict[str, Any]) -> Cart:
    return Cart(
        id=str(raw.get("id", "")).strip(),
        name=str(raw.get("name") or raw.get("id") or "").strip(),
        stack_cap=int(raw.get("stack_cap", 4)),
        speed_m_per_min=float(raw.get("speed_m_per_min", 60)),
        load_sec_per_stack=int(raw.get("load_sec_per_stack", 10)),
        shift_min=int(raw.get("shift_min", 60)),
    )


def _parse_station(raw: dict[str, Any]) -> Station:
    piles = []
    for pile in raw.get("piles") or []:
        piles.append(
            Pile(
                tote=str(pile.get("tote", "")).strip(),
                count=int(pile["count"]),
            )
        )
    return Station(
        id=str(raw.get("id", "")).strip(),
        name=str(raw.get("name") or raw.get("id") or "").strip(),
        kind=str(raw.get("kind", "")).strip(),
        x_m=float(raw["x_m"]),
        y_m=float(raw["y_m"]),
        threshold=int(raw.get("threshold", 8)),
        cap=int(raw.get("cap", 24)),
        minutes_since_pickup=int(raw.get("minutes_since_pickup", 0)),
        piles=tuple(piles),
    )
