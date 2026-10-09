"""Wave input types: orders, lots, and allocation policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .policies import HOLD_STATES, STRATEGIES, Policy, get_policy, normalize_hold


def parse_date(value: str, label: str) -> date:
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} '{value}' must be YYYY-MM-DD") from exc


@dataclass(frozen=True)
class Order:
    id: str
    sku: str
    qty: int
    ship_by: str
    priority: int = 2
    min_remaining_days: int | None = None

    def ship_date(self) -> date:
        return parse_date(self.ship_by, f"Order '{self.id}' ship_by")

    def life_floor(self, policy: Policy) -> int:
        if self.min_remaining_days is None:
            return policy.min_remaining_days
        return self.min_remaining_days

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each order needs an id")
        if not self.sku.strip():
            raise ValueError(f"Order '{self.id}' needs a sku")
        if self.qty < 1:
            raise ValueError(f"Order '{self.id}' qty must be at least 1")
        self.ship_date()
        if self.priority < 1:
            raise ValueError(f"Order '{self.id}' priority must be at least 1")
        if self.min_remaining_days is not None and self.min_remaining_days < 0:
            raise ValueError(f"Order '{self.id}' min_remaining_days cannot be negative")

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "sku": self.sku,
            "qty": self.qty,
            "ship_by": self.ship_by,
            "priority": self.priority,
        }
        if self.min_remaining_days is not None:
            data["min_remaining_days"] = self.min_remaining_days
        return data


@dataclass(frozen=True)
class Lot:
    id: str
    sku: str
    qty: int
    expiry: str
    received: str
    location: str = ""
    hold: str = ""

    def expiry_date(self) -> date:
        return parse_date(self.expiry, f"Lot '{self.id}' expiry")

    def received_date(self) -> date:
        return parse_date(self.received, f"Lot '{self.id}' received")

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each lot needs an id")
        if not self.sku.strip():
            raise ValueError(f"Lot '{self.id}' needs a sku")
        if self.qty < 1:
            raise ValueError(f"Lot '{self.id}' qty must be at least 1")
        expiry = self.expiry_date()
        received = self.received_date()
        if received > expiry:
            raise ValueError(f"Lot '{self.id}' received date is after expiry")
        if self.hold not in HOLD_STATES:
            raise ValueError(f"Lot '{self.id}' hold must be empty or {', '.join(s for s in HOLD_STATES if s)}")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sku": self.sku,
            "qty": self.qty,
            "expiry": self.expiry,
            "received": self.received,
            "location": self.location,
            "hold": self.hold,
        }


@dataclass
class Wave:
    policy: Policy
    orders: list[Order]
    lots: list[Lot]
    today: str = "2026-10-09"
    strategy: str = "fefo"

    def today_date(self) -> date:
        return parse_date(self.today, "today")

    def validate(self) -> None:
        self.policy.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        self.today_date()
        if not self.orders:
            raise ValueError("Wave has no orders")
        if not self.lots:
            raise ValueError("Wave has no lots")
        seen_orders: set[str] = set()
        for order in self.orders:
            order.validate()
            if order.id in seen_orders:
                raise ValueError(f"Duplicate order '{order.id}'")
            seen_orders.add(order.id)
        seen_lots: set[str] = set()
        for lot in self.lots:
            lot.validate()
            if lot.id in seen_lots:
                raise ValueError(f"Duplicate lot '{lot.id}'")
            seen_lots.add(lot.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Wave:
        orders: list[Order] = []
        for raw in payload.get("orders") or []:
            life = raw.get("min_remaining_days")
            orders.append(
                Order(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    qty=int(raw.get("qty", 0)),
                    ship_by=str(raw.get("ship_by", "")).strip(),
                    priority=int(raw.get("priority", 2)),
                    min_remaining_days=None if life in (None, "") else int(life),
                )
            )
        lots: list[Lot] = []
        for raw in payload.get("lots") or []:
            lots.append(
                Lot(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    qty=int(raw.get("qty", 0)),
                    expiry=str(raw.get("expiry", "")).strip(),
                    received=str(raw.get("received", "")).strip(),
                    location=str(raw.get("location", "")).strip(),
                    hold=normalize_hold(str(raw.get("hold", ""))),
                )
            )
        wave = cls(
            policy=get_policy(payload.get("policy") or {}),
            orders=orders,
            lots=lots,
            today=str(payload.get("today", "")).strip() or "2026-10-09",
            strategy=str(payload.get("strategy", "fefo")).strip() or "fefo",
        )
        wave.validate()
        return wave
