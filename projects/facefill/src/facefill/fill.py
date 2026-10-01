"""Greedy pick-face replenishment planner."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Face, FillPlan, Reserve
from .warehouses import Warehouse


@dataclass
class Pull:
    reserve_id: str
    aisle: int
    cases: int

    def as_dict(self) -> dict[str, object]:
        return {"reserve_id": self.reserve_id, "aisle": self.aisle, "cases": self.cases}


@dataclass
class Task:
    face: Face
    cases: int
    units: int
    demand: int
    after_qty: int
    projected_after: int
    trigger: str
    labor_min: int
    pulls: list[Pull] = field(default_factory=list)

    @property
    def fill_before(self) -> float:
        if self.face.max_qty <= 0:
            return 0.0
        return self.face.on_hand / self.face.max_qty

    @property
    def fill_after(self) -> float:
        if self.face.max_qty <= 0:
            return 0.0
        return self.after_qty / self.face.max_qty

    def as_dict(self) -> dict[str, object]:
        return {
            "face_id": self.face.id,
            "sku": self.face.sku,
            "aisle": self.face.aisle,
            "bay": self.face.bay,
            "cases": self.cases,
            "units": self.units,
            "demand": self.demand,
            "on_hand": self.face.on_hand,
            "after_qty": self.after_qty,
            "projected_after": self.projected_after,
            "min_qty": self.face.min_qty,
            "max_qty": self.face.max_qty,
            "fill_before": self.fill_before,
            "fill_after": self.fill_after,
            "trigger": self.trigger,
            "labor_min": self.labor_min,
            "pulls": [pull.as_dict() for pull in self.pulls],
        }


@dataclass
class FaceState:
    face: Face
    demand: int
    projected: int
    after_qty: int
    projected_after: int
    status: str
    task: Task | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "face": self.face.as_dict(),
            "demand": self.demand,
            "projected": self.projected,
            "after_qty": self.after_qty,
            "projected_after": self.projected_after,
            "status": self.status,
            "fill_now": self.face.on_hand / self.face.max_qty if self.face.max_qty else 0.0,
            "fill_after": self.after_qty / self.face.max_qty if self.face.max_qty else 0.0,
        }


@dataclass
class FillResult:
    warehouse: Warehouse
    strategy: str
    tasks: list[Task]
    leftover: list[dict[str, str]]
    faces: list[FaceState]
    labor_min: int

    @property
    def all_filled(self) -> bool:
        return not self.leftover

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def case_count(self) -> int:
        return sum(task.cases for task in self.tasks)

    @property
    def healthy_after(self) -> int:
        return sum(1 for state in self.faces if state.projected_after >= state.face.min_qty)

    @property
    def labor_fill(self) -> float:
        if self.warehouse.max_labor_min <= 0:
            return 0.0
        return self.labor_min / self.warehouse.max_labor_min

    def as_dict(self) -> dict[str, object]:
        return {
            "warehouse": self.warehouse.as_dict(),
            "strategy": self.strategy,
            "all_filled": self.all_filled,
            "task_count": self.task_count,
            "leftover_count": self.leftover_count,
            "case_count": self.case_count,
            "labor_min": self.labor_min,
            "labor_fill": self.labor_fill,
            "healthy_after": self.healthy_after,
            "face_count": len(self.faces),
            "tasks": [task.as_dict() for task in self.tasks],
            "leftover": list(self.leftover),
            "faces": [state.as_dict() for state in self.faces],
        }


def _fill_pct(face: Face) -> float:
    if face.max_qty <= 0:
        return 0.0
    return face.on_hand / face.max_qty


def _sort_faces(faces: list[Face], demand: dict[str, int], strategy: str) -> list[Face]:
    if strategy == "urgent":
        key = lambda face: (
            0 if face.on_hand < face.min_qty else 1,
            _fill_pct(face),
            face.priority,
            face.aisle,
            face.bay,
            face.id,
        )
    elif strategy == "demand":
        key = lambda face: (
            face.priority,
            -(demand.get(face.sku, 0)),
            _fill_pct(face),
            face.id,
        )
    elif strategy == "cluster":
        key = lambda face: (face.aisle, face.bay, face.id)
    else:
        key = lambda face: (
            0 if face.on_hand < face.min_qty else 1,
            face.aisle,
            face.bay,
            face.priority,
            face.id,
        )
    return sorted(faces, key=key)


def _trigger(face: Face, demand_units: int) -> str | None:
    projected = face.on_hand - demand_units
    if face.on_hand < face.min_qty:
        return "already below min"
    if projected < face.min_qty:
        return "wave will breach min"
    return None


def _cases_to_max(face: Face) -> int:
    room = face.max_qty - face.on_hand
    if room < face.case_qty:
        return 0
    return room // face.case_qty


def _labor_cost(warehouse: Warehouse, aisle: int, last_aisle: int | None) -> int:
    if last_aisle is None:
        return warehouse.minutes_per_task + warehouse.aisle_change_min * aisle
    return warehouse.minutes_per_task + warehouse.aisle_change_min * abs(aisle - last_aisle)


def _take_reserve(
    buckets: dict[str, list[list[object]]], sku: str, aisle: int, want: int
) -> list[Pull]:
    """Consume up to `want` cases from nearest reserve locations for this sku."""
    if want < 1 or sku not in buckets:
        return []
    locs = buckets[sku]
    locs.sort(key=lambda item: (abs(int(item[1]) - aisle), str(item[0])))
    pulls: list[Pull] = []
    remaining = want
    for item in locs:
        available = int(item[2])
        if available < 1:
            continue
        take = min(available, remaining)
        item[2] = available - take
        pulls.append(Pull(reserve_id=str(item[0]), aisle=int(item[1]), cases=take))
        remaining -= take
        if remaining == 0:
            break
    return pulls


def fill(plan: FillPlan) -> FillResult:
    plan.validate()
    warehouse = plan.warehouse
    leftover: list[dict[str, str]] = []
    tasks: list[Task] = []
    states: dict[str, FaceState] = {}
    last_aisle: int | None = None
    labor_used = 0

    buckets: dict[str, list[list[object]]] = {}
    for loc in plan.reserve:
        buckets.setdefault(loc.sku, []).append([loc.id, loc.aisle, loc.cases])

    for face in plan.faces:
        demand_units = plan.demand_for(face.sku)
        projected = face.on_hand - demand_units
        states[face.id] = FaceState(
            face=face,
            demand=demand_units,
            projected=projected,
            after_qty=face.on_hand,
            projected_after=projected,
            status="healthy" if projected >= face.min_qty else "at-risk",
        )

    for face in _sort_faces(plan.faces, plan.demand, plan.strategy):
        state = states[face.id]
        if not warehouse.in_layout(face.aisle, face.bay):
            leftover.append({"id": face.id, "reason": "outside layout"})
            state.status = "outside"
            continue

        trigger = _trigger(face, state.demand)
        if trigger is None:
            state.status = "healthy"
            continue

        cases_wanted = _cases_to_max(face)
        if cases_wanted < 1:
            leftover.append({"id": face.id, "reason": "case does not fit remaining face room"})
            state.status = "blocked"
            continue

        available = sum(int(item[2]) for item in buckets.get(face.sku, []))
        if available < 1:
            leftover.append({"id": face.id, "reason": "no reserve stock"})
            state.status = "no-reserve"
            continue

        if len(tasks) >= warehouse.max_tasks:
            leftover.append({"id": face.id, "reason": "over task cap"})
            state.status = "capped"
            continue

        cost = _labor_cost(warehouse, face.aisle, last_aisle)
        if labor_used + cost > warehouse.max_labor_min:
            leftover.append({"id": face.id, "reason": "no remaining labor"})
            state.status = "capped"
            continue

        pulls = _take_reserve(buckets, face.sku, face.aisle, cases_wanted)
        taken = sum(pull.cases for pull in pulls)
        if taken < 1:
            leftover.append({"id": face.id, "reason": "no reserve stock"})
            state.status = "no-reserve"
            continue

        units = taken * face.case_qty
        after_qty = face.on_hand + units
        projected_after = after_qty - state.demand
        task = Task(
            face=face,
            cases=taken,
            units=units,
            demand=state.demand,
            after_qty=after_qty,
            projected_after=projected_after,
            trigger=trigger,
            labor_min=cost,
            pulls=pulls,
        )
        tasks.append(task)
        labor_used += cost
        last_aisle = face.aisle
        state.task = task
        state.after_qty = after_qty
        state.projected_after = projected_after
        state.status = "replenished" if projected_after >= face.min_qty else "short"
        if projected_after < face.min_qty:
            leftover.append({"id": face.id, "reason": "reserve short — still below min"})

    leftover.sort(key=lambda item: item["id"])
    tasks.sort(key=lambda item: (item.face.aisle, item.face.bay, item.face.id))
    face_states = sorted(states.values(), key=lambda item: (item.face.aisle, item.face.bay, item.face.id))
    return FillResult(
        warehouse=warehouse,
        strategy=plan.strategy,
        tasks=tasks,
        leftover=leftover,
        faces=face_states,
        labor_min=labor_used,
    )
