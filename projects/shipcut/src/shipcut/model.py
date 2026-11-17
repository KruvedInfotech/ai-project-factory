"""Order input types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .cards import Zone, get_zone, zone_for


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

    def longest_cm(self) -> float:
        return max(self.length_cm, self.width_cm, self.height_cm)


@dataclass
class Job:
    origin: str
    destination: str
    ready_at: datetime
    promised_on: date
    zone: Zone
    pieces: list[Piece]
    distance_km: float | None = None

    def validate(self) -> None:
        if not self.pieces:
            raise ValueError("Order has no pieces")
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
        ready_at = _parse_dt(payload.get("ready_at"))
        promised_on = _parse_date(payload.get("promised_on"))
        distance = payload.get("distance_km")
        zone_id = payload.get("zone")
        if zone_id:
            zone = get_zone(str(zone_id).strip().upper())
        elif distance is not None:
            zone = zone_for(float(distance))
        else:
            raise ValueError("Order needs a zone or distance_km")
        job = cls(
            origin=_place_name(payload.get("origin"), "Origin"),
            destination=_place_name(payload.get("destination"), "Destination"),
            ready_at=ready_at,
            promised_on=promised_on,
            zone=zone,
            pieces=pieces,
            distance_km=None if distance is None else float(distance),
        )
        job.validate()
        return job


def _parse_dt(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value
    if not value:
        raise ValueError("ready_at is required (ISO datetime)")
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("ready_at must be an ISO datetime") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        raise ValueError("promised_on is required (YYYY-MM-DD)")
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise ValueError("promised_on must be YYYY-MM-DD") from exc


def _place_name(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        if name:
            return name
    return fallback
