"""Vehicle and container inner dimensions.

Sizes are cargo-box interiors in millimetres, with a screening payload in kg.
They are typical working figures, not a particular OEM spec sheet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Container:
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
        data["volume_m3"] = round(self.volume_mm3 / 1_000_000_000, 4)
        return data


PRESETS: dict[str, Container] = {
    "van_407": Container("van_407", "Light truck / 407-class", 2740, 1800, 1800, 2500),
    "truck_14ft": Container("truck_14ft", "14 ft box truck", 4270, 2130, 2130, 4000),
    "truck_20ft": Container("truck_20ft", "20 ft box truck", 6100, 2130, 2280, 7000),
    "container_20ft": Container("container_20ft", "20 ft dry container", 5898, 2352, 2393, 21700),
    "container_40ft": Container("container_40ft", "40 ft dry container", 12032, 2352, 2393, 26600),
    "pallet_eu": Container("pallet_eu", "EUR pallet stack", 1200, 800, 1440, 1000),
}


def get_container(payload: dict) -> Container:
    if "preset" in payload and payload["preset"]:
        key = str(payload["preset"])
        if key not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"Unknown container preset '{key}'. Known: {known}")
        preset = PRESETS[key]
        overrides = {
            field: payload[field]
            for field in ("length_mm", "width_mm", "height_mm", "max_weight_kg")
            if field in payload and payload[field] is not None
        }
        if not overrides:
            return preset
        return Container(
            id=preset.id,
            name=payload.get("name", preset.name),
            length_mm=int(overrides.get("length_mm", preset.length_mm)),
            width_mm=int(overrides.get("width_mm", preset.width_mm)),
            height_mm=int(overrides.get("height_mm", preset.height_mm)),
            max_weight_kg=float(overrides.get("max_weight_kg", preset.max_weight_kg)),
        )
    required = ("length_mm", "width_mm", "height_mm", "max_weight_kg")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Custom container missing: {', '.join(missing)}")
    return Container(
        id="custom",
        name=str(payload.get("name") or "Custom cargo box"),
        length_mm=int(payload["length_mm"]),
        width_mm=int(payload["width_mm"]),
        height_mm=int(payload["height_mm"]),
        max_weight_kg=float(payload["max_weight_kg"]),
    )
