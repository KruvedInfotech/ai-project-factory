"""Workbook input types: benches, jobs, and VAS steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ops import OPS, default_seconds_per_unit, default_setup_seconds, known_ops


@dataclass(frozen=True)
class Bench:
    id: str
    name: str
    skills: tuple[str, ...]
    shift_min: int

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each bench needs an id")
        if self.shift_min <= 0:
            raise ValueError(f"Bench '{self.id}' shift_min must be positive")
        if not self.skills:
            raise ValueError(f"Bench '{self.id}' needs at least one skill")
        unknown = [op for op in self.skills if op not in OPS]
        if unknown:
            raise ValueError(
                f"Bench '{self.id}' unknown skill(s) {', '.join(unknown)}. "
                f"Known: {', '.join(known_ops())}"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "skills": list(self.skills),
            "shift_min": self.shift_min,
            "shift_sec": self.shift_min * 60,
        }


@dataclass(frozen=True)
class Step:
    op: str
    seconds_per_unit: float
    setup_seconds: int

    def validate(self, job_id: str) -> None:
        if self.op not in OPS:
            raise ValueError(
                f"Job '{job_id}' unknown op '{self.op}'. Known: {', '.join(known_ops())}"
            )
        if self.seconds_per_unit <= 0:
            raise ValueError(f"Job '{job_id}' step '{self.op}' seconds_per_unit must be positive")
        if self.setup_seconds < 0:
            raise ValueError(f"Job '{job_id}' step '{self.op}' setup_seconds cannot be negative")


@dataclass(frozen=True)
class Job:
    id: str
    sku: str
    units: int
    due_min: int | None
    priority: int
    family: str
    steps: tuple[Step, ...]

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each job needs an id")
        if not self.sku.strip():
            raise ValueError(f"Job '{self.id}' needs a sku")
        if self.units < 1:
            raise ValueError(f"Job '{self.id}' units must be at least 1")
        if self.priority < 1 or self.priority > 5:
            raise ValueError(f"Job '{self.id}' priority must be 1 (rush) through 5")
        if not self.family.strip():
            raise ValueError(f"Job '{self.id}' needs a family (changeover group)")
        if self.due_min is not None and self.due_min < 0:
            raise ValueError(f"Job '{self.id}' due_min cannot be negative")
        if not self.steps:
            raise ValueError(f"Job '{self.id}' needs at least one step")
        for step in self.steps:
            step.validate(self.id)

    def sort_key(self) -> tuple[int, int, str]:
        due = self.due_min if self.due_min is not None else 10**9
        return (self.priority, due, self.id)


@dataclass
class Workbook:
    benches: list[Bench]
    jobs: list[Job]

    def validate(self) -> None:
        if not self.benches:
            raise ValueError("Workbook has no benches")
        if not self.jobs:
            raise ValueError("Workbook has no jobs")
        seen_benches: set[str] = set()
        for bench in self.benches:
            bench.validate()
            if bench.id in seen_benches:
                raise ValueError(f"Duplicate bench '{bench.id}'")
            seen_benches.add(bench.id)
        seen_jobs: set[str] = set()
        for job in self.jobs:
            job.validate()
            if job.id in seen_jobs:
                raise ValueError(f"Duplicate job '{job.id}'")
            seen_jobs.add(job.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Workbook:
        benches = [_parse_bench(raw) for raw in payload.get("benches") or []]
        jobs = [_parse_job(raw) for raw in payload.get("jobs") or []]
        book = cls(benches=benches, jobs=jobs)
        book.validate()
        return book


def _parse_bench(raw: dict[str, Any]) -> Bench:
    skills = tuple(str(item).strip() for item in (raw.get("skills") or []) if str(item).strip())
    bench_id = str(raw.get("id", "")).strip()
    return Bench(
        id=bench_id,
        name=str(raw.get("name") or bench_id or "Bench"),
        skills=skills,
        shift_min=int(raw.get("shift_min", 480)),
    )


def _parse_job(raw: dict[str, Any]) -> Job:
    job_id = str(raw.get("id", "")).strip()
    steps = tuple(_parse_step(item, job_id) for item in (raw.get("steps") or []))
    due_raw = raw.get("due_min", None)
    return Job(
        id=job_id,
        sku=str(raw.get("sku", "")).strip(),
        units=int(raw.get("units", 1)),
        due_min=None if due_raw is None else int(due_raw),
        priority=int(raw.get("priority", 3)),
        family=str(raw.get("family", "")).strip(),
        steps=steps,
    )


def _parse_step(raw: dict[str, Any], job_id: str) -> Step:
    op = str(raw.get("op", "")).strip()
    if not op:
        raise ValueError(f"Job '{job_id}' has a step with no op")
    seconds = raw.get("seconds_per_unit")
    setup = raw.get("setup_seconds")
    if op in OPS:
        if seconds is None:
            seconds = default_seconds_per_unit(op)
        if setup is None:
            setup = default_setup_seconds(op)
    else:
        # Unknown op is rejected in validate(); keep dummy times so that error wins.
        if seconds is None:
            seconds = 1
        if setup is None:
            setup = 0
    return Step(
        op=op,
        seconds_per_unit=float(seconds),
        setup_seconds=int(setup),
    )
