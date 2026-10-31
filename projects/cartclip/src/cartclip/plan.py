"""Greedy pick-cart clusterer: one tote per order, aisle-overlap first."""

from __future__ import annotations

from dataclasses import dataclass, field

from .floor import Cart, Warehouse
from .model import Order, Wave


@dataclass
class OpenCart:
    index: int
    orders: list[Order] = field(default_factory=list)
    minutes: int = 0

    @property
    def id(self) -> str:
        return f"C{self.index}"

    def aisle_set(self) -> set[str]:
        aisles: set[str] = set()
        for order in self.orders:
            aisles |= order.aisle_set()
        return aisles

    @property
    def weight_kg(self) -> float:
        return sum(order.weight_kg for order in self.orders)

    @property
    def volume_mm3(self) -> int:
        return sum(order.volume_mm3 for order in self.orders)


@dataclass(frozen=True)
class Placement:
    cart_id: str
    slot: int
    order_id: str
    priority: int
    temp: str
    aisles: list[str]
    line_count: int
    piece_count: int
    weight_kg: float
    volume_l: float
    minutes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "cart_id": self.cart_id,
            "slot": self.slot,
            "order_id": self.order_id,
            "priority": self.priority,
            "temp": self.temp,
            "aisles": list(self.aisles),
            "line_count": self.line_count,
            "piece_count": self.piece_count,
            "weight_kg": round(self.weight_kg, 3),
            "volume_l": round(self.volume_l, 4),
            "minutes": self.minutes,
        }


@dataclass
class PlanResult:
    warehouse: Warehouse
    cart: Cart
    strategy: str
    labor_cap_min: int
    labor_used_min: int
    placements: list[Placement]
    leftover: list[dict[str, object]]
    carts: list[dict[str, object]]
    aisle_map: list[dict[str, object]]
    picks: list[dict[str, object]]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def cart_count(self) -> int:
        return len(self.carts)

    @property
    def clipped_count(self) -> int:
        return len(self.placements)

    @property
    def leftover_count(self) -> int:
        return len(self.leftover)

    @property
    def tote_utilization(self) -> float:
        capacity = self.cart_count * self.cart.tote_slots
        return self.clipped_count / capacity if capacity else 0.0

    @property
    def labor_utilization(self) -> float:
        return self.labor_used_min / self.labor_cap_min if self.labor_cap_min else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "warehouse": self.warehouse.as_dict(),
            "cart": self.cart.as_dict(),
            "strategy": self.strategy,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "cart_count": self.cart_count,
            "clipped_count": self.clipped_count,
            "leftover_count": self.leftover_count,
            "tote_utilization": round(self.tote_utilization, 4),
            "all_fit": self.all_fit,
            "placements": [item.as_dict() for item in self.placements],
            "leftover": list(self.leftover),
            "carts": list(self.carts),
            "aisle_map": list(self.aisle_map),
            "picks": list(self.picks),
        }


def plan_wave(wave: Wave) -> PlanResult:
    wave.validate()
    labor_cap = wave.labor_cap()
    labor_used = 0
    open_carts: list[OpenCart] = []
    leftover: list[dict[str, object]] = []

    for order in _sort_orders(wave.orders, wave.warehouse, wave.strategy):
        hard = _hard_reason(order, wave.cart, wave.warehouse)
        if hard:
            leftover.append(_leftover_row(order, hard))
            continue

        minutes = _order_minutes(order, wave.cart)
        host = _best_cart(order, open_carts, wave)
        if host is not None:
            if labor_used + minutes > labor_cap:
                leftover.append(_leftover_row(order, "labor-cap"))
                continue
            host.orders.append(order)
            host.minutes += minutes
            labor_used += minutes
            continue

        open_cost = wave.cart.minutes_per_cart + minutes
        if labor_used + open_cost > labor_cap:
            leftover.append(_leftover_row(order, "labor-cap"))
            continue
        opened = OpenCart(index=len(open_carts) + 1, orders=[order], minutes=open_cost)
        open_carts.append(opened)
        labor_used += open_cost

    placements = _placements(open_carts, wave.cart)
    picks = _picks(open_carts)
    return PlanResult(
        warehouse=wave.warehouse,
        cart=wave.cart,
        strategy=wave.strategy,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        placements=placements,
        leftover=leftover,
        carts=_cart_rows(open_carts, wave),
        aisle_map=_aisle_map(wave.warehouse, open_carts),
        picks=picks,
    )


def _order_minutes(order: Order, cart: Cart) -> int:
    return cart.minutes_per_order + cart.minutes_per_line * order.line_count


def _hard_reason(order: Order, cart: Cart, warehouse: Warehouse) -> str | None:
    if not cart.accepts_temp(order.temp):
        return "temp"
    if order.weight_kg > cart.max_weight_kg + 1e-9:
        return "too-heavy"
    if order.volume_mm3 > cart.max_volume_mm3:
        return "too-cube"
    if order.aisle_span(warehouse) > cart.max_aisle_span:
        return "aisle-span"
    return None


def _can_join(host: OpenCart, order: Order, wave: Wave) -> bool:
    spec = wave.cart
    if len(host.orders) >= spec.tote_slots:
        return False
    if host.weight_kg + order.weight_kg > spec.max_weight_kg + 1e-9:
        return False
    if host.volume_mm3 + order.volume_mm3 > spec.max_volume_mm3:
        return False
    if not spec.accepts_temp(order.temp):
        return False
    combined = host.aisle_set() | order.aisle_set()
    if wave.warehouse.span(combined) > spec.max_aisle_span:
        return False
    if wave.strategy == "aisle" and host.orders and not (host.aisle_set() & order.aisle_set()):
        return False
    return True


def _best_cart(order: Order, hosts: list[OpenCart], wave: Wave) -> OpenCart | None:
    eligible = [host for host in hosts if _can_join(host, order, wave)]
    if not eligible:
        return None

    def score(host: OpenCart) -> tuple[float, float, int]:
        union = host.aisle_set() | order.aisle_set()
        overlap = host.aisle_set() & order.aisle_set()
        jaccard = (len(overlap) / len(union)) if union else 0.0
        fill = len(host.orders) / wave.cart.tote_slots
        return (-jaccard, -fill, host.index)

    return min(eligible, key=score)


def _sort_orders(orders: list[Order], warehouse: Warehouse, strategy: str) -> list[Order]:
    if strategy == "compact":
        return sorted(orders, key=lambda item: (item.volume_mm3, item.piece_count, item.id))
    if strategy == "aisle":
        return sorted(orders, key=lambda item: (*item.primary_aisle(warehouse), item.id))
    if strategy == "priority":
        return sorted(orders, key=lambda item: (item.priority, item.id))
    return sorted(orders, key=lambda item: (item.priority, -item.line_count, -item.volume_mm3, item.id))


def _leftover_row(order: Order, reason: str) -> dict[str, object]:
    return {
        "id": order.id,
        "priority": order.priority,
        "temp": order.temp,
        "aisles": sorted(order.aisle_set()),
        "line_count": order.line_count,
        "piece_count": order.piece_count,
        "weight_kg": round(order.weight_kg, 3),
        "volume_l": round(order.volume_l, 4),
        "reason": reason,
    }


def _placements(hosts: list[OpenCart], cart: Cart) -> list[Placement]:
    placed: list[Placement] = []
    for host in hosts:
        for slot, order in enumerate(host.orders, start=1):
            placed.append(
                Placement(
                    cart_id=host.id,
                    slot=slot,
                    order_id=order.id,
                    priority=order.priority,
                    temp=order.temp,
                    aisles=sorted(order.aisle_set()),
                    line_count=order.line_count,
                    piece_count=order.piece_count,
                    weight_kg=order.weight_kg,
                    volume_l=order.volume_l,
                    minutes=_order_minutes(order, cart),
                )
            )
    return placed


def _cart_rows(hosts: list[OpenCart], wave: Wave) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for host in hosts:
        totes: list[dict[str, object]] = []
        for slot in range(1, wave.cart.tote_slots + 1):
            if slot <= len(host.orders):
                order = host.orders[slot - 1]
                totes.append(
                    {
                        "slot": slot,
                        "order_id": order.id,
                        "priority": order.priority,
                        "temp": order.temp,
                        "aisles": sorted(order.aisle_set()),
                        "weight_kg": round(order.weight_kg, 3),
                        "volume_l": round(order.volume_l, 4),
                    }
                )
            else:
                totes.append({"slot": slot, "order_id": None})
        rows.append(
            {
                "id": host.id,
                "used_slots": len(host.orders),
                "tote_slots": wave.cart.tote_slots,
                "weight_kg": round(host.weight_kg, 3),
                "volume_l": round(host.volume_mm3 / 1_000_000, 4),
                "aisles": sorted(host.aisle_set(), key=wave.warehouse.aisle_index),
                "span": wave.warehouse.span(host.aisle_set()),
                "minutes": host.minutes,
                "totes": totes,
            }
        )
    return rows


def _picks(hosts: list[OpenCart]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for host in hosts:
        for order in host.orders:
            for line in order.lines:
                rows.append(
                    {
                        "cart_id": host.id,
                        "order_id": order.id,
                        "sku": line.sku,
                        "aisle": line.aisle,
                        "bay": line.bay,
                        "quantity": line.quantity,
                    }
                )
    return rows


def _aisle_map(warehouse: Warehouse, hosts: list[OpenCart]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for aisle in warehouse.aisles:
        carts: list[str] = []
        orders: set[str] = set()
        picks = 0
        bays = [0] * warehouse.bays
        for host in hosts:
            hits = False
            for order in host.orders:
                for line in order.lines:
                    if line.aisle != aisle:
                        continue
                    hits = True
                    orders.add(order.id)
                    picks += line.quantity
                    bays[line.bay - 1] += line.quantity
            if hits:
                carts.append(host.id)
        rows.append(
            {
                "aisle": aisle,
                "index": warehouse.aisle_index(aisle),
                "picks": picks,
                "orders": len(orders),
                "carts": carts,
                "bays": bays,
            }
        )
    return rows
