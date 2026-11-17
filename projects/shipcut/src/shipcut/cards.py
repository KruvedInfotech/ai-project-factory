"""Screening carrier cards and destination zones.

Cutoffs, transit, and piece caps are typical dock figures, not a carrier tariff
or a booking window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time


WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    max_km: float

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "max_km": None if math.isinf(self.max_km) else self.max_km,
        }


ZONES: tuple[Zone, ...] = (
    Zone("Z1", "Metro", 80),
    Zone("Z2", "Near", 250),
    Zone("Z3", "Regional", 500),
    Zone("Z4", "Long", 1000),
    Zone("Z5", "National", float("inf")),
)


def zone_for(distance_km: float) -> Zone:
    if distance_km < 0:
        raise ValueError("Distance cannot be negative")
    for zone in ZONES:
        if distance_km <= zone.max_km:
            return zone
    return ZONES[-1]


def get_zone(zone_id: str) -> Zone:
    for zone in ZONES:
        if zone.id == zone_id:
            return zone
    known = ", ".join(z.id for z in ZONES)
    raise ValueError(f"Unknown zone '{zone_id}'. Known: {known}")


@dataclass(frozen=True)
class Carrier:
    id: str
    name: str
    cutoff: time
    pickup_weekdays: tuple[int, ...]
    transit_days: dict[str, int]
    max_weight_kg: float
    max_side_cm: float
    skip_sunday: bool = True
    skip_saturday_delivery: bool = False

    def pickup_label(self) -> str:
        days = tuple(self.pickup_weekdays)
        if days == (0, 1, 2, 3, 4, 5):
            return "Mon–Sat"
        if days == (0, 1, 2, 3, 4):
            return "Mon–Fri"
        return ",".join(WEEKDAY_NAMES[d] for d in days)

    def transit_label(self) -> str:
        parts = [f"{zone}:{days}" for zone, days in self.transit_days.items()]
        return " ".join(parts)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "cutoff": self.cutoff.strftime("%H:%M"),
            "pickup_weekdays": list(self.pickup_weekdays),
            "pickup_label": self.pickup_label(),
            "transit_days": dict(self.transit_days),
            "max_weight_kg": self.max_weight_kg,
            "max_side_cm": self.max_side_cm,
            "skip_sunday": self.skip_sunday,
            "skip_saturday_delivery": self.skip_saturday_delivery,
        }


MON_SAT = (0, 1, 2, 3, 4, 5)
MON_FRI = (0, 1, 2, 3, 4)

CARRIERS: dict[str, Carrier] = {
    "metro_same": Carrier(
        "metro_same",
        "Metro same-day",
        time(12, 0),
        MON_SAT,
        {"Z1": 0, "Z2": 1},
        max_weight_kg=20,
        max_side_cm=80,
        skip_saturday_delivery=True,
    ),
    "air_express": Carrier(
        "air_express",
        "Air express",
        time(15, 0),
        MON_SAT,
        {"Z1": 1, "Z2": 1, "Z3": 2, "Z4": 2, "Z5": 3},
        max_weight_kg=30,
        max_side_cm=120,
    ),
    "night_run": Carrier(
        "night_run",
        "Night linehaul",
        time(21, 0),
        MON_SAT,
        {"Z1": 1, "Z2": 1, "Z3": 2, "Z4": 3, "Z5": 4},
        max_weight_kg=40,
        max_side_cm=120,
        skip_saturday_delivery=True,
    ),
    "ground_std": Carrier(
        "ground_std",
        "Ground standard",
        time(18, 0),
        MON_SAT,
        {"Z1": 1, "Z2": 2, "Z3": 3, "Z4": 4, "Z5": 5},
        max_weight_kg=50,
        max_side_cm=150,
        skip_saturday_delivery=True,
    ),
    "economy": Carrier(
        "economy",
        "Economy road",
        time(17, 0),
        MON_FRI,
        {"Z1": 2, "Z2": 3, "Z3": 4, "Z4": 5, "Z5": 7},
        max_weight_kg=70,
        max_side_cm=180,
        skip_saturday_delivery=True,
    ),
}
