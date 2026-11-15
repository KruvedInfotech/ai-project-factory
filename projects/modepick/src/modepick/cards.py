"""Screening rate cards: parcel zones, LTL bands, FTL trucks.

Figures are typical working cards for a dock-side mode check, not a
carrier tariff or a contract rate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ParcelZone:
    id: str
    max_km: float
    per_kg_usd: float
    min_piece_usd: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LtlBand:
    id: str
    max_km: float
    class100_per_cwt_usd: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Truck:
    id: str
    name: str
    volume_m3: float
    max_weight_kg: float
    per_km_usd: float
    minimum_usd: float
    cube_fill: float = 0.85

    @property
    def usable_m3(self) -> float:
        return self.volume_m3 * self.cube_fill

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["usable_m3"] = round(self.usable_m3, 4)
        return data


# Dimensional weight: L×W×H cm³ / divisor. 5000 is a common metric DIM factor.
DIM_DIVISOR_CM3_PER_KG = 5000.0
PARCEL_MAX_KG = 30.0
PARCEL_MAX_SIDE_CM = 120.0
PARCEL_MAX_LENGTH_GIRTH_CM = 300.0
PARCEL_FUEL = 0.12

# LTL screening: NMFC-style density class, US CWT, then a typical 45% discount.
LTL_FUEL = 0.18
LTL_DISCOUNT = 0.45
LTL_MIN_CHARGE_USD = 95.0
LTL_MIN_LB = 150.0
LTL_MAX_KG = 4500.0
LTL_MAX_M3 = 8.0
LB_PER_KG = 2.2046226218
FT3_PER_M3 = 35.3146667

# Density floor (lb/ft³) → freight class. Simplified NMFC-style table.
CLASS_BY_PCF: tuple[tuple[float, float], ...] = (
    (30.0, 70.0),
    (22.5, 85.0),
    (15.0, 92.5),
    (12.0, 100.0),
    (10.5, 125.0),
    (8.0, 150.0),
    (6.0, 175.0),
    (4.0, 250.0),
    (0.0, 300.0),
)

PARCEL_ZONES: tuple[ParcelZone, ...] = (
    ParcelZone("Z1", 80, 4.20, 8.50),
    ParcelZone("Z2", 250, 5.10, 9.50),
    ParcelZone("Z3", 500, 6.40, 11.00),
    ParcelZone("Z4", 1000, 8.20, 13.00),
    ParcelZone("Z5", 1800, 10.50, 16.00),
    ParcelZone("Z6", float("inf"), 13.80, 19.00),
)

LTL_BANDS: tuple[LtlBand, ...] = (
    LtlBand("local", 80, 28.0),
    LtlBand("short", 250, 42.0),
    LtlBand("regional", 500, 58.0),
    LtlBand("lane", 1000, 78.0),
    LtlBand("long", 1800, 105.0),
    LtlBand("cross", float("inf"), 132.0),
)

# Inner volumes match LoadFit's typical cargo-box millimetres.
TRUCKS: dict[str, Truck] = {
    "van_407": Truck("van_407", "Light truck / 407-class", 8.8776, 2500, 1.15, 90),
    "truck_14ft": Truck("truck_14ft", "14 ft box truck", 19.3652, 4000, 1.55, 140),
    "truck_20ft": Truck("truck_20ft", "20 ft box truck", 29.6244, 7000, 1.95, 220),
    "trailer_32ft": Truck("trailer_32ft", "32 ft trailer", 56.4480, 12000, 2.40, 320),
}


def parcel_zone_for(distance_km: float) -> ParcelZone:
    for zone in PARCEL_ZONES:
        if distance_km <= zone.max_km:
            return zone
    return PARCEL_ZONES[-1]


def ltl_band_for(distance_km: float) -> LtlBand:
    for band in LTL_BANDS:
        if distance_km <= band.max_km:
            return band
    return LTL_BANDS[-1]


def freight_class(pcf: float) -> float:
    for floor, klass in CLASS_BY_PCF:
        if pcf >= floor:
            return klass
    return 300.0
