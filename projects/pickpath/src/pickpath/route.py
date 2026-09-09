"""Pick routing: S-shape, return, nearest-neighbor + 2-opt, and auto."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import Pick, Wave
from .warehouse import Point, Warehouse

NAMED_STRATEGIES = ("s_shape", "return", "nearest")


@dataclass
class Stop:
    seq: int
    pick: Pick
    x: float
    y: float

    def as_dict(self) -> dict[str, object]:
        data = self.pick.as_dict()
        data["seq"] = self.seq
        data["x"] = round(self.x, 4)
        data["y"] = round(self.y, 4)
        return data


@dataclass
class RouteResult:
    warehouse: Warehouse
    strategy: str
    chosen_strategy: str
    stops: list[Stop]
    path: list[Point]
    skipped: list[dict[str, object]]
    distance_m: float
    comparison: dict[str, float]

    @property
    def all_routed(self) -> bool:
        return not self.skipped

    @property
    def walk_min(self) -> float:
        speed = self.warehouse.walk_speed_m_per_min
        return self.distance_m / speed if speed else 0.0

    @property
    def pick_min(self) -> float:
        return len(self.stops) * self.warehouse.handling_s / 60.0

    @property
    def total_min(self) -> float:
        return self.walk_min + self.pick_min

    def as_dict(self) -> dict[str, object]:
        return {
            "warehouse": self.warehouse.as_dict(),
            "strategy": self.strategy,
            "chosen_strategy": self.chosen_strategy,
            "stops": [stop.as_dict() for stop in self.stops],
            "path": [pt.as_dict() for pt in self.path],
            "skipped": self.skipped,
            "distance_m": round(self.distance_m, 3),
            "walk_min": round(self.walk_min, 2),
            "pick_min": round(self.pick_min, 2),
            "total_min": round(self.total_min, 2),
            "routed_count": len(self.stops),
            "skipped_count": len(self.skipped),
            "all_routed": self.all_routed,
            "comparison": {key: round(val, 3) for key, val in self.comparison.items()},
        }


def route(wave: Wave) -> RouteResult:
    routable, skipped = wave.split()
    comparison = {name: _distance(wave.warehouse, routable, name) for name in NAMED_STRATEGIES}
    if wave.strategy == "auto":
        chosen = min(NAMED_STRATEGIES, key=lambda name: (comparison[name], NAMED_STRATEGIES.index(name)))
        built = _build(wave.warehouse, routable, chosen)
        return _result(wave, "auto", chosen, built, skipped, comparison)
    built = _build(wave.warehouse, routable, wave.strategy)
    return _result(wave, wave.strategy, wave.strategy, built, skipped, comparison)


def _distance(warehouse: Warehouse, picks: list[Pick], strategy: str) -> float:
    path, _stops = _build(warehouse, picks, strategy)
    return _path_length(path)


def _result(
    wave: Wave,
    strategy: str,
    chosen: str,
    built: tuple[list[Point], list[Stop]],
    skipped: list[dict[str, object]],
    comparison: dict[str, float],
) -> RouteResult:
    path, stops = built
    return RouteResult(
        warehouse=wave.warehouse,
        strategy=strategy,
        chosen_strategy=chosen,
        stops=stops,
        path=path,
        skipped=skipped,
        distance_m=_path_length(path),
        comparison=comparison,
    )


def _build(warehouse: Warehouse, picks: list[Pick], strategy: str) -> tuple[list[Point], list[Stop]]:
    if strategy == "s_shape":
        return _trace(warehouse, _order_s_shape(picks), force_front=False, s_shape_exits=True)
    if strategy == "return":
        return _trace(warehouse, _order_return(picks), force_front=True, s_shape_exits=False)
    if strategy == "nearest":
        return _trace(warehouse, _order_nearest(warehouse, picks), force_front=False, s_shape_exits=False)
    raise ValueError(f"Unknown routing strategy '{strategy}'")


def _order_s_shape(picks: list[Pick]) -> list[Pick]:
    groups = _by_aisle(picks)
    aisles = sorted(groups)
    order: list[Pick] = []
    go_rear = True
    for aisle in aisles:
        members = sorted(groups[aisle], key=lambda p: (p.bay, p.side, p.index))
        order.extend(members if go_rear else list(reversed(members)))
        go_rear = not go_rear
    return order


def _order_return(picks: list[Pick]) -> list[Pick]:
    groups = _by_aisle(picks)
    order: list[Pick] = []
    for aisle in sorted(groups):
        members = sorted(groups[aisle], key=lambda p: (p.bay, p.side, p.index))
        order.extend(members)
    return order


def _order_nearest(warehouse: Warehouse, picks: list[Pick]) -> list[Pick]:
    if len(picks) <= 1:
        return list(picks)
    remaining = list(picks)
    order: list[Pick] = []
    current = warehouse.depot()
    while remaining:
        nxt = min(
            remaining,
            key=lambda p: (
                warehouse.walk_length(current, warehouse.pick_node(p.aisle, p.bay, p.side)),
                p.aisle,
                p.bay,
                p.index,
            ),
        )
        remaining.remove(nxt)
        order.append(nxt)
        current = warehouse.pick_node(nxt.aisle, nxt.bay, nxt.side)
    return _two_opt(warehouse, order)


def _two_opt(warehouse: Warehouse, order: list[Pick]) -> list[Pick]:
    if len(order) < 4:
        return order
    depot = warehouse.depot()
    nodes = [depot] + [warehouse.pick_node(p.aisle, p.bay, p.side) for p in order]
    n = len(order)
    dist = [[0.0] * (n + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(n + 1):
            if i != j:
                dist[i][j] = warehouse.walk_length(nodes[i], nodes[j])

    def tour_len(perm: list[int]) -> float:
        total = dist[0][perm[0] + 1]
        for a, b in zip(perm, perm[1:]):
            total += dist[a + 1][b + 1]
        total += dist[perm[-1] + 1][0]
        return total

    perm = list(range(n))
    improved = True
    while improved:
        improved = False
        best = tour_len(perm)
        for i in range(n - 1):
            for j in range(i + 2, n):
                cand = perm[:i] + list(reversed(perm[i : j + 1])) + perm[j + 1 :]
                length = tour_len(cand)
                if length + 1e-9 < best:
                    perm = cand
                    best = length
                    improved = True
    return [order[i] for i in perm]


def _trace(
    warehouse: Warehouse,
    order: list[Pick],
    force_front: bool,
    s_shape_exits: bool,
) -> tuple[list[Point], list[Stop]]:
    depot = warehouse.depot()
    path: list[Point] = [depot]
    stops: list[Stop] = []
    current = depot
    aisle_seq: list[int] = []
    seen: set[int] = set()
    for pick in order:
        if pick.aisle not in seen:
            aisle_seq.append(pick.aisle)
            seen.add(pick.aisle)

    def extend(target: Point) -> None:
        nonlocal current
        segment = warehouse.waypoints(current, target, force_front=force_front)
        path.extend(segment[1:])
        current = target

    go_rear = True
    idx = 0
    for aisle_i, aisle in enumerate(aisle_seq):
        members = [p for p in order if p.aisle == aisle]
        last = aisle_i == len(aisle_seq) - 1
        for pick in members:
            node = warehouse.pick_node(pick.aisle, pick.bay, pick.side)
            extend(node)
            idx += 1
            stops.append(Stop(seq=idx, pick=pick, x=node.x, y=node.y))
        if s_shape_exits and not last:
            if go_rear:
                extend(warehouse.rear_node(aisle))
            else:
                extend(warehouse.front_node(aisle))
            go_rear = not go_rear
    extend(depot)
    return path, stops


def _by_aisle(picks: list[Pick]) -> dict[int, list[Pick]]:
    groups: dict[int, list[Pick]] = defaultdict(list)
    for pick in picks:
        groups[pick.aisle].append(pick)
    return groups


def _path_length(path: list[Point]) -> float:
    if len(path) < 2:
        return 0.0
    return sum(path[i].manhattan(path[i + 1]) for i in range(len(path) - 1))
