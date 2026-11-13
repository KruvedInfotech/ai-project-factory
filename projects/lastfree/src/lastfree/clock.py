"""Count last free day, then tiered demurrage and detention.

Demurrage is terminal storage. Detention is equipment on the street.
Pickup on last free day is still free. Charge days start the day after LFD.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .model import Job
from .presets import RateTier

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def is_skipped(day: date, day_type: str, holidays: set[date]) -> bool:
    if day_type == "calendar":
        return False
    if day.weekday() >= 5:
        return True
    return day in holidays


def last_free_day(start: date, free_days: int, day_type: str, holidays: set[date]) -> date:
    """Last day that still counts as free. Pickup that day is $0.

    Free time of 0 means LFD is the day before start, so the start date charges.
    """
    if free_days == 0:
        return start - timedelta(days=1)
    counted = 0
    cursor = start
    last = start
    for _ in range(800):
        if not is_skipped(cursor, day_type, holidays):
            counted += 1
            last = cursor
            if counted >= free_days:
                return last
        cursor += timedelta(days=1)
    raise ValueError("Could not finish free-time count (check holidays / free days)")


def charge_days(after: date, through: date, day_type: str, holidays: set[date]) -> list[date]:
    """Days in (after, through] of the configured type."""
    if through <= after:
        return []
    days: list[date] = []
    cursor = after + timedelta(days=1)
    while cursor <= through:
        if not is_skipped(cursor, day_type, holidays):
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def daily_rate(ordinal: int, tiers: tuple[RateTier, ...], factor: float) -> float:
    for tier in tiers:
        hi = tier.to_day if tier.to_day is not None else 10**9
        if tier.from_day <= ordinal <= hi:
            return round(tier.usd * factor, 2)
    raise ValueError(f"No rate tier covers charge day {ordinal}")


def money_for(days: list[date], tiers: tuple[RateTier, ...], factor: float) -> list[tuple[date, float]]:
    billed: list[tuple[date, float]] = []
    for index, day in enumerate(days, start=1):
        billed.append((day, daily_rate(index, tiers, factor)))
    return billed


@dataclass(frozen=True)
class DayCell:
    date: date
    weekday: str
    skipped: bool
    holiday: bool
    flags: tuple[str, ...]
    demurrage_usd: float
    detention_usd: float

    def as_dict(self) -> dict[str, object]:
        return {
            "date": self.date.isoformat(),
            "weekday": self.weekday,
            "skipped": self.skipped,
            "holiday": self.holiday,
            "flags": list(self.flags),
            "demurrage_usd": self.demurrage_usd,
            "detention_usd": self.detention_usd,
        }


@dataclass
class ClockResult:
    job: Job
    demurrage_lfd: date
    detention_lfd: date | None
    demurrage_days: int
    detention_days: int
    demurrage_usd: float
    detention_usd: float
    accrued_demurrage_usd: float
    accrued_detention_usd: float
    status: str
    calendar: list[DayCell]

    @property
    def projected_usd(self) -> float:
        return round(self.demurrage_usd + self.detention_usd, 2)

    @property
    def accrued_usd(self) -> float:
        return round(self.accrued_demurrage_usd + self.accrued_detention_usd, 2)

    @property
    def days_until_lfd(self) -> int | None:
        if self.job.gate_out_on is not None:
            return None
        return (self.demurrage_lfd - self.job.as_of).days

    def as_dict(self) -> dict[str, object]:
        return {
            "container": self.job.container,
            "size": self.job.size,
            "preset": self.job.preset.as_dict(),
            "available_on": self.job.available_on.isoformat(),
            "as_of": self.job.as_of.isoformat(),
            "gate_out_on": self.job.gate_out_on.isoformat() if self.job.gate_out_on else None,
            "empty_return_on": self.job.empty_return_on.isoformat() if self.job.empty_return_on else None,
            "demurrage_lfd": self.demurrage_lfd.isoformat(),
            "detention_lfd": self.detention_lfd.isoformat() if self.detention_lfd else None,
            "demurrage_days": self.demurrage_days,
            "detention_days": self.detention_days,
            "demurrage_usd": self.demurrage_usd,
            "detention_usd": self.detention_usd,
            "projected_usd": self.projected_usd,
            "accrued_demurrage_usd": self.accrued_demurrage_usd,
            "accrued_detention_usd": self.accrued_detention_usd,
            "accrued_usd": self.accrued_usd,
            "days_until_lfd": self.days_until_lfd,
            "status": self.status,
            "calendar": [cell.as_dict() for cell in self.calendar],
        }


def _status(job: Job, demurrage_lfd: date, detention_lfd: date | None) -> str:
    as_of = job.as_of
    if as_of < job.available_on:
        return "not_yet_available"
    if job.empty_return_on is not None and as_of >= job.empty_return_on:
        return "closed"
    if job.gate_out_on is None or as_of < job.gate_out_on:
        if as_of <= demurrage_lfd:
            return "inside_free"
        return "demurrage_running"
    if detention_lfd is not None and as_of <= detention_lfd:
        return "on_street_free"
    return "detention_running"


def _through(event: date | None, as_of: date, fallback: date | None = None) -> date:
    if event is not None:
        return event
    if fallback is not None:
        return fallback
    return as_of


def run_clock(job: Job) -> ClockResult:
    job.validate()
    holidays = job.holiday_set
    factor = job.size_factor()
    preset = job.preset

    demurrage_lfd = last_free_day(
        job.available_on, preset.demurrage_free_days, preset.demurrage_day_type, holidays
    )
    demurrage_stop = _through(job.gate_out_on, job.as_of)
    demurrage_all = money_for(
        charge_days(demurrage_lfd, demurrage_stop, preset.demurrage_day_type, holidays),
        preset.demurrage_rates,
        factor,
    )
    demurrage_accrued = money_for(
        charge_days(demurrage_lfd, min(demurrage_stop, job.as_of), preset.demurrage_day_type, holidays),
        preset.demurrage_rates,
        factor,
    )

    detention_lfd: date | None = None
    detention_all: list[tuple[date, float]] = []
    detention_accrued: list[tuple[date, float]] = []
    if job.gate_out_on is not None:
        detention_lfd = last_free_day(
            job.gate_out_on, preset.detention_free_days, preset.detention_day_type, holidays
        )
        detention_stop = _through(job.empty_return_on, job.as_of)
        detention_all = money_for(
            charge_days(detention_lfd, detention_stop, preset.detention_day_type, holidays),
            preset.detention_rates,
            factor,
        )
        detention_accrued = money_for(
            charge_days(detention_lfd, min(detention_stop, job.as_of), preset.detention_day_type, holidays),
            preset.detention_rates,
            factor,
        )

    demurrage_map = {day: usd for day, usd in demurrage_all}
    detention_map = {day: usd for day, usd in detention_all}

    end = max(
        [
            job.as_of,
            job.available_on,
            demurrage_lfd,
            demurrage_stop,
            job.gate_out_on or job.available_on,
            detention_lfd or job.available_on,
            job.empty_return_on or job.available_on,
        ]
    )
    calendar: list[DayCell] = []
    cursor = job.available_on
    while cursor <= end:
        flags: list[str] = []
        if cursor == job.available_on:
            flags.append("available")
        if cursor == demurrage_lfd:
            flags.append("lfd_demurrage")
        if job.gate_out_on is not None and cursor == job.gate_out_on:
            flags.append("gate_out")
        if detention_lfd is not None and cursor == detention_lfd:
            flags.append("lfd_detention")
        if job.empty_return_on is not None and cursor == job.empty_return_on:
            flags.append("empty_return")
        skipped = is_skipped(cursor, "business", holidays)
        calendar.append(
            DayCell(
                date=cursor,
                weekday=WEEKDAYS[cursor.weekday()],
                skipped=skipped,
                holiday=cursor in holidays,
                flags=tuple(flags),
                demurrage_usd=demurrage_map.get(cursor, 0.0),
                detention_usd=detention_map.get(cursor, 0.0),
            )
        )
        cursor += timedelta(days=1)

    return ClockResult(
        job=job,
        demurrage_lfd=demurrage_lfd,
        detention_lfd=detention_lfd,
        demurrage_days=len(demurrage_all),
        detention_days=len(detention_all),
        demurrage_usd=round(sum(usd for _, usd in demurrage_all), 2),
        detention_usd=round(sum(usd for _, usd in detention_all), 2),
        accrued_demurrage_usd=round(sum(usd for _, usd in demurrage_accrued), 2),
        accrued_detention_usd=round(sum(usd for _, usd in detention_accrued), 2),
        status=_status(job, demurrage_lfd, detention_lfd),
        calendar=calendar,
    )
