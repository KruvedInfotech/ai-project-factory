"""Pick the next pickup that still makes the customer promise."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .cards import CARRIERS, Carrier
from .model import Job, Piece

MAKES_SLA = "makes_sla"
MISSED_CUTOFF = "missed_cutoff"
LATE = "late"
OVERSIZE = "oversize"
ZONE_BLOCKED = "zone_blocked"
NO_PICKUP = "no_pickup"


@dataclass
class CarrierPlan:
    carrier: str
    name: str
    status: str
    cutoff: str
    pickup_label: str
    pickup_at: str | None
    delivery_on: str | None
    transit_days: int | None
    minutes_remaining: int | None
    missed_today: bool
    days_late: int | None
    reason: str | None = None
    detail: dict[str, object] = field(default_factory=dict)

    @property
    def makes_sla(self) -> bool:
        return self.status == MAKES_SLA

    def as_dict(self) -> dict[str, object]:
        return {
            "carrier": self.carrier,
            "name": self.name,
            "status": self.status,
            "cutoff": self.cutoff,
            "pickup_label": self.pickup_label,
            "pickup_at": self.pickup_at,
            "delivery_on": self.delivery_on,
            "transit_days": self.transit_days,
            "minutes_remaining": self.minutes_remaining,
            "missed_today": self.missed_today,
            "days_late": self.days_late,
            "reason": self.reason,
            "makes_sla": self.makes_sla,
            "detail": self.detail,
        }


@dataclass
class PlanResult:
    origin: str
    destination: str
    ready_at: str
    promised_on: str
    zone: str
    zone_name: str
    distance_km: float | None
    piece_count: int
    weight_kg: float
    longest_cm: float
    plans: list[CarrierPlan]
    winner: str | None
    winner_name: str | None
    soonest_cutoff_minutes: int | None
    makes_sla_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "ready_at": self.ready_at,
            "promised_on": self.promised_on,
            "zone": self.zone,
            "zone_name": self.zone_name,
            "distance_km": self.distance_km,
            "piece_count": self.piece_count,
            "weight_kg": round(self.weight_kg, 3),
            "longest_cm": round(self.longest_cm, 1),
            "plans": [item.as_dict() for item in self.plans],
            "winner": self.winner,
            "winner_name": self.winner_name,
            "soonest_cutoff_minutes": self.soonest_cutoff_minutes,
            "makes_sla_count": self.makes_sla_count,
        }


def plan(job: Job) -> PlanResult:
    job.validate()
    pieces = job.expand()
    weight = sum(p.weight_kg for p in pieces)
    longest = max(p.longest_cm() for p in pieces)
    plans = [_plan_carrier(job, pieces, carrier) for carrier in CARRIERS.values()]
    feasible = [item for item in plans if item.makes_sla]
    feasible.sort(
        key=lambda item: (
            item.delivery_on or "9999-12-31",
            item.pickup_at or "9999-12-31T99:99:99",
            item.name,
        )
    )
    winner = feasible[0] if feasible else None
    remaining = [
        item.minutes_remaining
        for item in feasible
        if item.minutes_remaining is not None
    ]
    return PlanResult(
        origin=job.origin,
        destination=job.destination,
        ready_at=_fmt_dt(job.ready_at),
        promised_on=job.promised_on.isoformat(),
        zone=job.zone.id,
        zone_name=job.zone.name,
        distance_km=job.distance_km,
        piece_count=len(pieces),
        weight_kg=weight,
        longest_cm=longest,
        plans=plans,
        winner=winner.carrier if winner else None,
        winner_name=winner.name if winner else None,
        soonest_cutoff_minutes=min(remaining) if remaining else None,
        makes_sla_count=len(feasible),
    )


def _plan_carrier(job: Job, pieces: list[Piece], carrier: Carrier) -> CarrierPlan:
    cutoff = carrier.cutoff.strftime("%H:%M")
    oversize = _oversize_reason(pieces, carrier)
    if oversize:
        return _closed(carrier, OVERSIZE, oversize, cutoff)
    transit = carrier.transit_days.get(job.zone.id)
    if transit is None:
        served = ", ".join(carrier.transit_days) or "none"
        return _closed(
            carrier,
            ZONE_BLOCKED,
            f"{carrier.name} does not serve {job.zone.id} (serves {served})",
            cutoff,
        )
    pickup = next_pickup(job.ready_at, carrier)
    if pickup is None:
        return _closed(carrier, NO_PICKUP, f"no {carrier.name} pickup in the next two weeks", cutoff)

    delivery = add_transit(
        pickup.date(),
        transit,
        skip_sunday=carrier.skip_sunday,
        skip_saturday=carrier.skip_saturday_delivery,
    )
    minutes = _minutes_remaining(job.ready_at, pickup)
    missed_today = _missed_today(job.ready_at, carrier)
    days_late = (delivery - job.promised_on).days
    detail = {
        "max_weight_kg": carrier.max_weight_kg,
        "max_side_cm": carrier.max_side_cm,
        "skip_sunday": carrier.skip_sunday,
        "skip_saturday_delivery": carrier.skip_saturday_delivery,
    }
    if delivery <= job.promised_on:
        reason = None
        if missed_today:
            reason = f"missed today's {cutoff} cutoff; next pickup still makes {job.promised_on.isoformat()}"
        return CarrierPlan(
            carrier=carrier.id,
            name=carrier.name,
            status=MAKES_SLA,
            cutoff=cutoff,
            pickup_label=carrier.pickup_label(),
            pickup_at=_fmt_dt(pickup),
            delivery_on=delivery.isoformat(),
            transit_days=transit,
            minutes_remaining=minutes,
            missed_today=missed_today,
            days_late=days_late,
            reason=reason,
            detail=detail,
        )

    hypo = _todays_missed_cutoff(job.ready_at, carrier)
    if hypo is not None:
        hypo_delivery = add_transit(
            hypo.date(),
            transit,
            skip_sunday=carrier.skip_sunday,
            skip_saturday=carrier.skip_saturday_delivery,
        )
        if hypo_delivery <= job.promised_on:
            return CarrierPlan(
                carrier=carrier.id,
                name=carrier.name,
                status=MISSED_CUTOFF,
                cutoff=cutoff,
                pickup_label=carrier.pickup_label(),
                pickup_at=_fmt_dt(pickup),
                delivery_on=delivery.isoformat(),
                transit_days=transit,
                minutes_remaining=None,
                missed_today=True,
                days_late=days_late,
                reason=(
                    f"missed {cutoff} cutoff; a same-day pickup would have delivered "
                    f"{hypo_delivery.isoformat()}"
                ),
                detail=detail,
            )

    return CarrierPlan(
        carrier=carrier.id,
        name=carrier.name,
        status=LATE,
        cutoff=cutoff,
        pickup_label=carrier.pickup_label(),
        pickup_at=_fmt_dt(pickup),
        delivery_on=delivery.isoformat(),
        transit_days=transit,
        minutes_remaining=minutes,
        missed_today=missed_today,
        days_late=days_late,
        reason=f"earliest delivery {delivery.isoformat()} is {days_late} day(s) after promise",
        detail=detail,
    )


def next_pickup(ready: datetime, carrier: Carrier) -> datetime | None:
    day = ready.date()
    for _ in range(16):
        if day.weekday() in carrier.pickup_weekdays:
            cutoff_dt = datetime.combine(day, carrier.cutoff)
            if ready <= cutoff_dt:
                return cutoff_dt
        day += timedelta(days=1)
    return None


def add_transit(
    pickup_on: date,
    transit_days: int,
    *,
    skip_sunday: bool,
    skip_saturday: bool,
) -> date:
    result = pickup_on + timedelta(days=transit_days)
    while True:
        if skip_sunday and result.weekday() == 6:
            result += timedelta(days=1)
            continue
        if skip_saturday and result.weekday() == 5:
            result += timedelta(days=1)
            continue
        break
    return result


def _oversize_reason(pieces: list[Piece], carrier: Carrier) -> str | None:
    for piece in pieces:
        if piece.weight_kg > carrier.max_weight_kg + 1e-9:
            return (
                f"piece '{piece.sku}' {piece.weight_kg:g} kg exceeds "
                f"{carrier.max_weight_kg:g} kg cap"
            )
        longest = piece.longest_cm()
        if longest > carrier.max_side_cm + 1e-9:
            return (
                f"piece '{piece.sku}' longest side {longest:g} cm exceeds "
                f"{carrier.max_side_cm:g} cm"
            )
    return None


def _missed_today(ready: datetime, carrier: Carrier) -> bool:
    return _todays_missed_cutoff(ready, carrier) is not None


def _todays_missed_cutoff(ready: datetime, carrier: Carrier) -> datetime | None:
    day = ready.date()
    if day.weekday() not in carrier.pickup_weekdays:
        return None
    cutoff_dt = datetime.combine(day, carrier.cutoff)
    if ready > cutoff_dt:
        return cutoff_dt
    return None


def _minutes_remaining(ready: datetime, pickup: datetime) -> int | None:
    if pickup.date() != ready.date() or pickup < ready:
        return None
    return int((pickup - ready).total_seconds() // 60)


def _closed(carrier: Carrier, status: str, reason: str, cutoff: str) -> CarrierPlan:
    return CarrierPlan(
        carrier=carrier.id,
        name=carrier.name,
        status=status,
        cutoff=cutoff,
        pickup_label=carrier.pickup_label(),
        pickup_at=None,
        delivery_on=None,
        transit_days=None,
        minutes_remaining=None,
        missed_today=False,
        days_late=None,
        reason=reason,
        detail={
            "max_weight_kg": carrier.max_weight_kg,
            "max_side_cm": carrier.max_side_cm,
        },
    )


def _fmt_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")
