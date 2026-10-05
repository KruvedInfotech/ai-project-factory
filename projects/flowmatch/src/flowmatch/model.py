"""Flow-plan input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .yards import TEMPS, Yard, clock_to_min, get_yard

STRATEGIES = ("auto", "cutoff", "lane", "live")


@dataclass(frozen=True)
class Receipt:
    id: str
    sku: str
    pallets: int
    eta: str
    door: str
    temp: str = "dry"

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each receipt needs an id")
        if not self.sku.strip():
            raise ValueError(f"Receipt '{self.id}' needs a sku")
        if self.pallets < 1:
            raise ValueError(f"Receipt '{self.id}' pallets must be at least 1")
        clock_to_min(self.eta)
        if not self.door.strip():
            raise ValueError(f"Receipt '{self.id}' needs a door")
        if self.temp not in TEMPS:
            raise ValueError(f"Receipt '{self.id}' temp must be {', '.join(TEMPS)}")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sku": self.sku,
            "pallets": self.pallets,
            "eta": self.eta,
            "door": self.door,
            "temp": self.temp,
        }


@dataclass(frozen=True)
class Order:
    id: str
    sku: str
    pallets: int
    cutoff: str
    door: str
    temp: str = "dry"
    priority: int = 2
    route: str = ""

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each order needs an id")
        if not self.sku.strip():
            raise ValueError(f"Order '{self.id}' needs a sku")
        if self.pallets < 1:
            raise ValueError(f"Order '{self.id}' pallets must be at least 1")
        clock_to_min(self.cutoff)
        if not self.door.strip():
            raise ValueError(f"Order '{self.id}' needs a door")
        if self.temp not in TEMPS:
            raise ValueError(f"Order '{self.id}' temp must be {', '.join(TEMPS)}")
        if self.priority < 1:
            raise ValueError(f"Order '{self.id}' priority must be at least 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sku": self.sku,
            "pallets": self.pallets,
            "cutoff": self.cutoff,
            "door": self.door,
            "temp": self.temp,
            "priority": self.priority,
            "route": self.route,
        }


@dataclass
class FlowPlan:
    yard: Yard
    receipts: list[Receipt]
    orders: list[Order]
    strategy: str = "auto"

    def validate(self) -> None:
        self.yard.validate()
        if self.strategy not in STRATEGIES:
            raise ValueError(f"strategy must be {', '.join(STRATEGIES)}")
        if not self.receipts:
            raise ValueError("Flow plan has no inbound receipts")
        if not self.orders:
            raise ValueError("Flow plan has no outbound orders")
        seen_in: set[str] = set()
        for receipt in self.receipts:
            receipt.validate()
            if receipt.id in seen_in:
                raise ValueError(f"Duplicate receipt '{receipt.id}'")
            seen_in.add(receipt.id)
        seen_out: set[str] = set()
        for order in self.orders:
            order.validate()
            if order.id in seen_out:
                raise ValueError(f"Duplicate order '{order.id}'")
            seen_out.add(order.id)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FlowPlan:
        receipts = []
        for raw in payload.get("receipts") or []:
            receipts.append(
                Receipt(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    pallets=int(raw["pallets"]),
                    eta=str(raw.get("eta", "")).strip(),
                    door=str(raw.get("door", "")).strip(),
                    temp=str(raw.get("temp", "dry")).strip(),
                )
            )
        orders = []
        for raw in payload.get("orders") or []:
            orders.append(
                Order(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    pallets=int(raw["pallets"]),
                    cutoff=str(raw.get("cutoff", "")).strip(),
                    door=str(raw.get("door", "")).strip(),
                    temp=str(raw.get("temp", "dry")).strip(),
                    priority=int(raw.get("priority", 2)),
                    route=str(raw.get("route", "")).strip(),
                )
            )
        plan = cls(
            yard=get_yard(payload.get("yard") or {}),
            receipts=receipts,
            orders=orders,
            strategy=str(payload.get("strategy", "auto")).strip() or "auto",
        )
        plan.validate()
        return plan
