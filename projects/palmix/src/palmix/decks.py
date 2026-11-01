"""Pallet deck catalogs.

Footprints, stack heights, and payloads are working figures for a planner,
not a particular pallet-pool spec sheet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPS = ("dry", "chill", "freeze")
STRATEGIES = ("auto", "store", "heavy", "compact")


@dataclass(frozen=True)
class Deck:
    id: str
    name: str
    length_mm: int
    width_mm: int
    height_mm: int
    max_weight_kg: float
    temp: str
    minutes_per_pallet: int
    minutes_per_case: int
    max_labor_min: int
    max_pallets: int

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    def accepts_temp(self, temp: str) -> bool:
        if self.temp == "mixed":
            return temp in TEMPS
        return temp == self.temp

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["volume_m3"] = round(self.volume_mm3 / 1_000_000_000, 4)
        return data

    def validate(self) -> None:
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0:
            raise ValueError("Deck dimensions must be positive")
        if self.max_weight_kg <= 0:
            raise ValueError("Deck payload must be positive")
        if self.temp not in (*TEMPS, "mixed"):
            raise ValueError("Deck temp must be dry, chill, freeze, or mixed")
        if min(self.minutes_per_pallet, self.minutes_per_case) < 0:
            raise ValueError("Deck minute rates cannot be negative")
        if self.max_labor_min < 1:
            raise ValueError("Deck labor cap must be at least 1 minute")
        if self.max_pallets < 1:
            raise ValueError("Deck max_pallets must be at least 1")


DECKS: dict[str, Deck] = {
    "gma_48": Deck(
        "gma_48",
        "GMA 48×40 grocery",
        length_mm=1219,
        width_mm=1016,
        height_mm=1500,
        max_weight_kg=1000,
        temp="dry",
        minutes_per_pallet=8,
        minutes_per_case=1,
        max_labor_min=90,
        max_pallets=12,
    ),
    "eur": Deck(
        "eur",
        "EUR pallet",
        length_mm=1200,
        width_mm=800,
        height_mm=1440,
        max_weight_kg=1000,
        temp="dry",
        minutes_per_pallet=8,
        minutes_per_case=1,
        max_labor_min=90,
        max_pallets=12,
    ),
    "chep": Deck(
        "chep",
        "CHEP 48×40",
        length_mm=1219,
        width_mm=1016,
        height_mm=1600,
        max_weight_kg=1250,
        temp="dry",
        minutes_per_pallet=8,
        minutes_per_case=1,
        max_labor_min=100,
        max_pallets=16,
    ),
    "chill_gma": Deck(
        "chill_gma",
        "Chill GMA 48×40",
        length_mm=1219,
        width_mm=1016,
        height_mm=1200,
        max_weight_kg=800,
        temp="chill",
        minutes_per_pallet=10,
        minutes_per_case=1,
        max_labor_min=60,
        max_pallets=8,
    ),
}


def get_deck(payload: dict) -> Deck:
    fields = (
        "length_mm",
        "width_mm",
        "height_mm",
        "max_weight_kg",
        "temp",
        "minutes_per_pallet",
        "minutes_per_case",
        "max_labor_min",
        "max_pallets",
    )
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in DECKS:
            known = ", ".join(sorted(DECKS))
            raise ValueError(f"Unknown deck preset '{key}'. Known: {known}")
        preset = DECKS[key]
        values = {field: getattr(preset, field) for field in fields}
        for field in fields:
            if field in payload and payload[field] not in (None, ""):
                values[field] = payload[field]
        deck = Deck(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            length_mm=int(values["length_mm"]),
            width_mm=int(values["width_mm"]),
            height_mm=int(values["height_mm"]),
            max_weight_kg=float(values["max_weight_kg"]),
            temp=str(values["temp"]),
            minutes_per_pallet=int(values["minutes_per_pallet"]),
            minutes_per_case=int(values["minutes_per_case"]),
            max_labor_min=int(values["max_labor_min"]),
            max_pallets=int(values["max_pallets"]),
        )
        deck.validate()
        return deck
    required = ("length_mm", "width_mm", "height_mm", "max_weight_kg")
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Custom deck missing: {', '.join(missing)}")
    deck = Deck(
        id="custom",
        name=str(payload.get("name") or "Custom pallet deck"),
        length_mm=int(payload["length_mm"]),
        width_mm=int(payload["width_mm"]),
        height_mm=int(payload["height_mm"]),
        max_weight_kg=float(payload["max_weight_kg"]),
        temp=str(payload.get("temp") or "dry"),
        minutes_per_pallet=int(payload.get("minutes_per_pallet", 8)),
        minutes_per_case=int(payload.get("minutes_per_case", 1)),
        max_labor_min=int(payload.get("max_labor_min", 90)),
        max_pallets=int(payload.get("max_pallets", 12)),
    )
    deck.validate()
    return deck
