"""Shipper carton catalogs.

Inner dimensions are working figures for a pack bench, not a particular
corrugate spec sheet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEMPS = ("dry", "chill", "freeze")


@dataclass(frozen=True)
class Shipper:
    id: str
    name: str
    length_mm: int
    width_mm: int
    height_mm: int
    max_weight_kg: float

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["volume_l"] = round(self.volume_mm3 / 1_000_000, 3)
        return data


@dataclass(frozen=True)
class Catalog:
    id: str
    name: str
    cartons: tuple[Shipper, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "carton_count": len(self.cartons),
            "cartons": [carton.as_dict() for carton in self.cartons],
        }

    def get(self, carton_id: str) -> Shipper:
        for carton in self.cartons:
            if carton.id == carton_id:
                return carton
        known = ", ".join(c.id for c in self.cartons)
        raise ValueError(f"Unknown shipper '{carton_id}'. Known: {known}")


MAILER_S = Shipper("mailer_s", "Small mailer", 250, 180, 40, 2)
MAILER_M = Shipper("mailer_m", "Medium mailer", 330, 240, 50, 5)
MAILER_L = Shipper("mailer_l", "Large mailer", 400, 300, 80, 8)
CUBE_S = Shipper("cube_s", "Small cube", 150, 150, 150, 5)
BOX_4 = Shipper("box_4", "#4 RSC", 300, 220, 150, 10)
BOX_6 = Shipper("box_6", "#6 RSC", 400, 300, 250, 18)
BOX_12 = Shipper("box_12", "#12 RSC", 500, 400, 300, 25)
BOX_18 = Shipper("box_18", "#18 RSC", 600, 400, 400, 30)
BOX_24 = Shipper("box_24", "#24 RSC", 700, 500, 400, 35)
SHIP_HALF = Shipper("ship_half", "Half shipper", 400, 300, 250, 20)
SHIP_FULL = Shipper("ship_full", "Full shipper", 600, 400, 400, 30)
CRATE = Shipper("crate", "Returnable crate", 600, 400, 300, 25)


PRESETS: dict[str, Catalog] = {
    "ecom_pack": Catalog(
        "ecom_pack",
        "E-com pack bench",
        (MAILER_S, MAILER_M, MAILER_L, CUBE_S, BOX_4, BOX_6),
    ),
    "parcel_dc": Catalog(
        "parcel_dc",
        "Parcel DC corrugate",
        (BOX_4, BOX_6, BOX_12, BOX_18, BOX_24),
    ),
    "grocery_shipper": Catalog(
        "grocery_shipper",
        "Grocery store shipper",
        (SHIP_HALF, SHIP_FULL, CRATE, BOX_12),
    ),
}


def get_catalog(payload: dict) -> Catalog:
    if "preset" in payload and payload["preset"]:
        key = str(payload["preset"])
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"Unknown catalog preset '{key}'. Known: {known}")
        preset = PRESETS[key]
        raw_cartons = payload.get("cartons")
        if not raw_cartons:
            return preset
        return Catalog(
            id=preset.id,
            name=str(payload.get("name") or preset.name),
            cartons=_parse_cartons(raw_cartons),
        )
    raw_cartons = payload.get("cartons")
    if not raw_cartons:
        raise ValueError("Custom catalog needs cartons, or pass a preset")
    return Catalog(
        id="custom",
        name=str(payload.get("name") or "Custom shipper catalog"),
        cartons=_parse_cartons(raw_cartons),
    )


def _parse_cartons(raw_cartons: list) -> tuple[Shipper, ...]:
    cartons = []
    seen: set[str] = set()
    for raw in raw_cartons:
        carton_id = str(raw.get("id") or "").strip()
        if not carton_id:
            raise ValueError("Each shipper carton needs an id")
        if carton_id in seen:
            raise ValueError(f"Duplicate shipper '{carton_id}'")
        seen.add(carton_id)
        length_mm = int(raw["length_mm"])
        width_mm = int(raw["width_mm"])
        height_mm = int(raw["height_mm"])
        max_weight_kg = float(raw["max_weight_kg"])
        if min(length_mm, width_mm, height_mm) <= 0:
            raise ValueError(f"Shipper '{carton_id}' dimensions must be positive")
        if max_weight_kg <= 0:
            raise ValueError(f"Shipper '{carton_id}' max_weight_kg must be positive")
        cartons.append(
            Shipper(
                id=carton_id,
                name=str(raw.get("name") or carton_id),
                length_mm=length_mm,
                width_mm=width_mm,
                height_mm=height_mm,
                max_weight_kg=max_weight_kg,
            )
        )
    if not cartons:
        raise ValueError("Catalog has no shipper cartons")
    return tuple(cartons)
