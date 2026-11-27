"""Greedy empty-tote milk runs: overflow first, one type per trip.

Carts start at induction and run in parallel. Each trip seeds on the most
urgent due (or overflowing) pile, then nearest-neighbour fills the cart
with the same tote type — including below-threshold neighbours. A trip
that cannot return before shift end is skipped. Residual below the
station threshold, on a station still under cap, is not a failed run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import Cart, Floor, Home, Station
from .totes import TOTES, nest_per_stack


@dataclass(frozen=True)
class Stop:
    station: str
    tote: str
    totes: int
    stacks: int
    arrive_sec: int
    leave_sec: int
    x_m: float
    y_m: float

    def as_dict(self) -> dict[str, object]:
        return {
            "station": self.station,
            "tote": self.tote,
            "totes": self.totes,
            "stacks": self.stacks,
            "arrive_sec": self.arrive_sec,
            "leave_sec": self.leave_sec,
            "x_m": self.x_m,
            "y_m": self.y_m,
        }


@dataclass(frozen=True)
class Trip:
    cart: str
    tote: str
    home: str
    start_sec: int
    finish_sec: int
    collected: int
    stacks: int
    start_x_m: float
    start_y_m: float
    home_x_m: float
    home_y_m: float
    stops: tuple[Stop, ...]

    def as_dict(self) -> dict[str, object]:
        meta = TOTES.get(self.tote, {})
        return {
            "cart": self.cart,
            "tote": self.tote,
            "tote_name": meta.get("name", self.tote),
            "home": self.home,
            "start_sec": self.start_sec,
            "finish_sec": self.finish_sec,
            "collected": self.collected,
            "stacks": self.stacks,
            "start_x_m": self.start_x_m,
            "start_y_m": self.start_y_m,
            "home_x_m": self.home_x_m,
            "home_y_m": self.home_y_m,
            "stops": [stop.as_dict() for stop in self.stops],
        }


@dataclass
class PlanResult:
    floor: Floor
    trips: list[Trip]
    leftover: list[dict[str, object]]
    residual: list[dict[str, object]]
    makespan_sec: int

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def collected(self) -> int:
        return sum(trip.collected for trip in self.trips)

    @property
    def overflow_stations(self) -> list[str]:
        remaining = _station_remaining(self)
        return [
            station.id
            for station in self.floor.stations
            if remaining.get(station.id, 0) > station.cap
        ]

    def as_dict(self) -> dict[str, object]:
        remaining = _remaining_after(self)
        stations = []
        for station in self.floor.stations:
            piles = []
            total = 0
            totes = {pile.tote for pile in station.piles}
            totes |= {tote for (sid, tote) in remaining if sid == station.id}
            for tote in sorted(totes):
                count = remaining.get((station.id, tote), 0)
                total += count
                if count:
                    piles.append({"tote": tote, "count": count})
            stations.append(
                {
                    **station.as_dict(),
                    "remaining": total,
                    "remaining_piles": piles,
                    "over_cap": total > station.cap,
                    "due": any(
                        count >= station.threshold
                        for (_sid, tote), count in remaining.items()
                        if _sid == station.id
                    ),
                }
            )
        return {
            "all_fit": self.all_fit,
            "trip_count": len(self.trips),
            "collected": self.collected,
            "leftover_count": len(self.leftover),
            "residual_count": len(self.residual),
            "makespan_sec": self.makespan_sec,
            "overflow_stations": self.overflow_stations,
            "homes": [home.as_dict() for home in self.floor.homes],
            "carts": [cart.as_dict() for cart in self.floor.carts],
            "stations": stations,
            "trips": [trip.as_dict() for trip in self.trips],
            "leftover": self.leftover,
            "residual": self.residual,
        }


def plan(floor: Floor) -> PlanResult:
    floor.validate()
    remaining = _initial_remaining(floor)
    start = floor.start_home()
    clocks = {cart.id: 0 for cart in floor.carts}
    positions = {cart.id: start.pos for cart in floor.carts}
    trips: list[Trip] = []
    done: set[str] = set()

    while len(done) < len(floor.carts):
        ready = [cart for cart in floor.carts if cart.id not in done]
        cart = min(ready, key=lambda item: (clocks[item.id], item.id))
        trip = _next_trip(cart, clocks[cart.id], positions[cart.id], remaining, floor)
        if trip is None:
            done.add(cart.id)
            continue
        _apply_trip(remaining, trip)
        trips.append(trip)
        clocks[cart.id] = trip.finish_sec
        positions[cart.id] = (trip.home_x_m, trip.home_y_m)

    leftover, residual = _classify(floor, remaining)
    makespan = max((trip.finish_sec for trip in trips), default=0)
    trips.sort(key=lambda item: (item.start_sec, item.cart, item.tote))
    return PlanResult(
        floor=floor,
        trips=trips,
        leftover=leftover,
        residual=residual,
        makespan_sec=makespan,
    )


def manhattan(a: tuple[float, float], b: tuple[float, float]) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def travel_sec(a: tuple[float, float], b: tuple[float, float], speed_m_per_min: float) -> int:
    metres = manhattan(a, b)
    if metres == 0:
        return 0
    return math.ceil(metres * 60 / speed_m_per_min)


def stacks_for(totes: int, nest: int) -> int:
    if totes <= 0:
        return 0
    return math.ceil(totes / nest)


def take_load(available: int, stack_room: int, nest: int) -> tuple[int, int]:
    if available <= 0 or stack_room <= 0:
        return 0, 0
    take = min(available, stack_room * nest)
    return take, stacks_for(take, nest)


def _initial_remaining(floor: Floor) -> dict[tuple[str, str], int]:
    remaining: dict[tuple[str, str], int] = {}
    for station in floor.stations:
        for pile in station.piles:
            remaining[(station.id, pile.tote)] = pile.count
    return remaining


def _apply_trip(remaining: dict[tuple[str, str], int], trip: Trip) -> None:
    for stop in trip.stops:
        key = (stop.station, stop.tote)
        remaining[key] = remaining.get(key, 0) - stop.totes


def _station_totals(floor: Floor, remaining: dict[tuple[str, str], int]) -> dict[str, int]:
    totals = {station.id: 0 for station in floor.stations}
    for (station_id, _tote), count in remaining.items():
        totals[station_id] = totals.get(station_id, 0) + count
    return totals


def _is_seed(
    station: Station,
    count: int,
    station_total: int,
) -> bool:
    return count >= station.threshold or station_total > station.cap


def _seed_key(
    station: Station,
    tote: str,
    count: int,
    station_total: int,
) -> tuple[float, int, str, str]:
    over_cap = 1 if station_total > station.cap else 0
    due = 1 if count >= station.threshold else 0
    ratio = count / station.threshold
    stale = station.minutes_since_pickup / 30.0
    score = over_cap * 1000 + due * 100 + ratio * 10 + stale
    return (-score, -count, station.id, tote)


def _pick_seed(
    floor: Floor,
    remaining: dict[tuple[str, str], int],
    skip: set[tuple[str, str]],
) -> tuple[str, str] | None:
    totals = _station_totals(floor, remaining)
    best: tuple[tuple[float, int, str, str], str, str] | None = None
    for (station_id, tote), count in remaining.items():
        if count <= 0 or (station_id, tote) in skip:
            continue
        station = floor.station(station_id)
        total = totals[station_id]
        if not _is_seed(station, count, total):
            continue
        key = _seed_key(station, tote, count, total)
        if best is None or key < best[0]:
            best = (key, station_id, tote)
    if best is None:
        return None
    return best[1], best[2]


def _homes_for(floor: Floor, tote: str) -> list[Home]:
    return [home for home in floor.homes if tote in home.accepts]


def _nearest_home(pos: tuple[float, float], homes: list[Home]) -> Home:
    return min(homes, key=lambda home: (manhattan(pos, home.pos), home.id))


def _next_trip(
    cart: Cart,
    clock: int,
    pos: tuple[float, float],
    remaining: dict[tuple[str, str], int],
    floor: Floor,
) -> Trip | None:
    skip: set[tuple[str, str]] = set()
    while True:
        seed = _pick_seed(floor, remaining, skip)
        if seed is None:
            return None
        station_id, tote = seed
        homes = _homes_for(floor, tote)
        if not homes:
            skip.add(seed)
            continue
        trip = _build_trip(cart, clock, pos, station_id, tote, remaining, homes, floor)
        if trip is None:
            skip.add(seed)
            continue
        return trip


def _build_trip(
    cart: Cart,
    clock: int,
    pos: tuple[float, float],
    seed_id: str,
    tote: str,
    remaining: dict[tuple[str, str], int],
    homes: list[Home],
    floor: Floor,
) -> Trip | None:
    nest = nest_per_stack(tote)
    seed = floor.station(seed_id)
    first = _try_stop(
        cart, clock, pos, seed, tote, remaining.get((seed_id, tote), 0), cart.stack_cap, nest, homes
    )
    if first is None:
        return None

    take, stacks, arrive, leave, home = first
    stops = [
        Stop(
            station=seed.id,
            tote=tote,
            totes=take,
            stacks=stacks,
            arrive_sec=arrive,
            leave_sec=leave,
            x_m=seed.x_m,
            y_m=seed.y_m,
        )
    ]
    used = stacks
    clock_now = leave
    cur = seed.pos
    tentative = dict(remaining)
    tentative[(seed_id, tote)] = remaining.get((seed_id, tote), 0) - take

    candidates = [
        station
        for station in floor.stations
        if station.id != seed_id and tentative.get((station.id, tote), 0) > 0
    ]
    while used < cart.stack_cap and candidates:
        nxt = min(candidates, key=lambda item: (manhattan(cur, item.pos), item.id))
        candidates.remove(nxt)
        available = tentative.get((nxt.id, tote), 0)
        choice = _try_stop(
            cart, clock_now, cur, nxt, tote, available, cart.stack_cap - used, nest, homes
        )
        if choice is None:
            continue
        take, stacks, arrive, leave, home = choice
        stops.append(
            Stop(
                station=nxt.id,
                tote=tote,
                totes=take,
                stacks=stacks,
                arrive_sec=arrive,
                leave_sec=leave,
                x_m=nxt.x_m,
                y_m=nxt.y_m,
            )
        )
        used += stacks
        clock_now = leave
        cur = nxt.pos
        tentative[(nxt.id, tote)] = available - take

    last = stops[-1]
    last_pos = (last.x_m, last.y_m)
    home = _nearest_home(last_pos, homes)
    return_sec = travel_sec(last_pos, home.pos, cart.speed_m_per_min)
    drop_sec = used * home.drop_sec_per_stack
    finish = last.leave_sec + return_sec + drop_sec
    return Trip(
        cart=cart.id,
        tote=tote,
        home=home.id,
        start_sec=clock,
        finish_sec=finish,
        collected=sum(stop.totes for stop in stops),
        stacks=used,
        start_x_m=pos[0],
        start_y_m=pos[1],
        home_x_m=home.x_m,
        home_y_m=home.y_m,
        stops=tuple(stops),
    )


def _try_stop(
    cart: Cart,
    clock: int,
    pos: tuple[float, float],
    station: Station,
    tote: str,
    available: int,
    stack_room: int,
    nest: int,
    homes: list[Home],
) -> tuple[int, int, int, int, Home] | None:
    take, stacks = take_load(available, stack_room, nest)
    if take <= 0:
        return None
    travel = travel_sec(pos, station.pos, cart.speed_m_per_min)
    arrive = clock + travel
    leave = arrive + stacks * cart.load_sec_per_stack
    home = _nearest_home(station.pos, homes)
    return_sec = travel_sec(station.pos, home.pos, cart.speed_m_per_min)
    already = cart.stack_cap - stack_room
    drop_sec = (already + stacks) * home.drop_sec_per_stack
    finish = leave + return_sec + drop_sec
    if finish > cart.shift_sec:
        return None
    return take, stacks, arrive, leave, home


def _classify(
    floor: Floor,
    remaining: dict[tuple[str, str], int],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    totals = _station_totals(floor, remaining)
    leftover: list[dict[str, object]] = []
    residual: list[dict[str, object]] = []
    for station in floor.stations:
        for tote in sorted({pile.tote for pile in station.piles}):
            count = remaining.get((station.id, tote), 0)
            if count <= 0:
                continue
            row = {
                "station": station.id,
                "tote": tote,
                "tote_name": TOTES[tote]["name"] if tote in TOTES else tote,
                "remaining": count,
                "threshold": station.threshold,
                "station_total": totals[station.id],
                "cap": station.cap,
            }
            if _is_seed(station, count, totals[station.id]):
                homes = _homes_for(floor, tote)
                if not homes:
                    row["reason"] = f"no home that accepts '{tote}'"
                elif totals[station.id] > station.cap:
                    row["reason"] = "station still over cap"
                else:
                    row["reason"] = "no cart free before shift end"
                leftover.append(row)
            else:
                row["reason"] = "below pickup threshold"
                residual.append(row)
    return leftover, residual


def _remaining_after(result: PlanResult) -> dict[tuple[str, str], int]:
    remaining = _initial_remaining(result.floor)
    for trip in result.trips:
        _apply_trip(remaining, trip)
    return remaining


def _station_remaining(result: PlanResult) -> dict[str, int]:
    remaining = _remaining_after(result)
    return _station_totals(result.floor, remaining)
