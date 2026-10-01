"""Replenishment-plan input types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .warehouses import Warehouse, get_warehouse

STRATEGIES = ("auto", "urgent", "demand", "cluster")


@dataclass(frozen=True)
class Face:
    id: str
    sku: str
    aisle: int
    bay: int
    min_qty: int
    max_qty: int
    on_hand: int
    case_qty: int
    priority: int = 2

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each face needs an id")
        if not self.sku.strip():
            raise ValueError(f"Face '{self.id}' needs a sku")
        if self.aisle < 1 or self.bay < 1:
            raise ValueError(f"Face '{self.id}' aisle and bay must be ≥ 1")
        if self.min_qty < 0:
            raise ValueError(f"Face '{self.id}' min_qty cannot be negative")
        if self.max_qty < 1:
            raise ValueError(f"Face '{self.id}' max_qty must be at least 1")
        if self.max_qty < self.min_qty:
            raise ValueError(f"Face '{self.id}' max_qty must be ≥ min_qty")
        if self.on_hand < 0:
            raise ValueError(f"Face '{self.id}' on_hand cannot be negative")
        if self.case_qty < 1:
            raise ValueError(f"Face '{self.id}' case_qty must be at least 1")
        if self.priority < 1:
            raise ValueError(f"Face '{self.id}' priority must be ≥ 1 (1 is first)")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sku": self.sku,
            "aisle": self.aisle,
            "bay": self.bay,
            "min_qty": self.min_qty,
            "max_qty": self.max_qty,
            "on_hand": self.on_hand,
            "case_qty": self.case_qty,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class Reserve:
    id: str
    sku: str
    aisle: int
    cases: int

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("Each reserve location needs an id")
        if not self.sku.strip():
            raise ValueError(f"Reserve '{self.id}' needs a sku")
        if self.aisle < 1:
            raise ValueError(f"Reserve '{self.id}' aisle must be ≥ 1")
        if self.cases < 0:
            raise ValueError(f"Reserve '{self.id}' cases cannot be negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sku": self.sku,
            "aisle": self.aisle,
            "cases": self.cases,
        }


@dataclass
class FillPlan:
    warehouse: Warehouse
    faces: list[Face]
    reserve: list[Reserve]
    demand: dict[str, int]
    strategy: str = "auto"

    def validate(self) -> None:
        if self.warehouse.aisle_count < 1 or self.warehouse.bays_per_aisle < 1:
            raise ValueError("Warehouse layout must have at least one aisle and bay")
        if self.warehouse.max_tasks < 1:
            raise ValueError("max_tasks must be at least 1")
        if self.warehouse.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")
        if self.warehouse.minutes_per_task < 1:
            raise ValueError("minutes_per_task must be at least 1")
        if self.warehouse.aisle_change_min < 0:
            raise ValueError("aisle_change_min cannot be negative")
        if not self.faces:
            raise ValueError("Fill plan has no pick faces")
        if self.strategy not in STRATEGIES:
            raise ValueError(
                f"Unknown strategy '{self.strategy}'. Known: {', '.join(STRATEGIES)}"
            )
        seen_faces: set[str] = set()
        seen_skus: set[str] = set()
        for face in self.faces:
            face.validate()
            if face.id in seen_faces:
                raise ValueError(f"Duplicate face id '{face.id}'")
            seen_faces.add(face.id)
            if face.sku in seen_skus:
                raise ValueError(f"Duplicate sku '{face.sku}' — one face per sku")
            seen_skus.add(face.sku)
        seen_reserve: set[str] = set()
        for loc in self.reserve:
            loc.validate()
            if loc.id in seen_reserve:
                raise ValueError(f"Duplicate reserve id '{loc.id}'")
            seen_reserve.add(loc.id)
        for sku, units in self.demand.items():
            if units < 0:
                raise ValueError(f"Demand for '{sku}' cannot be negative")

    def demand_for(self, sku: str) -> int:
        return int(self.demand.get(sku, 0))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FillPlan:
        warehouse = get_warehouse(payload.get("warehouse") or {})
        faces: list[Face] = []
        for raw in payload.get("faces") or []:
            faces.append(
                Face(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    aisle=int(raw["aisle"]),
                    bay=int(raw["bay"]),
                    min_qty=int(raw["min_qty"]),
                    max_qty=int(raw["max_qty"]),
                    on_hand=int(raw["on_hand"]),
                    case_qty=int(raw["case_qty"]),
                    priority=int(raw.get("priority", 2)),
                )
            )
        reserve: list[Reserve] = []
        for raw in payload.get("reserve") or []:
            reserve.append(
                Reserve(
                    id=str(raw.get("id", "")).strip(),
                    sku=str(raw.get("sku", "")).strip(),
                    aisle=int(raw["aisle"]),
                    cases=int(raw["cases"]),
                )
            )
        demand: dict[str, int] = {}
        for raw in payload.get("demand") or []:
            sku = str(raw.get("sku", "")).strip()
            if not sku:
                raise ValueError("Each demand line needs a sku")
            demand[sku] = demand.get(sku, 0) + int(raw["units"])
        plan = cls(
            warehouse=warehouse,
            faces=faces,
            reserve=reserve,
            demand=demand,
            strategy=str(payload.get("strategy", "auto")),
        )
        plan.validate()
        return plan
