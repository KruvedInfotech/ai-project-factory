"""Wave input types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .policies import DEFAULT_POLICY, get_grade, get_policy


@dataclass(frozen=True)
class Sku:
    sku: str
    dc_on_hand: int
    case_pack: int
    inner_pack: int = 1
    description: str = ""

    def pack_size(self, break_case: bool) -> int:
        size = self.inner_pack if break_case else self.case_pack
        if size < 1:
            raise ValueError(f"SKU '{self.sku}' pack size must be at least 1")
        return size

    def validate(self) -> None:
        if not self.sku.strip():
            raise ValueError("Each SKU needs an id")
        if self.dc_on_hand < 0:
            raise ValueError(f"SKU '{self.sku}' DC on-hand cannot be negative")
        if self.case_pack < 1:
            raise ValueError(f"SKU '{self.sku}' case_pack must be at least 1")
        if self.inner_pack < 1:
            raise ValueError(f"SKU '{self.sku}' inner_pack must be at least 1")
        if self.inner_pack > self.case_pack:
            raise ValueError(f"SKU '{self.sku}' inner_pack cannot exceed case_pack")


@dataclass(frozen=True)
class Book:
    sku: str
    on_hand: int
    forecast: int
    min_face: int
    max_cap: int

    def validate(self, sku_ids: set[str]) -> None:
        if not self.sku.strip():
            raise ValueError("Each store book needs a sku")
        if self.sku not in sku_ids:
            raise ValueError(f"Store book references unknown sku '{self.sku}'")
        if self.on_hand < 0:
            raise ValueError(f"Book '{self.sku}' on_hand cannot be negative")
        if self.forecast < 0:
            raise ValueError(f"Book '{self.sku}' forecast cannot be negative")
        if self.min_face < 0:
            raise ValueError(f"Book '{self.sku}' min_face cannot be negative")
        if self.max_cap < 0:
            raise ValueError(f"Book '{self.sku}' max_cap cannot be negative")


@dataclass(frozen=True)
class Store:
    store_id: str
    name: str
    grade: str
    books: tuple[Book, ...] = ()

    def book_for(self, sku: str) -> Book | None:
        for book in self.books:
            if book.sku == sku:
                return book
        return None

    def validate(self, sku_ids: set[str]) -> None:
        if not self.store_id.strip():
            raise ValueError("Each store needs a store_id")
        seen: set[str] = set()
        for book in self.books:
            book.validate(sku_ids)
            if book.sku in seen:
                raise ValueError(f"Store '{self.store_id}' has duplicate book for '{book.sku}'")
            seen.add(book.sku)


@dataclass
class Wave:
    wave: str
    dc: str
    policy: str
    holdback_pct: float
    break_case: bool
    skus: list[Sku]
    stores: list[Store] = field(default_factory=list)

    def sku_ids(self) -> set[str]:
        return {item.sku for item in self.skus}

    def sku(self, sku: str) -> Sku:
        for item in self.skus:
            if item.sku == sku:
                return item
        raise KeyError(sku)

    def validate(self) -> None:
        if not self.wave.strip():
            raise ValueError("Wave id is required")
        if self.holdback_pct < 0 or self.holdback_pct > 100:
            raise ValueError("holdback_pct must be between 0 and 100")
        if not self.skus:
            raise ValueError("Wave has no SKUs")
        if not self.stores:
            raise ValueError("Wave has no stores")
        seen_sku: set[str] = set()
        for item in self.skus:
            item.validate()
            if item.sku in seen_sku:
                raise ValueError(f"Duplicate sku '{item.sku}'")
            seen_sku.add(item.sku)
        seen_store: set[str] = set()
        for store in self.stores:
            store.validate(seen_sku)
            if store.store_id in seen_store:
                raise ValueError(f"Duplicate store_id '{store.store_id}'")
            seen_store.add(store.store_id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        if not isinstance(payload, dict):
            raise ValueError("Wave must be an object")
        wave = cls(
            wave=_text(payload.get("wave"), "Wave"),
            dc=_text(payload.get("dc"), "DC"),
            policy=get_policy(payload.get("policy") or DEFAULT_POLICY),
            holdback_pct=_number(payload.get("holdback_pct"), 0.0, "holdback_pct"),
            break_case=bool(payload.get("break_case", False)),
            skus=[_sku(raw) for raw in payload.get("skus") or []],
            stores=[_store(raw) for raw in payload.get("stores") or []],
        )
        wave.validate()
        return wave


def _text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _number(value: object, default: float, name: str) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc


def _int(raw: object, field: str, default: int | None = None) -> int:
    if raw is None:
        if default is None:
            raise ValueError(f"{field} is required")
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _sku(raw: object) -> Sku:
    if not isinstance(raw, dict):
        raise ValueError("Each SKU must be an object")
    return Sku(
        sku=str(raw.get("sku", "")).strip(),
        description=str(raw.get("description") or "").strip(),
        dc_on_hand=_int(raw.get("dc_on_hand"), "dc_on_hand"),
        case_pack=_int(raw.get("case_pack"), "case_pack"),
        inner_pack=_int(raw.get("inner_pack"), "inner_pack", 1),
    )


def _book(raw: object) -> Book:
    if not isinstance(raw, dict):
        raise ValueError("Each store book must be an object")
    return Book(
        sku=str(raw.get("sku", "")).strip(),
        on_hand=_int(raw.get("on_hand"), "on_hand", 0),
        forecast=_int(raw.get("forecast"), "forecast", 0),
        min_face=_int(raw.get("min_face"), "min_face", 0),
        max_cap=_int(raw.get("max_cap"), "max_cap"),
    )


def _store(raw: object) -> Store:
    if not isinstance(raw, dict):
        raise ValueError("Each store must be an object")
    books_raw = raw.get("books")
    if books_raw is None:
        books: tuple[Book, ...] = ()
    elif not isinstance(books_raw, list):
        raise ValueError("store books must be a list")
    else:
        books = tuple(_book(item) for item in books_raw)
    return Store(
        store_id=str(raw.get("store_id", "")).strip(),
        name=str(raw.get("name") or raw.get("store_id") or "").strip(),
        grade=get_grade(raw.get("grade") or "B"),
        books=books,
    )
