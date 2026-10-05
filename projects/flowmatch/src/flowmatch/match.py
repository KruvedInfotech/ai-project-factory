"""Match inbound receipts to outbound orders through live doors or staging."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import FlowPlan, Order, Receipt
from .yards import Lane, Yard, clock_to_min, min_to_clock


@dataclass(frozen=True)
class Allocation:
    receipt_id: str
    order_id: str
    sku: str
    pallets: int
    mode: str
    lane_id: str | None
    ready: str
    labor_min: int
    door_in: str
    door_out: str

    def as_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "order_id": self.order_id,
            "sku": self.sku,
            "pallets": self.pallets,
            "mode": self.mode,
            "lane_id": self.lane_id,
            "ready": self.ready,
            "labor_min": self.labor_min,
            "door_in": self.door_in,
            "door_out": self.door_out,
        }


@dataclass
class FlowResult:
    yard: Yard
    strategy: str
    allocations: list[Allocation] = field(default_factory=list)
    leftover_in: list[dict[str, object]] = field(default_factory=list)
    leftover_out: list[dict[str, object]] = field(default_factory=list)
    lane_fill: dict[str, int] = field(default_factory=dict)

    @property
    def matched_pallets(self) -> int:
        return sum(item.pallets for item in self.allocations)

    @property
    def live_pallets(self) -> int:
        return sum(item.pallets for item in self.allocations if item.mode == "live")

    @property
    def stage_pallets(self) -> int:
        return sum(item.pallets for item in self.allocations if item.mode == "stage")

    @property
    def inbound_pallets(self) -> int:
        used = self.matched_pallets + sum(int(item["pallets"]) for item in self.leftover_in)
        return used

    @property
    def outbound_pallets(self) -> int:
        return self.matched_pallets + sum(int(item["pallets"]) for item in self.leftover_out)

    @property
    def labor_min(self) -> int:
        return sum(item.labor_min for item in self.allocations)

    @property
    def live_count(self) -> int:
        return sum(1 for item in self.allocations if item.mode == "live")

    @property
    def stage_count(self) -> int:
        return sum(1 for item in self.allocations if item.mode == "stage")

    @property
    def leftover_count(self) -> int:
        return len(self.leftover_in) + len(self.leftover_out)

    @property
    def all_clear(self) -> bool:
        return not self.leftover_in and not self.leftover_out

    @property
    def fill_rate(self) -> float:
        if self.outbound_pallets == 0:
            return 0.0
        return self.matched_pallets / self.outbound_pallets

    def as_dict(self) -> dict[str, object]:
        return {
            "yard": self.yard.as_dict(),
            "strategy": self.strategy,
            "allocations": [item.as_dict() for item in self.allocations],
            "leftover_in": self.leftover_in,
            "leftover_out": self.leftover_out,
            "lane_fill": self.lane_fill,
            "matched_pallets": self.matched_pallets,
            "live_pallets": self.live_pallets,
            "stage_pallets": self.stage_pallets,
            "inbound_pallets": self.inbound_pallets,
            "outbound_pallets": self.outbound_pallets,
            "labor_min": self.labor_min,
            "live_count": self.live_count,
            "stage_count": self.stage_count,
            "leftover_count": self.leftover_count,
            "fill_rate": self.fill_rate,
            "all_clear": self.all_clear,
        }


def available_min(receipt: Receipt, yard: Yard) -> int:
    eta = clock_to_min(receipt.eta)
    if eta < yard.open_min:
        return yard.open_min
    return eta


def live_ready(receipt: Receipt, yard: Yard) -> int:
    return available_min(receipt, yard) + yard.unload_min + yard.load_min


def stage_ready(receipt: Receipt, yard: Yard) -> int:
    return available_min(receipt, yard) + yard.unload_min + yard.stage_min + yard.load_min


def sort_orders(plan: FlowPlan) -> list[Order]:
    orders = list(plan.orders)
    if plan.strategy == "lane":
        orders.sort(key=lambda order: (order.door, order.priority, clock_to_min(order.cutoff), order.id))
        return orders
    if plan.strategy == "live":
        def live_key(order: Order) -> tuple[int, int, int, str]:
            same_door = any(
                receipt.sku == order.sku
                and receipt.temp == order.temp
                and receipt.door == order.door
                for receipt in plan.receipts
            )
            return (0 if same_door else 1, order.priority, clock_to_min(order.cutoff), order.id)

        orders.sort(key=live_key)
        return orders
    orders.sort(key=lambda order: (order.priority, clock_to_min(order.cutoff), order.id))
    return orders


def choose_mode(
    strategy: str,
    receipt: Receipt,
    order: Order,
    can_live: bool,
    can_stage: bool,
) -> str | None:
    if strategy == "lane":
        if can_stage:
            return "stage"
        return None
    if strategy == "live":
        if can_live:
            return "live"
        if can_stage:
            return "stage"
        return None
    if strategy == "cutoff":
        if can_live:
            return "live"
        if can_stage:
            return "stage"
        return None
    if can_live and receipt.door == order.door:
        return "live"
    if can_stage:
        return "stage"
    if can_live:
        return "live"
    return None


def pick_lane(
    order: Order,
    yard: Yard,
    fill: dict[str, int],
    strategy: str,
    pallets: int,
) -> Lane | None:
    candidates = [
        lane
        for lane in yard.lanes
        if lane.temp == order.temp and fill[lane.id] < lane.max_pallets
    ]
    if not candidates:
        return None
    need = max(1, pallets)

    def key(lane: Lane) -> tuple[int, int, int, str]:
        remaining = lane.max_pallets - fill[lane.id]
        door_rank = 0 if lane.door == order.door else 1
        if strategy == "lane":
            pack_rank = 0 if fill[lane.id] else 1
            return (door_rank, pack_rank, -fill[lane.id], lane.id)
        fit_rank = 0 if remaining >= need else 1
        return (door_rank, fit_rank, fill[lane.id], lane.id)

    candidates.sort(key=key)
    return candidates[0]


def _in_hours(ready: int, cutoff: int, yard: Yard) -> bool:
    return ready <= cutoff and ready <= yard.close_min


def pick_receipt(
    order: Order,
    plan: FlowPlan,
    remaining_in: dict[str, int],
    remaining_out: int,
    fill: dict[str, int],
) -> tuple[Receipt, str, Lane | None, int, int] | None:
    options: list[tuple[Receipt, str, Lane | None, int, int, int]] = []
    cutoff = clock_to_min(order.cutoff)
    for receipt in plan.receipts:
        if remaining_in[receipt.id] <= 0:
            continue
        if receipt.sku != order.sku or receipt.temp != order.temp:
            continue
        if available_min(receipt, plan.yard) >= plan.yard.close_min:
            continue
        live_ok = _in_hours(live_ready(receipt, plan.yard), cutoff, plan.yard)
        lane = pick_lane(order, plan.yard, fill, plan.strategy, remaining_out)
        stage_ok = lane is not None and _in_hours(stage_ready(receipt, plan.yard), cutoff, plan.yard)
        mode = choose_mode(plan.strategy, receipt, order, live_ok, stage_ok)
        if mode is None:
            continue
        if mode == "live":
            qty = min(remaining_in[receipt.id], remaining_out)
            options.append(
                (receipt, "live", None, qty, live_ready(receipt, plan.yard), available_min(receipt, plan.yard))
            )
            continue
        assert lane is not None
        room = lane.max_pallets - fill[lane.id]
        qty = min(remaining_in[receipt.id], remaining_out, room)
        if qty < 1:
            continue
        options.append(
            (receipt, "stage", lane, qty, stage_ready(receipt, plan.yard), available_min(receipt, plan.yard))
        )
    if not options:
        return None
    options.sort(key=lambda item: (item[5], item[0].id))
    receipt, mode, lane, qty, ready, _avail = options[0]
    return receipt, mode, lane, qty, ready


def classify_out_fail(
    order: Order,
    plan: FlowPlan,
    remaining_in: dict[str, int],
    fill: dict[str, int],
) -> str:
    same_sku = [receipt for receipt in plan.receipts if receipt.sku == order.sku]
    if not same_sku or all(remaining_in[receipt.id] <= 0 for receipt in same_sku):
        return "short"
    temp_ok = [receipt for receipt in same_sku if receipt.temp == order.temp and remaining_in[receipt.id] > 0]
    if not temp_ok:
        return "temp"
    cutoff = clock_to_min(order.cutoff)
    on_time = [
        receipt
        for receipt in temp_ok
        if _in_hours(live_ready(receipt, plan.yard), cutoff, plan.yard)
        or _in_hours(stage_ready(receipt, plan.yard), cutoff, plan.yard)
    ]
    if not on_time:
        if all(available_min(receipt, plan.yard) >= plan.yard.close_min for receipt in temp_ok):
            return "closed"
        return "late"
    if pick_lane(order, plan.yard, fill, plan.strategy, 1) is None:
        live_possible = any(_in_hours(live_ready(receipt, plan.yard), cutoff, plan.yard) for receipt in on_time)
        if not live_possible:
            return "no-lane"
        if plan.strategy == "lane":
            return "no-lane"
    return "short"


def classify_inbound(
    receipt: Receipt,
    leftover: int,
    plan: FlowPlan,
    allocated_skus: set[str],
) -> str:
    if leftover <= 0:
        return "ok"
    if available_min(receipt, plan.yard) >= plan.yard.close_min:
        return "closed"
    matching = [order for order in plan.orders if order.sku == receipt.sku and order.temp == receipt.temp]
    if not matching:
        return "no-demand"
    if receipt.sku in allocated_skus:
        return "no-demand"
    cutoff_ok = any(
        _in_hours(live_ready(receipt, plan.yard), clock_to_min(order.cutoff), plan.yard)
        or _in_hours(stage_ready(receipt, plan.yard), clock_to_min(order.cutoff), plan.yard)
        for order in matching
    )
    if not cutoff_ok:
        return "late"
    return "no-demand"


def labor_cost(yard: Yard, prev_key: str | None, next_key: str) -> int:
    extra = 0 if prev_key is None or prev_key == next_key else yard.lane_change_min
    return yard.minutes_per_match + extra


def match(plan: FlowPlan) -> FlowResult:
    plan.validate()
    yard = plan.yard
    remaining_in = {receipt.id: receipt.pallets for receipt in plan.receipts}
    remaining_out = {order.id: order.pallets for order in plan.orders}
    fill = {lane.id: 0 for lane in yard.lanes}
    allocations: list[Allocation] = []
    leftover_out: list[dict[str, object]] = []
    labor = 0
    prev_key: str | None = None

    for order in sort_orders(plan):
        while remaining_out[order.id] > 0:
            if len(allocations) >= yard.max_matches:
                leftover_out.append(
                    {
                        "id": order.id,
                        "sku": order.sku,
                        "pallets": remaining_out[order.id],
                        "reason": "capped",
                    }
                )
                remaining_out[order.id] = 0
                break
            picked = pick_receipt(order, plan, remaining_in, remaining_out[order.id], fill)
            if picked is None:
                leftover_out.append(
                    {
                        "id": order.id,
                        "sku": order.sku,
                        "pallets": remaining_out[order.id],
                        "reason": classify_out_fail(order, plan, remaining_in, fill),
                    }
                )
                remaining_out[order.id] = 0
                break
            receipt, mode, lane, qty, ready = picked
            next_key = lane.id if lane else f"live:{order.door}"
            cost = labor_cost(yard, prev_key, next_key)
            if labor + cost > yard.max_labor_min:
                leftover_out.append(
                    {
                        "id": order.id,
                        "sku": order.sku,
                        "pallets": remaining_out[order.id],
                        "reason": "capped",
                    }
                )
                remaining_out[order.id] = 0
                break
            allocations.append(
                Allocation(
                    receipt_id=receipt.id,
                    order_id=order.id,
                    sku=order.sku,
                    pallets=qty,
                    mode=mode,
                    lane_id=lane.id if lane else None,
                    ready=min_to_clock(ready),
                    labor_min=cost,
                    door_in=receipt.door,
                    door_out=order.door,
                )
            )
            remaining_in[receipt.id] -= qty
            remaining_out[order.id] -= qty
            if lane:
                fill[lane.id] += qty
            labor += cost
            prev_key = next_key

    allocated_skus = {item.sku for item in allocations}
    leftover_in: list[dict[str, object]] = []
    for receipt in plan.receipts:
        leftover = remaining_in[receipt.id]
        if leftover <= 0:
            continue
        leftover_in.append(
            {
                "id": receipt.id,
                "sku": receipt.sku,
                "pallets": leftover,
                "reason": classify_inbound(receipt, leftover, plan, allocated_skus),
            }
        )

    return FlowResult(
        yard=yard,
        strategy=plan.strategy,
        allocations=allocations,
        leftover_in=leftover_in,
        leftover_out=leftover_out,
        lane_fill=fill,
    )
