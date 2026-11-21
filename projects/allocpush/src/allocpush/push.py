"""DC-to-store push allocation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Book, Sku, Store, Wave
from .policies import GRADE_WEIGHT


@dataclass(frozen=True)
class StoreNeed:
    store_id: str
    name: str
    grade: str
    weight: int
    on_hand: int
    forecast: int
    min_face: int
    max_cap: int
    target: int
    need_units: int
    pack: int
    need_packs: int


@dataclass(frozen=True)
class StoreLine:
    store_id: str
    name: str
    grade: str
    on_hand: int
    forecast: int
    min_face: int
    max_cap: int
    target: int
    need_units: int
    need_packs: int
    push_packs: int
    push_units: int
    short_units: int
    fill_pct: float

    def as_dict(self) -> dict[str, object]:
        return {
            "store_id": self.store_id,
            "name": self.name,
            "grade": self.grade,
            "on_hand": self.on_hand,
            "forecast": self.forecast,
            "min_face": self.min_face,
            "max_cap": self.max_cap,
            "target": self.target,
            "need_units": self.need_units,
            "need_packs": self.need_packs,
            "push_packs": self.push_packs,
            "push_units": self.push_units,
            "short_units": self.short_units,
            "fill_pct": round(self.fill_pct, 4),
        }


@dataclass
class SkuPlan:
    sku: str
    description: str
    case_pack: int
    inner_pack: int
    pack: int
    dc_on_hand: int
    holdback_units: int
    available_units: int
    available_packs: int
    need_units: int
    need_packs: int
    push_units: int
    push_packs: int
    short_units: int
    dc_remaining: int
    fill_pct: float
    lines: list[StoreLine] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "description": self.description,
            "case_pack": self.case_pack,
            "inner_pack": self.inner_pack,
            "pack": self.pack,
            "dc_on_hand": self.dc_on_hand,
            "holdback_units": self.holdback_units,
            "available_units": self.available_units,
            "available_packs": self.available_packs,
            "need_units": self.need_units,
            "need_packs": self.need_packs,
            "push_units": self.push_units,
            "push_packs": self.push_packs,
            "short_units": self.short_units,
            "dc_remaining": self.dc_remaining,
            "fill_pct": round(self.fill_pct, 4),
            "lines": [line.as_dict() for line in self.lines],
        }


@dataclass
class PlanResult:
    wave: str
    dc: str
    policy: str
    holdback_pct: float
    break_case: bool
    sku_count: int
    store_count: int
    push_units: int
    short_units: int
    dc_remaining: int
    all_filled: bool
    skus: list[SkuPlan] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "wave": self.wave,
            "dc": self.dc,
            "policy": self.policy,
            "holdback_pct": self.holdback_pct,
            "break_case": self.break_case,
            "sku_count": self.sku_count,
            "store_count": self.store_count,
            "push_units": self.push_units,
            "short_units": self.short_units,
            "dc_remaining": self.dc_remaining,
            "all_filled": self.all_filled,
            "skus": [item.as_dict() for item in self.skus],
        }


def plan(wave: Wave) -> PlanResult:
    skus = [_allocate_sku(wave, sku) for sku in wave.skus]
    push_units = sum(item.push_units for item in skus)
    short_units = sum(item.short_units for item in skus)
    dc_remaining = sum(item.dc_remaining for item in skus)
    return PlanResult(
        wave=wave.wave,
        dc=wave.dc,
        policy=wave.policy,
        holdback_pct=wave.holdback_pct,
        break_case=wave.break_case,
        sku_count=len(wave.skus),
        store_count=len(wave.stores),
        push_units=push_units,
        short_units=short_units,
        dc_remaining=dc_remaining,
        all_filled=short_units == 0,
        skus=skus,
    )


def store_need(store: Store, book: Book, pack: int) -> StoreNeed:
    target = min(book.max_cap, max(book.min_face, book.forecast))
    need_units = max(0, target - book.on_hand)
    capacity_left = max(0, book.max_cap - book.on_hand)
    max_packs = capacity_left // pack
    if need_units <= 0 or max_packs <= 0:
        need_packs = 0
    else:
        wanted = (need_units + pack - 1) // pack
        need_packs = min(wanted, max_packs)
    return StoreNeed(
        store_id=store.store_id,
        name=store.name,
        grade=store.grade,
        weight=GRADE_WEIGHT[store.grade],
        on_hand=book.on_hand,
        forecast=book.forecast,
        min_face=book.min_face,
        max_cap=book.max_cap,
        target=target,
        need_units=need_units,
        pack=pack,
        need_packs=need_packs,
    )


def _allocate_sku(wave: Wave, sku: Sku) -> SkuPlan:
    pack = sku.pack_size(wave.break_case)
    holdback_units = int(sku.dc_on_hand * wave.holdback_pct // 100)
    available_units = max(0, sku.dc_on_hand - holdback_units)
    available_packs = available_units // pack
    needs: list[StoreNeed] = []
    for store in wave.stores:
        book = store.book_for(sku.sku)
        if book is None:
            continue
        needs.append(store_need(store, book, pack))

    alloc = _allocate_packs(wave.policy, needs, available_packs)
    lines: list[StoreLine] = []
    for need in needs:
        push_packs = alloc.get(need.store_id, 0)
        push_units = push_packs * pack
        short_units = max(0, need.need_units - push_units)
        fill_pct = 1.0 if need.need_units == 0 else push_units / need.need_units
        lines.append(
            StoreLine(
                store_id=need.store_id,
                name=need.name,
                grade=need.grade,
                on_hand=need.on_hand,
                forecast=need.forecast,
                min_face=need.min_face,
                max_cap=need.max_cap,
                target=need.target,
                need_units=need.need_units,
                need_packs=need.need_packs,
                push_packs=push_packs,
                push_units=push_units,
                short_units=short_units,
                fill_pct=min(fill_pct, 1.0),
            )
        )

    need_units = sum(item.need_units for item in lines)
    need_packs = sum(item.need_packs for item in lines)
    push_units = sum(item.push_units for item in lines)
    push_packs = sum(item.push_packs for item in lines)
    short_units = sum(item.short_units for item in lines)
    fill_pct = 1.0 if need_units == 0 else min(push_units / need_units, 1.0)
    return SkuPlan(
        sku=sku.sku,
        description=sku.description,
        case_pack=sku.case_pack,
        inner_pack=sku.inner_pack,
        pack=pack,
        dc_on_hand=sku.dc_on_hand,
        holdback_units=holdback_units,
        available_units=available_units,
        available_packs=available_packs,
        need_units=need_units,
        need_packs=need_packs,
        push_units=push_units,
        push_packs=push_packs,
        short_units=short_units,
        dc_remaining=sku.dc_on_hand - push_units,
        fill_pct=fill_pct,
        lines=lines,
    )


def _allocate_packs(policy: str, needs: list[StoreNeed], available_packs: int) -> dict[str, int]:
    if policy == "need_fill":
        key = lambda n: (-n.need_packs, -n.weight, n.store_id)
        return _greedy_fill(needs, available_packs, key)
    if policy == "grade_first":
        key = lambda n: (-n.weight, -n.need_packs, n.store_id)
        return _greedy_fill(needs, available_packs, key)
    return _fair_share(needs, available_packs)


def _greedy_fill(
    needs: list[StoreNeed],
    available_packs: int,
    key,
) -> dict[str, int]:
    alloc = {item.store_id: 0 for item in needs}
    left = max(0, available_packs)
    for item in sorted(needs, key=key):
        if left <= 0:
            break
        take = min(item.need_packs, left)
        alloc[item.store_id] = take
        left -= take
    return alloc


def _fair_share(needs: list[StoreNeed], available_packs: int) -> dict[str, int]:
    alloc = {item.store_id: 0 for item in needs}
    total_need = sum(item.need_packs for item in needs)
    give = min(max(0, available_packs), total_need)
    if give == 0:
        return alloc
    if give == total_need:
        return {item.store_id: item.need_packs for item in needs}

    weighted = {item.store_id: item.need_packs * item.weight for item in needs}
    total_w = sum(weighted.values())
    leftover = give
    remainders: dict[str, int] = {}
    for item in needs:
        if total_w <= 0:
            share = 0
            rem = 0
        else:
            share = min(item.need_packs, (give * weighted[item.store_id]) // total_w)
            rem = (give * weighted[item.store_id]) % total_w
        alloc[item.store_id] = share
        leftover -= share
        remainders[item.store_id] = rem

    order = sorted(
        needs,
        key=lambda item: (-remainders[item.store_id], -item.weight, item.store_id),
    )
    while leftover > 0:
        progressed = False
        for item in order:
            if leftover <= 0:
                break
            if alloc[item.store_id] < item.need_packs:
                alloc[item.store_id] += 1
                leftover -= 1
                progressed = True
        if not progressed:
            break
    return alloc
