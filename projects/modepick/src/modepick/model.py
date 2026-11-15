"""Shipment input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .geo import haversine_km


@dataclass(frozen=True)
class Piece:
    sku: str
    length_cm: float
    width_cm: float
    height_cm: float
    weight_kg: float
    quantity: int = 1

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each piece needs a sku")
        if min(self.length_cm, self.width_cm, self.height_cm) <= 0:
            raise ValueError(f"Piece '{self.sku}' dimensions must be positive")
        if self.weight_kg < 0:
            raise ValueError(f"Piece '{self.sku}' weight cannot be negative")
        if self.quantity < 1:
            raise ValueError(f"Piece '{self.sku}' quantity must be at least 1")

    @property
    def volume_cm3(self) -> float:
        return self.length_cm * self.width_cm * self.height_cm

    @property
    def volume_m3(self) -> float:
        return self.volume_cm3 / 1_000_000

    def sorted_sides(self) -> tuple[float, float, float]:
        sides = sorted((self.length_cm, self.width_cm, self.height_cm), reverse=True)
        return sides[0], sides[1], sides[2]


@dataclass
class Job:
    origin: str
    destination: str
    distance_km: float
    pieces: list[Piece]
    fuel_parcel: float = 0.12
    fuel_ltl: float = 0.18
    ltl_discount: float = 0.45
    dim_divisor: float = 5000.0

    def validate(self) -> None:
        if self.distance_km <= 0:
            raise ValueError("Distance must be positive")
        if not self.pieces:
            raise ValueError("Shipment has no pieces")
        if self.fuel_parcel < 0 or self.fuel_ltl < 0:
            raise ValueError("Fuel surcharge cannot be negative")
        if not 0 <= self.ltl_discount < 1:
            raise ValueError("LTL discount must be in [0, 1)")
        if self.dim_divisor <= 0:
            raise ValueError("DIM divisor must be positive")
        seen: set[str] = set()
        for piece in self.pieces:
            piece.validate()
            if piece.sku in seen:
                raise ValueError(f"Duplicate sku '{piece.sku}'")
            seen.add(piece.sku)

    def expand(self) -> list[Piece]:
        pieces: list[Piece] = []
        for piece in self.pieces:
            for _ in range(piece.quantity):
                pieces.append(
                    Piece(
                        sku=piece.sku,
                        length_cm=piece.length_cm,
                        width_cm=piece.width_cm,
                        height_cm=piece.height_cm,
                        weight_kg=piece.weight_kg,
                        quantity=1,
                    )
                )
        return pieces

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Job:
        pieces = []
        for raw in payload.get("pieces") or []:
            pieces.append(
                Piece(
                    sku=str(raw.get("sku", "")).strip(),
                    length_cm=float(raw["length_cm"]),
                    width_cm=float(raw["width_cm"]),
                    height_cm=float(raw["height_cm"]),
                    weight_kg=float(raw["weight_kg"]),
                    quantity=int(raw.get("quantity", 1)),
                )
            )
        distance = payload.get("distance_km")
        if distance is None:
            origin = payload.get("origin") or {}
            dest = payload.get("destination") or {}
            if not isinstance(origin, dict) or not isinstance(dest, dict):
                raise ValueError("Without distance_km, origin and destination need lat and lon")
            try:
                distance = haversine_km(
                    float(origin["lat"]),
                    float(origin["lon"]),
                    float(dest["lat"]),
                    float(dest["lon"]),
                )
            except (KeyError, TypeError) as exc:
                raise ValueError("Without distance_km, origin and destination need lat and lon") from exc
            origin_name = str(origin.get("name") or "Origin")
            dest_name = str(dest.get("name") or "Destination")
        else:
            distance = float(distance)
            origin_name = _place_name(payload.get("origin"), "Origin")
            dest_name = _place_name(payload.get("destination"), "Destination")
        job = cls(
            origin=origin_name,
            destination=dest_name,
            distance_km=distance,
            pieces=pieces,
            fuel_parcel=float(payload.get("fuel_parcel", 0.12)),
            fuel_ltl=float(payload.get("fuel_ltl", 0.18)),
            ltl_discount=float(payload.get("ltl_discount", 0.45)),
            dim_divisor=float(payload.get("dim_divisor", 5000.0)),
        )
        job.validate()
        return job


def _place_name(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        if name:
            return name
    return fallback
