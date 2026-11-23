"""Greedy bay assignment that honours mixing codes."""

from __future__ import annotations

from dataclasses import dataclass

from .matrix import CODE_RANK, MixCode, lookup, mix, worse
from .model import Lot, Pad, Shipment


@dataclass(frozen=True)
class Placement:
    lot: str
    un: str
    clazz: str
    description: str
    kg: float
    limited_qty: bool
    foodstuff: bool
    bay: int
    compartment: int

    def as_dict(self) -> dict[str, object]:
        return {
            "lot": self.lot,
            "un": self.un,
            "class": self.clazz,
            "description": self.description,
            "kg": self.kg,
            "limited_qty": self.limited_qty,
            "foodstuff": self.foodstuff,
            "bay": self.bay,
            "compartment": self.compartment,
        }


@dataclass(frozen=True)
class PairCheck:
    lot_a: str
    lot_b: str
    class_a: str
    class_b: str
    code: str
    raw_code: str
    eased: bool
    share: str
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "lot_a": self.lot_a,
            "lot_b": self.lot_b,
            "class_a": self.class_a,
            "class_b": self.class_b,
            "code": self.code,
            "raw_code": self.raw_code,
            "eased": self.eased,
            "share": self.share,
            "note": self.note,
        }


@dataclass
class PlanResult:
    pad: Pad
    allow_limited_qty_ease: bool
    placements: list[Placement]
    leftover: list[dict[str, object]]
    pairs: list[PairCheck]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def placed_kg(self) -> float:
        return sum(item.kg for item in self.placements)

    @property
    def leftover_kg(self) -> float:
        return sum(float(item["kg"]) for item in self.leftover)

    @property
    def worst_code(self) -> str:
        if not self.pairs:
            return "C"
        on_pad = [pair for pair in self.pairs if pair.share == "same_pad"]
        pool = on_pad or self.pairs
        return max((pair.code for pair in pool), key=lambda code: CODE_RANK[code])

    def as_dict(self) -> dict[str, object]:
        return {
            "pad": {
                "id": self.pad.id,
                "bays": self.pad.bays,
                "compartments": self.pad.compartments,
                "away_bays": self.pad.away_bays,
                "empty_as_partition": self.pad.empty_as_partition,
            },
            "allow_limited_qty_ease": self.allow_limited_qty_ease,
            "all_fit": self.all_fit,
            "placed_count": len(self.placements),
            "leftover_count": len(self.leftover),
            "placed_kg": self.placed_kg,
            "leftover_kg": self.leftover_kg,
            "worst_code": self.worst_code,
            "bays": _bay_map(self),
            "placements": [item.as_dict() for item in self.placements],
            "leftover": self.leftover,
            "pairs": [item.as_dict() for item in self.pairs],
        }


def lot_mix(a: Lot, b: Lot, allow_lq: bool) -> MixCode:
    both_limited = allow_lq and a.limited_qty and b.limited_qty
    result = mix(a.clazz, b.clazz, both_limited)
    code = result.code
    raw = result.raw
    if a.foodstuff and b.clazz != "FOOD":
        extra = lookup("FOOD", b.clazz)
        raw = worse(raw, extra)
        code = worse(code, extra)
    if b.foodstuff and a.clazz != "FOOD":
        extra = lookup(a.clazz, "FOOD")
        raw = worse(raw, extra)
        code = worse(code, extra)
    return MixCode(raw=raw, code=code, eased=code != raw)


def plan(shipment: Shipment) -> PlanResult:
    pad = shipment.pad
    allow = shipment.allow_limited_qty_ease
    ordered = sorted(shipment.lots, key=lambda lot: (-lot.kg, lot.lot))
    placed: list[Placement] = []
    leftover: list[dict[str, object]] = []

    for lot in ordered:
        bay = _first_bay(lot, placed, pad, allow)
        if bay is None:
            leftover.append(_lot_dict(lot, "no bay honours mixing codes"))
            continue
        placed.append(
            Placement(
                lot=lot.lot,
                un=lot.un,
                clazz=lot.clazz,
                description=lot.description,
                kg=lot.kg,
                limited_qty=lot.limited_qty,
                foodstuff=lot.foodstuff,
                bay=bay,
                compartment=pad.compartment_of(bay),
            )
        )

    placed.sort(key=lambda item: item.bay)
    leftover.sort(key=lambda item: str(item["lot"]))
    by_id = {lot.lot: lot for lot in shipment.lots}
    pairs = _pairs(shipment.lots, placed, leftover, allow)
    # Keep leftover reasons stable even if a later pair is X.
    for item in leftover:
        lot = by_id[str(item["lot"])]
        clashes = [
            pair.lot_b if pair.lot_a == lot.lot else pair.lot_a
            for pair in pairs
            if pair.code == "X" and lot.lot in (pair.lot_a, pair.lot_b)
        ]
        if clashes:
            item["reason"] = "forbidden with " + ", ".join(clashes)
    return PlanResult(
        pad=pad,
        allow_limited_qty_ease=allow,
        placements=placed,
        leftover=leftover,
        pairs=pairs,
    )


def _first_bay(lot: Lot, placed: list[Placement], pad: Pad, allow: bool) -> int | None:
    for bay in range(pad.bays):
        if _occupied(bay, placed):
            continue
        if _bay_ok(lot, bay, placed, pad, allow):
            return bay
    return None


def _occupied(bay: int, placed: list[Placement]) -> bool:
    return any(item.bay == bay for item in placed)


def _bay_ok(lot: Lot, bay: int, placed: list[Placement], pad: Pad, allow: bool) -> bool:
    for other in placed:
        code = lot_mix(lot, _as_lot(other), allow).code
        if not _pair_ok(code, bay, other.bay, pad):
            return False
    for left, right in _separated_pairs(placed, pad, allow):
        lo, hi = sorted((left.bay, right.bay))
        if lo < bay < hi and left.compartment == right.compartment:
            return False
    return True


def _pair_ok(code: str, bay_a: int, bay_b: int, pad: Pad) -> bool:
    dist = abs(bay_a - bay_b)
    same_comp = pad.compartment_of(bay_a) == pad.compartment_of(bay_b)
    if code == "C":
        return True
    if code == "X":
        return False
    if code == "A":
        return dist >= pad.away_bays + 1
    if code == "S":
        if pad.compartments >= 2 and not same_comp:
            return True
        return pad.empty_as_partition and dist >= 2
    return False


def _separated_pairs(
    placed: list[Placement], pad: Pad, allow: bool
) -> list[tuple[Placement, Placement]]:
    pairs: list[tuple[Placement, Placement]] = []
    for i, left in enumerate(placed):
        for right in placed[i + 1 :]:
            if lot_mix(_as_lot(left), _as_lot(right), allow).code != "S":
                continue
            if pad.compartments >= 2 and left.compartment != right.compartment:
                continue
            pairs.append((left, right))
    return pairs


def _as_lot(item: Placement) -> Lot:
    return Lot(
        lot=item.lot,
        clazz=item.clazz,
        kg=item.kg,
        un=item.un,
        description=item.description,
        limited_qty=item.limited_qty,
        foodstuff=item.foodstuff,
    )


def _lot_dict(lot: Lot, reason: str) -> dict[str, object]:
    return {
        "lot": lot.lot,
        "un": lot.un,
        "class": lot.clazz,
        "description": lot.description,
        "kg": lot.kg,
        "limited_qty": lot.limited_qty,
        "foodstuff": lot.foodstuff,
        "reason": reason,
    }


def _pairs(
    lots: list[Lot],
    placed: list[Placement],
    leftover: list[dict[str, object]],
    allow: bool,
) -> list[PairCheck]:
    on_pad = {item.lot for item in placed}
    left_ids = {str(item["lot"]) for item in leftover}
    out: list[PairCheck] = []
    for i, a in enumerate(lots):
        for b in lots[i + 1 :]:
            result = lot_mix(a, b, allow)
            share = "same_pad" if a.lot in on_pad and b.lot in on_pad else "split"
            if share == "split":
                note = "not on the same pad"
            else:
                note = _share_note(result.code)
            if a.lot in left_ids or b.lot in left_ids:
                share = "split"
            out.append(
                PairCheck(
                    lot_a=a.lot,
                    lot_b=b.lot,
                    class_a=a.clazz,
                    class_b=b.clazz,
                    code=result.code,
                    raw_code=result.raw,
                    eased=result.eased,
                    share=share,
                    note=note,
                )
            )
    out.sort(key=lambda item: (-CODE_RANK[item.code], item.lot_a, item.lot_b))
    return out


def _share_note(code: str) -> str:
    return {
        "C": "adjacent OK",
        "A": "keep empty bays between",
        "S": "partition required",
        "X": "cannot share this pad",
    }[code]


def _bay_map(result: PlanResult) -> list[dict[str, object]]:
    by_bay = {item.bay: item for item in result.placements}
    rows: list[dict[str, object]] = []
    for bay in range(result.pad.bays):
        item = by_bay.get(bay)
        rows.append(
            {
                "bay": bay,
                "compartment": result.pad.compartment_of(bay),
                "lot": None if item is None else item.as_dict(),
            }
        )
    return rows
