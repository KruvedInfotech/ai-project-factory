"""Quote parcel, LTL, and FTL against the screening cards and pick a winner."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .cards import (
    DIM_DIVISOR_CM3_PER_KG,
    FT3_PER_M3,
    LB_PER_KG,
    LTL_MAX_KG,
    LTL_MAX_M3,
    LTL_MIN_CHARGE_USD,
    LTL_MIN_LB,
    PARCEL_MAX_KG,
    PARCEL_MAX_LENGTH_GIRTH_CM,
    PARCEL_MAX_SIDE_CM,
    TRUCKS,
    Truck,
    freight_class,
    ltl_band_for,
    parcel_zone_for,
)
from .model import Job, Piece


def money(value: float) -> float:
    return round(value + 1e-12, 2)


def ceil_half_kg(kg: float) -> float:
    return math.ceil(kg * 2 - 1e-12) / 2


@dataclass(frozen=True)
class Line:
    label: str
    amount_usd: float


@dataclass
class ModeQuote:
    mode: str
    name: str
    feasible: bool
    total_usd: float | None
    reason: str | None = None
    lines: list[Line] = field(default_factory=list)
    detail: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "name": self.name,
            "feasible": self.feasible,
            "total_usd": self.total_usd,
            "reason": self.reason,
            "lines": [{"label": line.label, "amount_usd": line.amount_usd} for line in self.lines],
            "detail": self.detail,
        }


@dataclass
class ShipmentStats:
    piece_count: int
    weight_kg: float
    cube_m3: float
    longest_cm: float
    density_kg_m3: float
    pcf: float
    freight_class: float
    weight_lb: float

    def as_dict(self) -> dict[str, object]:
        return {
            "piece_count": self.piece_count,
            "weight_kg": round(self.weight_kg, 3),
            "cube_m3": round(self.cube_m3, 6),
            "longest_cm": round(self.longest_cm, 1),
            "density_kg_m3": round(self.density_kg_m3, 2),
            "pcf": round(self.pcf, 2),
            "freight_class": self.freight_class,
            "weight_lb": round(self.weight_lb, 2),
        }


@dataclass
class QuoteResult:
    origin: str
    destination: str
    distance_km: float
    stats: ShipmentStats
    quotes: list[ModeQuote]
    winner: str | None
    winner_usd: float | None
    savings_usd: float | None

    @property
    def all_feasible(self) -> bool:
        return all(item.feasible for item in self.quotes)

    def as_dict(self) -> dict[str, object]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "distance_km": round(self.distance_km, 1),
            "stats": self.stats.as_dict(),
            "quotes": [item.as_dict() for item in self.quotes],
            "winner": self.winner,
            "winner_usd": self.winner_usd,
            "savings_usd": self.savings_usd,
            "all_feasible": self.all_feasible,
        }


def quote(job: Job) -> QuoteResult:
    job.validate()
    stats = _stats(job)
    quotes = [_quote_parcel(job, stats), _quote_ltl(job, stats), _quote_ftl(job, stats)]
    feasible = [item for item in quotes if item.feasible and item.total_usd is not None]
    feasible.sort(key=lambda item: (item.total_usd or 0.0, item.mode))
    winner = feasible[0] if feasible else None
    savings = None
    if winner and len(feasible) >= 2 and winner.total_usd is not None and feasible[1].total_usd is not None:
        savings = money(feasible[1].total_usd - winner.total_usd)
    return QuoteResult(
        origin=job.origin,
        destination=job.destination,
        distance_km=job.distance_km,
        stats=stats,
        quotes=quotes,
        winner=winner.mode if winner else None,
        winner_usd=winner.total_usd if winner else None,
        savings_usd=savings,
    )


def _stats(job: Job) -> ShipmentStats:
    pieces = job.expand()
    weight = sum(p.weight_kg for p in pieces)
    cube = sum(p.volume_m3 for p in pieces)
    longest = max(max(p.sorted_sides()) for p in pieces)
    density = weight / cube if cube else 0.0
    weight_lb = weight * LB_PER_KG
    cube_ft3 = cube * FT3_PER_M3
    pcf = weight_lb / cube_ft3 if cube_ft3 else 0.0
    return ShipmentStats(
        piece_count=len(pieces),
        weight_kg=weight,
        cube_m3=cube,
        longest_cm=longest,
        density_kg_m3=density,
        pcf=pcf,
        freight_class=freight_class(pcf),
        weight_lb=weight_lb,
    )


def _quote_parcel(job: Job, stats: ShipmentStats) -> ModeQuote:
    zone = parcel_zone_for(job.distance_km)
    divisor = job.dim_divisor or DIM_DIVISOR_CM3_PER_KG
    piece_bases: list[float] = []
    billable_total = 0.0
    actual_total = 0.0
    for piece in job.expand():
        reason = _parcel_piece_reason(piece, divisor)
        if reason:
            return ModeQuote(
                mode="parcel",
                name="Parcel",
                feasible=False,
                total_usd=None,
                reason=reason,
                detail={"zone": zone.id, "max_km": _finite(zone.max_km)},
            )
        billed = _billable_kg(piece, divisor)
        billable_total += billed
        actual_total += piece.weight_kg
        piece_bases.append(max(zone.min_piece_usd, zone.per_kg_usd * billed))
    subtotal = sum(piece_bases)
    fuel = money(subtotal * job.fuel_parcel)
    total = money(subtotal + fuel)
    return ModeQuote(
        mode="parcel",
        name="Parcel",
        feasible=True,
        total_usd=total,
        lines=[
            Line(f"{stats.piece_count} piece(s) · {zone.id} @ ${zone.per_kg_usd:.2f}/kg", money(subtotal)),
            Line(f"Fuel {job.fuel_parcel:.0%}", fuel),
        ],
        detail={
            "zone": zone.id,
            "max_km": _finite(zone.max_km),
            "per_kg_usd": zone.per_kg_usd,
            "min_piece_usd": zone.min_piece_usd,
            "actual_kg": round(actual_total, 3),
            "billable_kg": round(billable_total, 3),
            "dim_divisor": divisor,
        },
    )


def _parcel_piece_reason(piece: Piece, divisor: float) -> str | None:
    longest, mid, short = piece.sorted_sides()
    billed = _billable_kg(piece, divisor)
    girth = longest + 2 * (mid + short)
    if billed > PARCEL_MAX_KG + 1e-9:
        return f"piece '{piece.sku}' billable {billed:g} kg exceeds {PARCEL_MAX_KG:g} kg parcel cap"
    if longest > PARCEL_MAX_SIDE_CM + 1e-9:
        return f"piece '{piece.sku}' longest side {longest:g} cm exceeds {PARCEL_MAX_SIDE_CM:g} cm"
    if girth > PARCEL_MAX_LENGTH_GIRTH_CM + 1e-9:
        return f"piece '{piece.sku}' length+girth {girth:g} cm exceeds {PARCEL_MAX_LENGTH_GIRTH_CM:g} cm"
    return None


def _billable_kg(piece: Piece, divisor: float) -> float:
    dim = piece.volume_cm3 / divisor
    return ceil_half_kg(max(piece.weight_kg, dim, 0.5))


def _quote_ltl(job: Job, stats: ShipmentStats) -> ModeQuote:
    if stats.weight_kg > LTL_MAX_KG + 1e-9:
        return ModeQuote(
            mode="ltl",
            name="LTL",
            feasible=False,
            total_usd=None,
            reason=f"shipment {stats.weight_kg:g} kg exceeds {LTL_MAX_KG:g} kg LTL cap",
        )
    if stats.cube_m3 > LTL_MAX_M3 + 1e-9:
        return ModeQuote(
            mode="ltl",
            name="LTL",
            feasible=False,
            total_usd=None,
            reason=f"shipment {stats.cube_m3:.2f} m³ exceeds {LTL_MAX_M3:g} m³ LTL cap",
        )
    band = ltl_band_for(job.distance_km)
    klass = stats.freight_class
    cwt = max(stats.weight_lb, LTL_MIN_LB) / 100.0
    tariff = cwt * band.class100_per_cwt_usd * (klass / 100.0)
    discounted = tariff * (1.0 - job.ltl_discount)
    with_fuel = discounted * (1.0 + job.fuel_ltl)
    billed = max(LTL_MIN_CHARGE_USD, with_fuel)
    total = money(billed)
    lines = [
        Line(
            f"Class {klass:g} · {cwt:.2f} cwt · {band.id} @ ${band.class100_per_cwt_usd:.0f}",
            money(tariff),
        ),
        Line(f"Discount {job.ltl_discount:.0%}", money(discounted - tariff)),
        Line(f"Fuel {job.fuel_ltl:.0%}", money(with_fuel - discounted)),
    ]
    if billed == LTL_MIN_CHARGE_USD and with_fuel < LTL_MIN_CHARGE_USD:
        lines.append(Line("Minimum charge", money(LTL_MIN_CHARGE_USD - with_fuel)))
    return ModeQuote(
        mode="ltl",
        name="LTL",
        feasible=True,
        total_usd=total,
        lines=lines,
        detail={
            "band": band.id,
            "max_km": _finite(band.max_km),
            "freight_class": klass,
            "pcf": round(stats.pcf, 2),
            "cwt": round(cwt, 3),
            "tariff_usd": money(tariff),
            "min_charge_usd": LTL_MIN_CHARGE_USD,
        },
    )


def _quote_ftl(job: Job, stats: ShipmentStats) -> ModeQuote:
    options: list[tuple[float, TruckQuote]] = []
    skipped: list[dict[str, object]] = []
    for truck in TRUCKS.values():
        reasons: list[str] = []
        if stats.weight_kg > truck.max_weight_kg + 1e-9:
            reasons.append(f"weight {stats.weight_kg:g} kg > {truck.max_weight_kg:g} kg")
        if stats.cube_m3 > truck.usable_m3 + 1e-9:
            reasons.append(f"cube {stats.cube_m3:.3f} m³ > {truck.usable_m3:.3f} m³ usable")
        if reasons:
            skipped.append({"id": truck.id, "name": truck.name, "reason": "; ".join(reasons)})
            continue
        mileage = truck.per_km_usd * job.distance_km
        total = money(max(truck.minimum_usd, mileage))
        options.append(
            (
                total,
                TruckQuote(
                    truck=truck,
                    mileage_usd=money(mileage),
                    total_usd=total,
                    used_min=total == money(truck.minimum_usd) and mileage < truck.minimum_usd,
                ),
            )
        )
    if not options:
        return ModeQuote(
            mode="ftl",
            name="FTL",
            feasible=False,
            total_usd=None,
            reason="no truck fits cube (85% screening) and payload — try splitting or LoadFit for a 3D check",
            detail={"skipped": skipped},
        )
    options.sort(key=lambda item: (item[0], item[1].truck.volume_m3))
    chosen = options[0][1]
    truck = chosen.truck
    lines = [Line(f"{truck.name} · {job.distance_km:g} km @ ${truck.per_km_usd:.2f}/km", chosen.mileage_usd)]
    if chosen.used_min:
        lines.append(Line("Minimum charge", money(truck.minimum_usd - chosen.mileage_usd)))
    return ModeQuote(
        mode="ftl",
        name="FTL",
        feasible=True,
        total_usd=chosen.total_usd,
        lines=lines,
        detail={
            "truck": truck.id,
            "truck_name": truck.name,
            "volume_m3": truck.volume_m3,
            "usable_m3": round(truck.usable_m3, 4),
            "max_weight_kg": truck.max_weight_kg,
            "cube_fill": truck.cube_fill,
            "weight_utilization": round(stats.weight_kg / truck.max_weight_kg, 4),
            "cube_utilization": round(stats.cube_m3 / truck.volume_m3, 4),
            "skipped": skipped,
        },
    )


@dataclass
class TruckQuote:
    truck: Truck
    mileage_usd: float
    total_usd: float
    used_min: bool


def _finite(value: float) -> float | None:
    if math.isinf(value):
        return None
    return value
