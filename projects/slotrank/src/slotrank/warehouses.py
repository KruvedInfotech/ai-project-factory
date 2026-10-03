"""Forward-pick layouts and slotting labor caps.

Aisle counts, golden-zone boxes, and travel minutes are typical
desk-side figures, not a particular WMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


SLOT_TYPES = ("piece", "case", "pallet")


@dataclass(frozen=True)
class Warehouse:
    id: str
    name: str
    aisle_count: int
    bays_per_aisle: int
    golden_aisles: int
    golden_bays: int
    default_slot_type: str
    default_max_cube: int
    max_moves: int
    max_labor_min: int
    minutes_per_move: int
    aisle_change_min: int = 4
    heavy_bays: tuple[int, ...] = (1,)
    a_share: float = 0.80
    b_share: float = 0.15

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["slot_count"] = self.aisle_count * self.bays_per_aisle
        data["heavy_bays"] = list(self.heavy_bays)
        return data

    def in_layout(self, aisle: int, bay: int) -> bool:
        return 1 <= aisle <= self.aisle_count and 1 <= bay <= self.bays_per_aisle

    def is_golden(self, aisle: int, bay: int) -> bool:
        return 1 <= aisle <= self.golden_aisles and 1 <= bay <= self.golden_bays

    def allows_heavy(self, bay: int) -> bool:
        return bay in self.heavy_bays

    def location_id(self, aisle: int, bay: int) -> str:
        return f"A{aisle}-{bay:02d}"


PRESETS: dict[str, Warehouse] = {
    "grocery_6": Warehouse(
        id="grocery_6",
        name="Grocery forward pick",
        aisle_count=6,
        bays_per_aisle=8,
        golden_aisles=2,
        golden_bays=4,
        default_slot_type="case",
        default_max_cube=40,
        max_moves=12,
        max_labor_min=90,
        minutes_per_move=6,
        aisle_change_min=4,
    ),
    "ecom_4": Warehouse(
        id="ecom_4",
        name="E-commerce piece pick",
        aisle_count=4,
        bays_per_aisle=10,
        golden_aisles=2,
        golden_bays=5,
        default_slot_type="piece",
        default_max_cube=16,
        max_moves=10,
        max_labor_min=60,
        minutes_per_move=5,
        aisle_change_min=3,
    ),
    "wholesale_8": Warehouse(
        id="wholesale_8",
        name="Wholesale case pick",
        aisle_count=8,
        bays_per_aisle=6,
        golden_aisles=3,
        golden_bays=3,
        default_slot_type="case",
        default_max_cube=80,
        max_moves=16,
        max_labor_min=120,
        minutes_per_move=8,
        aisle_change_min=5,
    ),
    "mini_3": Warehouse(
        id="mini_3",
        name="Small demo block",
        aisle_count=3,
        bays_per_aisle=4,
        golden_aisles=1,
        golden_bays=2,
        default_slot_type="case",
        default_max_cube=40,
        max_moves=6,
        max_labor_min=40,
        minutes_per_move=5,
        aisle_change_min=4,
    ),
}


def get_warehouse(raw: dict[str, object]) -> Warehouse:
    if "preset" in raw:
        key = str(raw["preset"])
        if key not in PRESETS:
            raise ValueError(
                f"Unknown warehouse preset '{key}'. Known: {', '.join(sorted(PRESETS))}"
            )
        base = PRESETS[key]
        updates: dict[str, object] = {}
        for field in (
            "name",
            "aisle_count",
            "bays_per_aisle",
            "golden_aisles",
            "golden_bays",
            "default_slot_type",
            "default_max_cube",
            "max_moves",
            "max_labor_min",
            "minutes_per_move",
            "aisle_change_min",
            "a_share",
            "b_share",
        ):
            if field in raw:
                updates[field] = raw[field]
        heavy_bays = base.heavy_bays
        if "heavy_bays" in raw:
            heavy_bays = tuple(int(item) for item in list(raw["heavy_bays"]))  # type: ignore[arg-type]
        slot_type = str(updates.get("default_slot_type", base.default_slot_type))
        if slot_type not in SLOT_TYPES:
            raise ValueError(
                f"Unknown slot type '{slot_type}'. Known: {', '.join(SLOT_TYPES)}"
            )
        return Warehouse(
            id=base.id,
            name=str(updates.get("name", base.name)),
            aisle_count=int(updates.get("aisle_count", base.aisle_count)),
            bays_per_aisle=int(updates.get("bays_per_aisle", base.bays_per_aisle)),
            golden_aisles=int(updates.get("golden_aisles", base.golden_aisles)),
            golden_bays=int(updates.get("golden_bays", base.golden_bays)),
            default_slot_type=slot_type,
            default_max_cube=int(updates.get("default_max_cube", base.default_max_cube)),
            max_moves=int(updates.get("max_moves", base.max_moves)),
            max_labor_min=int(updates.get("max_labor_min", base.max_labor_min)),
            minutes_per_move=int(updates.get("minutes_per_move", base.minutes_per_move)),
            aisle_change_min=int(updates.get("aisle_change_min", base.aisle_change_min)),
            heavy_bays=heavy_bays,
            a_share=float(updates.get("a_share", base.a_share)),
            b_share=float(updates.get("b_share", base.b_share)),
        )

    required = (
        "name",
        "aisle_count",
        "bays_per_aisle",
        "golden_aisles",
        "golden_bays",
        "default_slot_type",
        "default_max_cube",
        "max_moves",
        "max_labor_min",
        "minutes_per_move",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"Custom warehouse is missing: {', '.join(missing)}")
    slot_type = str(raw["default_slot_type"])
    if slot_type not in SLOT_TYPES:
        raise ValueError(
            f"Unknown slot type '{slot_type}'. Known: {', '.join(SLOT_TYPES)}"
        )
    heavy_raw = raw.get("heavy_bays", (1,))
    return Warehouse(
        id=str(raw.get("id", "custom")),
        name=str(raw["name"]),
        aisle_count=int(raw["aisle_count"]),
        bays_per_aisle=int(raw["bays_per_aisle"]),
        golden_aisles=int(raw["golden_aisles"]),
        golden_bays=int(raw["golden_bays"]),
        default_slot_type=slot_type,
        default_max_cube=int(raw["default_max_cube"]),
        max_moves=int(raw["max_moves"]),
        max_labor_min=int(raw["max_labor_min"]),
        minutes_per_move=int(raw["minutes_per_move"]),
        aisle_change_min=int(raw.get("aisle_change_min", 4)),
        heavy_bays=tuple(int(item) for item in list(heavy_raw)),  # type: ignore[arg-type]
        a_share=float(raw.get("a_share", 0.80)),
        b_share=float(raw.get("b_share", 0.15)),
    )


def generate_locations(warehouse: Warehouse) -> list["Location"]:
    from .model import Location

    locations: list[Location] = []
    for aisle in range(1, warehouse.aisle_count + 1):
        for bay in range(1, warehouse.bays_per_aisle + 1):
            locations.append(
                Location(
                    id=warehouse.location_id(aisle, bay),
                    aisle=aisle,
                    bay=bay,
                    slot_type=warehouse.default_slot_type,
                    max_cube=warehouse.default_max_cube,
                    allow_heavy=warehouse.allows_heavy(bay),
                )
            )
    return locations
