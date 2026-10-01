"""Forward-pick layouts and replenishment labor caps.

Aisle counts, min/max working rules, and travel minutes are typical
desk-side figures, not a particular WMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Warehouse:
    id: str
    name: str
    aisle_count: int
    bays_per_aisle: int
    max_tasks: int
    max_labor_min: int
    minutes_per_task: int
    aisle_change_min: int = 4

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["slot_count"] = self.aisle_count * self.bays_per_aisle
        return data

    def in_layout(self, aisle: int, bay: int) -> bool:
        return 1 <= aisle <= self.aisle_count and 1 <= bay <= self.bays_per_aisle


PRESETS: dict[str, Warehouse] = {
    "grocery_6": Warehouse(
        id="grocery_6",
        name="Grocery forward pick",
        aisle_count=6,
        bays_per_aisle=8,
        max_tasks=12,
        max_labor_min=90,
        minutes_per_task=6,
        aisle_change_min=4,
    ),
    "ecom_4": Warehouse(
        id="ecom_4",
        name="E-commerce piece pick",
        aisle_count=4,
        bays_per_aisle=10,
        max_tasks=10,
        max_labor_min=60,
        minutes_per_task=5,
        aisle_change_min=3,
    ),
    "wholesale_8": Warehouse(
        id="wholesale_8",
        name="Wholesale case pick",
        aisle_count=8,
        bays_per_aisle=6,
        max_tasks=16,
        max_labor_min=120,
        minutes_per_task=8,
        aisle_change_min=5,
    ),
    "mini_3": Warehouse(
        id="mini_3",
        name="Small demo block",
        aisle_count=3,
        bays_per_aisle=4,
        max_tasks=6,
        max_labor_min=40,
        minutes_per_task=5,
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
            "max_tasks",
            "max_labor_min",
            "minutes_per_task",
            "aisle_change_min",
        ):
            if field in raw:
                updates[field] = raw[field]
        return Warehouse(
            id=base.id,
            name=str(updates.get("name", base.name)),
            aisle_count=int(updates.get("aisle_count", base.aisle_count)),
            bays_per_aisle=int(updates.get("bays_per_aisle", base.bays_per_aisle)),
            max_tasks=int(updates.get("max_tasks", base.max_tasks)),
            max_labor_min=int(updates.get("max_labor_min", base.max_labor_min)),
            minutes_per_task=int(updates.get("minutes_per_task", base.minutes_per_task)),
            aisle_change_min=int(updates.get("aisle_change_min", base.aisle_change_min)),
        )

    required = (
        "name",
        "aisle_count",
        "bays_per_aisle",
        "max_tasks",
        "max_labor_min",
        "minutes_per_task",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"Custom warehouse is missing: {', '.join(missing)}")
    return Warehouse(
        id=str(raw.get("id", "custom")),
        name=str(raw["name"]),
        aisle_count=int(raw["aisle_count"]),
        bays_per_aisle=int(raw["bays_per_aisle"]),
        max_tasks=int(raw["max_tasks"]),
        max_labor_min=int(raw["max_labor_min"]),
        minutes_per_task=int(raw["minutes_per_task"]),
        aisle_change_min=int(raw.get("aisle_change_min", 4)),
    )
