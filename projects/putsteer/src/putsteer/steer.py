"""Greedy directed putaway: floor first, nearest legal slot, top-off first."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Location, Pallet, Wave
from .policies import Policy

REASON_ORDER = (
    "mix-sku",
    "weight",
    "height",
    "no-space",
    "blocked",
    "type",
    "temp",
)


@dataclass(frozen=True)
class Put:
    pallet_id: str
    sku: str
    location_id: str
    aisle: int
    bay: int
    level: int
    zone: str
    temp: str
    minutes: int
    topoff: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "pallet_id": self.pallet_id,
            "sku": self.sku,
            "location_id": self.location_id,
            "aisle": self.aisle,
            "bay": self.bay,
            "level": self.level,
            "zone": self.zone,
            "temp": self.temp,
            "minutes": self.minutes,
            "topoff": self.topoff,
        }


@dataclass
class SlotState:
    location: Location
    occupied_pallets: int
    occupied_weight_kg: float
    sku: str
    assigned: list[str]

    @property
    def remaining_pallets(self) -> int:
        return self.location.max_pallets - self.occupied_pallets

    def as_dict(self) -> dict[str, object]:
        loc = self.location
        return {
            **loc.as_dict(),
            "occupied_pallets": self.occupied_pallets,
            "occupied_weight_kg": round(self.occupied_weight_kg, 3),
            "sku": self.sku,
            "remaining_pallets": self.remaining_pallets,
            "assigned": list(self.assigned),
        }


@dataclass
class SteerResult:
    policy: Policy
    strategy: str
    labor_cap_min: int
    labor_used_min: int
    puts: list[Put]
    leftover: list[dict[str, object]]
    locations: list[dict[str, object]]
    asked_pallets: int
    placed_pallets: int

    @property
    def all_clear(self) -> bool:
        return not self.leftover

    @property
    def put_count(self) -> int:
        return len(self.puts)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def fill_rate(self) -> float:
        if self.asked_pallets <= 0:
            return 0.0
        return self.placed_pallets / self.asked_pallets

    @property
    def labor_utilization(self) -> float:
        if self.labor_cap_min <= 0:
            return 0.0
        return self.labor_used_min / self.labor_cap_min

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy.as_dict(),
            "strategy": self.strategy,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "puts": [item.as_dict() for item in self.puts],
            "leftover": list(self.leftover),
            "locations": list(self.locations),
            "asked_pallets": self.asked_pallets,
            "placed_pallets": self.placed_pallets,
            "put_count": self.put_count,
            "leftover_count": self.leftover_count,
            "fill_rate": self.fill_rate,
            "all_clear": self.all_clear,
        }


def _sort_inbound(pallets: list[Pallet], strategy: str) -> list[Pallet]:
    def key(pallet: Pallet) -> tuple:
        if strategy == "heavy":
            return (-pallet.weight_kg, pallet.priority, pallet.id)
        if strategy == "tall":
            return (-pallet.height_mm, pallet.priority, pallet.id)
        if strategy == "fifo":
            return (pallet.id,)
        return (pallet.priority, -pallet.weight_kg, pallet.id)

    return sorted(pallets, key=key)


def _reject_reason(location: Location, pallet: Pallet, slot: SlotState, policy: Policy) -> str | None:
    if location.blocked:
        return "blocked"
    if policy.location_type and location.type != policy.location_type:
        return "type"
    if location.temp != pallet.temp:
        return "temp"
    if pallet.height_mm > location.max_height_mm:
        return "height"
    if slot.occupied_pallets + pallet.pallets > location.max_pallets:
        return "no-space"
    if slot.occupied_weight_kg + pallet.weight_kg > location.max_weight_kg + 1e-9:
        return "weight"
    if slot.sku and slot.sku != pallet.sku and not policy.allow_mix_sku:
        return "mix-sku"
    return None


def _score(pallet: Pallet, slot: SlotState, policy: Policy) -> tuple:
    loc = slot.location
    score = 0.0
    topoff = bool(slot.sku and slot.sku == pallet.sku)
    if policy.prefer_topoff and topoff:
        score -= 1000
    if loc.zone != pallet.velocity:
        score += 80
    if pallet.home_aisle is not None:
        score += abs(loc.aisle - pallet.home_aisle) * 10
    else:
        score += loc.aisle * 4
    leftover_slots = loc.max_pallets - slot.occupied_pallets - pallet.pallets
    score += leftover_slots * 3
    score += loc.level * 10
    score += loc.bay * 0.1
    return (score, loc.id)


def _travel_minutes(policy: Policy, aisle: int, previous_aisle: int) -> int:
    return policy.minutes_per_put + policy.aisle_change_min * abs(aisle - previous_aisle)


def _leftover_reason(pallet: Pallet, slots: list[SlotState], policy: Policy) -> str:
    reasons = {
        _reject_reason(slot.location, pallet, slot, policy)
        for slot in slots
    }
    reasons.discard(None)
    for reason in REASON_ORDER:
        if reason in reasons:
            return reason
    return "no-space"


def _leftover_row(pallet: Pallet, reason: str) -> dict[str, object]:
    return {
        "id": pallet.id,
        "sku": pallet.sku,
        "qty": pallet.qty,
        "pallets": pallet.pallets,
        "height_mm": pallet.height_mm,
        "weight_kg": pallet.weight_kg,
        "temp": pallet.temp,
        "reason": reason,
    }


def steer(wave: Wave) -> SteerResult:
    wave.validate()
    slots = [
        SlotState(
            location=location,
            occupied_pallets=location.occupied_pallets,
            occupied_weight_kg=location.occupied_weight_kg,
            sku=location.sku,
            assigned=[],
        )
        for location in wave.locations
    ]
    labor_cap = wave.labor_cap()
    labor_used = 0
    previous_aisle = 0
    puts: list[Put] = []
    leftover: list[dict[str, object]] = []
    placed = 0
    asked = sum(pallet.pallets for pallet in wave.inbound)

    for pallet in _sort_inbound(wave.inbound, wave.strategy):
        eligible: list[SlotState] = []
        for slot in slots:
            if _reject_reason(slot.location, pallet, slot, wave.policy) is None:
                eligible.append(slot)
        if not eligible:
            leftover.append(_leftover_row(pallet, _leftover_reason(pallet, slots, wave.policy)))
            continue
        chosen = min(eligible, key=lambda slot: _score(pallet, slot, wave.policy))
        minutes = _travel_minutes(wave.policy, chosen.location.aisle, previous_aisle)
        if labor_used + minutes > labor_cap:
            leftover.append(_leftover_row(pallet, "labor-cap"))
            continue
        topoff = bool(chosen.sku and chosen.sku == pallet.sku)
        chosen.occupied_pallets += pallet.pallets
        chosen.occupied_weight_kg += pallet.weight_kg
        if not chosen.sku or chosen.sku == pallet.sku:
            chosen.sku = pallet.sku
        else:
            chosen.sku = "MIXED"
        chosen.assigned.append(pallet.id)
        previous_aisle = chosen.location.aisle
        labor_used += minutes
        placed += pallet.pallets
        loc = chosen.location
        puts.append(
            Put(
                pallet_id=pallet.id,
                sku=pallet.sku,
                location_id=loc.id,
                aisle=loc.aisle,
                bay=loc.bay,
                level=loc.level,
                zone=loc.zone,
                temp=loc.temp,
                minutes=minutes,
                topoff=topoff,
            )
        )

    return SteerResult(
        policy=wave.policy,
        strategy=wave.strategy,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        puts=puts,
        leftover=leftover,
        locations=[slot.as_dict() for slot in slots],
        asked_pallets=asked,
        placed_pallets=placed,
    )
