"""Warehouse rack-room layouts.

Aisles, bay counts, and levels are working figures for a map, not a
particular location master.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPS = ("dry", "chill", "freeze")
KINDS = ("pick", "reserve")


@dataclass(frozen=True)
class Warehouse:
    id: str
    name: str
    aisles: tuple[str, ...]
    bays: int
    levels: int

    @property
    def slot_count(self) -> int:
        return len(self.aisles) * self.bays * self.levels

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["aisles"] = list(self.aisles)
        data["slot_count"] = self.slot_count
        return data

    def contains(self, aisle: str, bay: int, level: int) -> bool:
        return aisle in self.aisles and 1 <= bay <= self.bays and 1 <= level <= self.levels


PRESETS: dict[str, Warehouse] = {
    "small_dc": Warehouse("small_dc", "4-aisle case pick", ("A", "B", "C", "D"), 10, 3),
    "grocery": Warehouse("grocery", "6-aisle grocery", ("A", "B", "C", "D", "E", "F"), 12, 4),
    "ecom": Warehouse("ecom", "8-aisle each-pick", ("A", "B", "C", "D", "E", "F", "G", "H"), 16, 3),
}


def get_warehouse(payload: dict) -> Warehouse:
    if "preset" in payload and payload["preset"]:
        key = str(payload["preset"])
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"Unknown warehouse preset '{key}'. Known: {known}")
        preset = PRESETS[key]
        aisles = payload.get("aisles")
        return Warehouse(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            aisles=tuple(str(a) for a in aisles) if aisles else preset.aisles,
            bays=int(payload.get("bays") or preset.bays),
            levels=int(payload.get("levels") or preset.levels),
        )
    required = ("aisles", "bays", "levels")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Custom warehouse missing: {', '.join(missing)}")
    aisles = tuple(str(a).strip() for a in payload["aisles"] if str(a).strip())
    if not aisles:
        raise ValueError("Custom warehouse needs at least one aisle")
    bays = int(payload["bays"])
    levels = int(payload["levels"])
    if bays < 1 or levels < 1:
        raise ValueError("Warehouse bays and levels must be at least 1")
    return Warehouse(
        id="custom",
        name=str(payload.get("name") or "Custom rack room"),
        aisles=aisles,
        bays=bays,
        levels=levels,
    )
