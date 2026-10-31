"""Warehouse floor layouts and pick-cart catalogs.

Aisle counts, tote slots, and payloads are working figures for a planner,
not a particular cart OEM or location master.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPS = ("dry", "chill", "freeze")
STRATEGIES = ("auto", "aisle", "priority", "compact")


@dataclass(frozen=True)
class Warehouse:
    id: str
    name: str
    aisles: tuple[str, ...]
    bays: int

    @property
    def bay_count(self) -> int:
        return len(self.aisles) * self.bays

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["aisles"] = list(self.aisles)
        data["bay_count"] = self.bay_count
        return data

    def contains(self, aisle: str, bay: int) -> bool:
        return aisle in self.aisles and 1 <= bay <= self.bays

    def aisle_index(self, aisle: str) -> int:
        try:
            return self.aisles.index(aisle)
        except ValueError as exc:
            raise ValueError(f"Aisle '{aisle}' is not on this floor") from exc

    def span(self, aisles: set[str]) -> int:
        if not aisles:
            return 0
        indexes = [self.aisle_index(aisle) for aisle in aisles]
        return max(indexes) - min(indexes)


@dataclass(frozen=True)
class Cart:
    id: str
    name: str
    tote_slots: int
    max_weight_kg: float
    max_volume_l: float
    temp: str
    max_aisle_span: int
    minutes_per_cart: int
    minutes_per_order: int
    minutes_per_line: int
    max_labor_min: int

    @property
    def max_volume_mm3(self) -> int:
        return int(round(self.max_volume_l * 1_000_000))

    def accepts_temp(self, temp: str) -> bool:
        if self.temp == "mixed":
            return temp in TEMPS
        return temp == self.temp

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["max_volume_mm3"] = self.max_volume_mm3
        return data

    def validate(self) -> None:
        if self.tote_slots < 1:
            raise ValueError("Cart tote_slots must be at least 1")
        if self.max_weight_kg <= 0:
            raise ValueError("Cart payload must be positive")
        if self.max_volume_l <= 0:
            raise ValueError("Cart cube must be positive")
        if self.temp not in (*TEMPS, "mixed"):
            raise ValueError("Cart temp must be dry, chill, freeze, or mixed")
        if self.max_aisle_span < 0:
            raise ValueError("Cart max_aisle_span cannot be negative")
        if min(self.minutes_per_cart, self.minutes_per_order, self.minutes_per_line) < 0:
            raise ValueError("Cart minute rates cannot be negative")
        if self.max_labor_min < 1:
            raise ValueError("Cart labor cap must be at least 1 minute")


WAREHOUSES: dict[str, Warehouse] = {
    "small_dc": Warehouse("small_dc", "4-aisle case pick", ("A", "B", "C", "D"), 10),
    "grocery": Warehouse("grocery", "6-aisle grocery", ("A", "B", "C", "D", "E", "F"), 12),
    "ecom": Warehouse("ecom", "8-aisle each-pick", ("A", "B", "C", "D", "E", "F", "G", "H"), 16),
}

CARTS: dict[str, Cart] = {
    "ecom_8tote": Cart(
        "ecom_8tote",
        "8-tote each-pick cart",
        tote_slots=8,
        max_weight_kg=45,
        max_volume_l=80,
        temp="dry",
        max_aisle_span=3,
        minutes_per_cart=6,
        minutes_per_order=1,
        minutes_per_line=1,
        max_labor_min=90,
    ),
    "grocery_4tote": Cart(
        "grocery_4tote",
        "4-tote grocery case cart",
        tote_slots=4,
        max_weight_kg=90,
        max_volume_l=160,
        temp="dry",
        max_aisle_span=2,
        minutes_per_cart=8,
        minutes_per_order=1,
        minutes_per_line=1,
        max_labor_min=60,
    ),
    "chill_6tote": Cart(
        "chill_6tote",
        "6-tote chill cart",
        tote_slots=6,
        max_weight_kg=50,
        max_volume_l=70,
        temp="chill",
        max_aisle_span=4,
        minutes_per_cart=7,
        minutes_per_order=1,
        minutes_per_line=1,
        max_labor_min=48,
    ),
}


def _aisles_from(value: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if value in (None, ""):
        return fallback
    if isinstance(value, int):
        if value < 1:
            raise ValueError("Warehouse needs at least one aisle")
        return tuple(chr(ord("A") + i) for i in range(value))
    aisles = tuple(str(item).strip() for item in value if str(item).strip())  # type: ignore[union-attr]
    if not aisles:
        raise ValueError("Warehouse needs at least one aisle")
    return aisles


def get_warehouse(payload: dict) -> Warehouse:
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in WAREHOUSES:
            known = ", ".join(sorted(WAREHOUSES))
            raise ValueError(f"Unknown warehouse preset '{key}'. Known: {known}")
        preset = WAREHOUSES[key]
        return Warehouse(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            aisles=_aisles_from(payload.get("aisles"), preset.aisles),
            bays=int(payload["bays"]) if payload.get("bays") not in (None, "") else preset.bays,
        )
    aisles = _aisles_from(payload.get("aisles"), ())
    if not aisles:
        raise ValueError("Custom warehouse missing: aisles")
    if payload.get("bays") in (None, ""):
        raise ValueError("Custom warehouse missing: bays")
    bays = int(payload["bays"])
    if bays < 1:
        raise ValueError("Warehouse bays must be at least 1")
    return Warehouse(
        id="custom",
        name=str(payload.get("name") or "Custom pick floor"),
        aisles=aisles,
        bays=bays,
    )


def get_cart(payload: dict) -> Cart:
    fields = (
        "tote_slots",
        "max_weight_kg",
        "max_volume_l",
        "temp",
        "max_aisle_span",
        "minutes_per_cart",
        "minutes_per_order",
        "minutes_per_line",
        "max_labor_min",
    )
    if payload.get("preset"):
        key = str(payload["preset"])
        if key not in CARTS:
            known = ", ".join(sorted(CARTS))
            raise ValueError(f"Unknown cart preset '{key}'. Known: {known}")
        preset = CARTS[key]
        values = {field: getattr(preset, field) for field in fields}
        for field in fields:
            if field in payload and payload[field] not in (None, ""):
                values[field] = payload[field]
        cart = Cart(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            tote_slots=int(values["tote_slots"]),
            max_weight_kg=float(values["max_weight_kg"]),
            max_volume_l=float(values["max_volume_l"]),
            temp=str(values["temp"]),
            max_aisle_span=int(values["max_aisle_span"]),
            minutes_per_cart=int(values["minutes_per_cart"]),
            minutes_per_order=int(values["minutes_per_order"]),
            minutes_per_line=int(values["minutes_per_line"]),
            max_labor_min=int(values["max_labor_min"]),
        )
        cart.validate()
        return cart
    missing = [field for field in ("tote_slots", "max_weight_kg", "max_volume_l") if field not in payload]
    if missing:
        raise ValueError(f"Custom cart missing: {', '.join(missing)}")
    cart = Cart(
        id="custom",
        name=str(payload.get("name") or "Custom pick cart"),
        tote_slots=int(payload["tote_slots"]),
        max_weight_kg=float(payload["max_weight_kg"]),
        max_volume_l=float(payload["max_volume_l"]),
        temp=str(payload.get("temp") or "dry"),
        max_aisle_span=int(payload.get("max_aisle_span", 99)),
        minutes_per_cart=int(payload.get("minutes_per_cart", 6)),
        minutes_per_order=int(payload.get("minutes_per_order", 1)),
        minutes_per_line=int(payload.get("minutes_per_line", 1)),
        max_labor_min=int(payload.get("max_labor_min", 90)),
    )
    cart.validate()
    return cart
