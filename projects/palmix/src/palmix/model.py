"""Build input types: cases, stores, and a pallet deck."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .decks import STRATEGIES, TEMPS, Deck, get_deck


def _as_int(value: Any, field: str, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def _as_bool(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


@dataclass(frozen=True)
class CaseSpec:
    sku: str
    store: str
    family: str
    temp: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    quantity: int = 1
    crushable: bool = False
    this_side_up: bool = True

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each case needs a sku")
        if not self.store.strip():
            raise ValueError(f"SKU '{self.sku}' needs a store")
        if not self.family.strip():
            raise ValueError(f"SKU '{self.sku}' needs a family")
        if self.temp not in TEMPS:
            raise ValueError(f"SKU '{self.sku}' temp must be {', '.join(TEMPS)}")
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0:
            raise ValueError(f"SKU '{self.sku}' dimensions must be positive")
        if self.weight_kg < 0:
            raise ValueError(f"SKU '{self.sku}' weight cannot be negative")
        if self.quantity < 1:
            raise ValueError(f"SKU '{self.sku}' quantity must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "store": self.store,
            "family": self.family,
            "temp": self.temp,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "quantity": self.quantity,
            "crushable": self.crushable,
            "this_side_up": self.this_side_up,
        }


@dataclass
class Build:
    deck: Deck
    cases: list[CaseSpec]
    strategy: str = "auto"
    labor_minutes: int | None = None
    allow_rotation: bool = True
    store_lock: bool = True

    def labor_cap(self) -> int:
        return self.labor_minutes if self.labor_minutes is not None else self.deck.max_labor_min

    def validate(self) -> None:
        self.deck.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if self.labor_minutes is not None and self.labor_minutes < 1:
            raise ValueError("labor_minutes must be at least 1")
        if not self.cases:
            raise ValueError("Build has no cases")
        seen: set[tuple[str, str]] = set()
        for case in self.cases:
            case.validate()
            key = (case.sku, case.store)
            if key in seen:
                raise ValueError(f"Duplicate sku '{case.sku}' for store '{case.store}'")
            seen.add(key)

    def expand(self) -> list[CaseSpec]:
        pieces: list[CaseSpec] = []
        for case in self.cases:
            for _ in range(case.quantity):
                pieces.append(
                    CaseSpec(
                        sku=case.sku,
                        store=case.store,
                        family=case.family,
                        temp=case.temp,
                        length_mm=case.length_mm,
                        width_mm=case.width_mm,
                        height_mm=case.height_mm,
                        weight_kg=case.weight_kg,
                        quantity=1,
                        crushable=case.crushable,
                        this_side_up=case.this_side_up,
                    )
                )
        return pieces

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Build:
        deck = get_deck(payload.get("deck") or {})
        cases: list[CaseSpec] = []
        for raw in payload.get("cases") or []:
            cases.append(
                CaseSpec(
                    sku=str(raw.get("sku", "")).strip(),
                    store=str(raw.get("store", "")).strip(),
                    family=str(raw.get("family") or raw.get("sku") or "").strip(),
                    temp=str(raw.get("temp", "dry")).strip() or "dry",
                    length_mm=_as_int(raw.get("length_mm"), "length_mm"),
                    width_mm=_as_int(raw.get("width_mm"), "width_mm"),
                    height_mm=_as_int(raw.get("height_mm"), "height_mm"),
                    weight_kg=_as_float(raw.get("weight_kg"), "weight_kg"),
                    quantity=_as_int(raw.get("quantity", 1), "quantity", 1),
                    crushable=_as_bool(raw.get("crushable"), False),
                    this_side_up=_as_bool(raw.get("this_side_up"), True),
                )
            )
        labor = payload.get("labor_minutes")
        build = cls(
            deck=deck,
            cases=cases,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
            labor_minutes=None if labor in (None, "") else int(labor),
            allow_rotation=_as_bool(payload.get("allow_rotation"), True),
            store_lock=_as_bool(payload.get("store_lock"), True),
        )
        build.validate()
        return build
