"""Receipt input types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cards import CLASS_ORDER, DEFAULT_CLASSES, get_level, get_severity


@dataclass(frozen=True)
class Lot:
    sku: str
    lot_size: int
    description: str = ""
    found: dict[str, int] | None = None

    def validate(self, class_ids: tuple[str, ...]) -> None:
        if not self.sku.strip():
            raise ValueError("Each lot needs a sku")
        if self.lot_size < 1:
            raise ValueError(f"Lot '{self.sku}' size must be at least 1")
        if self.found is None:
            return
        extra = set(self.found) - set(class_ids)
        if extra:
            raise ValueError(f"Lot '{self.sku}' has unknown defect class: {sorted(extra)[0]}")
        missing = [key for key in class_ids if key not in self.found]
        if missing:
            raise ValueError(f"Lot '{self.sku}' found counts missing class '{missing[0]}'")
        for key, count in self.found.items():
            if int(count) < 0:
                raise ValueError(f"Lot '{self.sku}' {key} found count cannot be negative")


@dataclass
class Receipt:
    receipt: str
    supplier: str
    dock: str
    level: str
    severity: str
    seed: str
    classes: dict[str, float]
    lots: list[Lot]
    history: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.receipt.strip():
            raise ValueError("Receipt id is required")
        if not self.classes:
            raise ValueError("Receipt needs at least one defect class AQL")
        for name, aql in self.classes.items():
            if not str(name).strip():
                raise ValueError("Defect class name is required")
            if aql < 0 or aql > 100:
                raise ValueError(f"AQL for '{name}' must be between 0 and 100")
        if not self.lots:
            raise ValueError("Receipt has no lots")
        seen: set[str] = set()
        class_ids = tuple(self.classes)
        for lot in self.lots:
            lot.validate(class_ids)
            if lot.sku in seen:
                raise ValueError(f"Duplicate sku '{lot.sku}'")
            seen.add(lot.sku)
        for item in self.history:
            if item not in ("accept", "reject"):
                raise ValueError("history entries must be 'accept' or 'reject'")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Receipt:
        receipt_id = _text(payload.get("receipt"), "Receipt")
        classes = _classes(payload.get("classes"))
        lots = [_lot(raw) for raw in payload.get("lots") or []]
        history = [str(item).strip().lower() for item in payload.get("history") or []]
        job = cls(
            receipt=receipt_id,
            supplier=_text(payload.get("supplier"), "Supplier"),
            dock=_text(payload.get("dock"), "Dock"),
            level=get_level(payload.get("level") or "II"),
            severity=get_severity(payload.get("severity") or "normal"),
            seed=_text(payload.get("seed"), receipt_id),
            classes=classes,
            lots=lots,
            history=history,
        )
        job.validate()
        return job


def _text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _classes(raw: object) -> dict[str, float]:
    if raw is None:
        return dict(DEFAULT_CLASSES)
    if not isinstance(raw, dict) or not raw:
        raise ValueError("classes must be an object of defect class → AQL percent")
    out: dict[str, float] = {}
    ordered = [key for key in CLASS_ORDER if key in raw]
    ordered.extend(key for key in raw if key not in CLASS_ORDER)
    for key in ordered:
        value = raw[key]
        if value is None:
            continue
        name = str(key).strip().lower()
        if not name:
            raise ValueError("Defect class name is required")
        try:
            aql = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"AQL for '{name}' must be a number") from exc
        out[name] = aql
    if not out:
        raise ValueError("Receipt needs at least one defect class AQL")
    return out


def _lot(raw: object) -> Lot:
    if not isinstance(raw, dict):
        raise ValueError("Each lot must be an object")
    found_raw = raw.get("found")
    found: dict[str, int] | None = None
    if found_raw is not None:
        if not isinstance(found_raw, dict):
            raise ValueError("found must be an object of class → count")
        found = {str(key).strip().lower(): int(value) for key, value in found_raw.items()}
    return Lot(
        sku=str(raw.get("sku", "")).strip(),
        lot_size=int(raw["lot_size"]),
        description=str(raw.get("description") or "").strip(),
        found=found,
    )
