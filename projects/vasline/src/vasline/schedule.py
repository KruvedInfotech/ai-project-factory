"""Greedy VAS dispatcher: rush / due-date list, earliest-finish bench.

Jobs are sorted rush-first, then earliest due. Each job is placed atomically:
every step must land on a skilled bench and finish inside that bench's shift,
or the whole job is leftover. Steps of one job are serial; benches run in
parallel. A family change on a bench pays that step's setup as soon as the
bench is free.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .model import Bench, Job, Step, Workbook
from .ops import OPS


@dataclass(frozen=True)
class Task:
    job: str
    sku: str
    op: str
    bench: str
    family: str
    units: int
    setup_sec: int
    setup_start_sec: int
    start_sec: int
    finish_sec: int

    def as_dict(self) -> dict[str, object]:
        return {
            "job": self.job,
            "sku": self.sku,
            "op": self.op,
            "op_name": OPS[self.op]["name"] if self.op in OPS else self.op,
            "bench": self.bench,
            "family": self.family,
            "units": self.units,
            "setup_sec": self.setup_sec,
            "setup_start_sec": self.setup_start_sec,
            "start_sec": self.start_sec,
            "finish_sec": self.finish_sec,
            "duration_sec": self.finish_sec - self.start_sec,
        }


@dataclass(frozen=True)
class ScheduledJob:
    job: str
    sku: str
    family: str
    units: int
    priority: int
    due_min: int | None
    finish_sec: int
    tardy: bool
    tardy_sec: int
    benches: list[str]
    steps: list[Task]

    def as_dict(self) -> dict[str, object]:
        return {
            "job": self.job,
            "sku": self.sku,
            "family": self.family,
            "units": self.units,
            "priority": self.priority,
            "due_min": self.due_min,
            "finish_sec": self.finish_sec,
            "tardy": self.tardy,
            "tardy_sec": self.tardy_sec,
            "benches": list(self.benches),
            "steps": [step.as_dict() for step in self.steps],
        }


@dataclass
class PlanResult:
    benches: list[Bench]
    tasks: list[Task]
    scheduled: list[ScheduledJob]
    leftover: list[dict[str, object]]
    makespan_sec: int

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def tardy_count(self) -> int:
        return sum(1 for item in self.scheduled if item.tardy)

    @property
    def busy_sec(self) -> int:
        busy = 0
        for task in self.tasks:
            busy += task.finish_sec - task.start_sec
            busy += task.setup_sec
        return busy

    @property
    def shift_sec(self) -> int:
        return sum(bench.shift_min * 60 for bench in self.benches)

    @property
    def bench_utilization(self) -> float:
        total = self.shift_sec
        return self.busy_sec / total if total else 0.0

    def as_dict(self) -> dict[str, object]:
        lanes = []
        for bench in self.benches:
            lane_tasks = [t for t in self.tasks if t.bench == bench.id]
            lanes.append(
                {
                    **bench.as_dict(),
                    "task_count": len(lane_tasks),
                    "busy_sec": sum(
                        (t.finish_sec - t.start_sec) + t.setup_sec for t in lane_tasks
                    ),
                    "tasks": [t.as_dict() for t in lane_tasks],
                }
            )
        return {
            "all_fit": self.all_fit,
            "scheduled_count": len(self.scheduled),
            "leftover_count": len(self.leftover),
            "tardy_count": self.tardy_count,
            "makespan_sec": self.makespan_sec,
            "busy_sec": self.busy_sec,
            "shift_sec": self.shift_sec,
            "bench_utilization": round(self.bench_utilization, 4),
            "benches": lanes,
            "scheduled": [item.as_dict() for item in self.scheduled],
            "tasks": [task.as_dict() for task in self.tasks],
            "leftover": self.leftover,
        }


@dataclass
class _BenchClock:
    clock: int = 0
    family: str | None = None
    tasks: list[Task] = field(default_factory=list)


def plan(book: Workbook) -> PlanResult:
    book.validate()
    clocks = {bench.id: _BenchClock() for bench in book.benches}
    leftover: list[dict[str, object]] = []
    scheduled: list[ScheduledJob] = []

    for job in sorted(book.jobs, key=lambda item: item.sort_key()):
        placed = _try_job(job, book.benches, clocks)
        if placed is None:
            leftover.append(
                {
                    "job": job.id,
                    "sku": job.sku,
                    "family": job.family,
                    "units": job.units,
                    "priority": job.priority,
                    "due_min": job.due_min,
                    "reason": _leftover_reason(job, book.benches, clocks),
                }
            )
            continue
        tasks, snapshot = placed
        for bench_id, state in snapshot.items():
            clocks[bench_id] = state
        finish = tasks[-1].finish_sec
        due_sec = None if job.due_min is None else job.due_min * 60
        tardy_sec = 0 if due_sec is None else max(0, finish - due_sec)
        benches_used = []
        for task in tasks:
            if task.bench not in benches_used:
                benches_used.append(task.bench)
        scheduled.append(
            ScheduledJob(
                job=job.id,
                sku=job.sku,
                family=job.family,
                units=job.units,
                priority=job.priority,
                due_min=job.due_min,
                finish_sec=finish,
                tardy=tardy_sec > 0,
                tardy_sec=tardy_sec,
                benches=benches_used,
                steps=tasks,
            )
        )

    tasks = [task for state in clocks.values() for task in state.tasks]
    tasks.sort(key=lambda item: (item.start_sec, item.bench, item.job))
    makespan = max((task.finish_sec for task in tasks), default=0)
    return PlanResult(
        benches=list(book.benches),
        tasks=tasks,
        scheduled=scheduled,
        leftover=leftover,
        makespan_sec=makespan,
    )


def _try_job(
    job: Job,
    benches: list[Bench],
    clocks: dict[str, _BenchClock],
) -> tuple[list[Task], dict[str, _BenchClock]] | None:
    working = {
        bench_id: _BenchClock(clock=state.clock, family=state.family, tasks=list(state.tasks))
        for bench_id, state in clocks.items()
    }
    job_ready = 0
    placed: list[Task] = []
    for step in job.steps:
        choice = _pick_bench(step, job, job_ready, benches, working)
        if choice is None:
            return None
        bench, task = choice
        state = working[bench.id]
        state.clock = task.finish_sec
        state.family = job.family
        state.tasks.append(task)
        placed.append(task)
        job_ready = task.finish_sec
    return placed, working


def _pick_bench(
    step: Step,
    job: Job,
    job_ready: int,
    benches: list[Bench],
    clocks: dict[str, _BenchClock],
) -> tuple[Bench, Task] | None:
    best: tuple[int, str, Bench, Task] | None = None
    duration = math.ceil(step.seconds_per_unit * job.units)
    for bench in benches:
        if step.op not in bench.skills:
            continue
        state = clocks[bench.id]
        setup = step.setup_seconds if state.family not in (None, job.family) else 0
        setup_start = state.clock
        start = max(state.clock + setup, job_ready)
        finish = start + duration
        if finish > bench.shift_min * 60:
            continue
        task = Task(
            job=job.id,
            sku=job.sku,
            op=step.op,
            bench=bench.id,
            family=job.family,
            units=job.units,
            setup_sec=setup,
            setup_start_sec=setup_start if setup else start,
            start_sec=start,
            finish_sec=finish,
        )
        key = (finish, bench.id, bench, task)
        if best is None or key[:2] < best[:2]:
            best = key
    if best is None:
        return None
    return best[2], best[3]


def _leftover_reason(
    job: Job,
    benches: list[Bench],
    clocks: dict[str, _BenchClock],
) -> str:
    skilled = {op for bench in benches for op in bench.skills}
    for step in job.steps:
        if step.op not in skilled:
            return f"no bench with skill '{step.op}'"
    # Walk as far as we can so the reason names the step that overflowed.
    working = {
        bench_id: _BenchClock(clock=state.clock, family=state.family)
        for bench_id, state in clocks.items()
    }
    job_ready = 0
    for step in job.steps:
        choice = _pick_bench(step, job, job_ready, benches, working)
        if choice is None:
            return f"no bench free before shift end for '{step.op}'"
        bench, task = choice
        state = working[bench.id]
        state.clock = task.finish_sec
        state.family = job.family
        job_ready = task.finish_sec
    return "could not schedule job"
