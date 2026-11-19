"""Sample-size, carton draw, accept/reject, and switching advice."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .cards import accept_number, letter_for, reject_number, sample_size
from .model import Lot, Receipt


@dataclass(frozen=True)
class ClassPlan:
    name: str
    aql: float
    n: int
    ac: int
    re: int
    found: int | None
    verdict: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "aql": self.aql,
            "n": self.n,
            "ac": self.ac,
            "re": self.re,
            "found": self.found,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class LotPlan:
    sku: str
    description: str
    lot_size: int
    letter: str
    sample_size: int
    hundred_percent: bool
    draw: list[int]
    classes: list[ClassPlan]
    verdict: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "description": self.description,
            "lot_size": self.lot_size,
            "letter": self.letter,
            "sample_size": self.sample_size,
            "hundred_percent": self.hundred_percent,
            "draw": list(self.draw),
            "classes": [item.as_dict() for item in self.classes],
            "verdict": self.verdict,
        }


@dataclass
class PlanResult:
    receipt: str
    supplier: str
    dock: str
    level: str
    severity: str
    seed: str
    switching: str
    lots: list[LotPlan]
    all_accept: bool
    reject_count: int
    pending_count: int
    sample_total: int

    def as_dict(self) -> dict[str, object]:
        return {
            "receipt": self.receipt,
            "supplier": self.supplier,
            "dock": self.dock,
            "level": self.level,
            "severity": self.severity,
            "seed": self.seed,
            "switching": self.switching,
            "lots": [item.as_dict() for item in self.lots],
            "all_accept": self.all_accept,
            "reject_count": self.reject_count,
            "pending_count": self.pending_count,
            "sample_total": self.sample_total,
            "lot_count": len(self.lots),
        }


def plan(receipt: Receipt) -> PlanResult:
    lots = [_plan_lot(receipt, lot) for lot in receipt.lots]
    reject_count = sum(1 for item in lots if item.verdict == "reject")
    pending_count = sum(1 for item in lots if item.verdict == "pending")
    if reject_count:
        current = "reject"
    elif pending_count:
        current = None
    else:
        current = "accept"
    switching = switching_advice(receipt.severity, receipt.history, current)
    return PlanResult(
        receipt=receipt.receipt,
        supplier=receipt.supplier,
        dock=receipt.dock,
        level=receipt.level,
        severity=receipt.severity,
        seed=receipt.seed,
        switching=switching,
        lots=lots,
        all_accept=reject_count == 0 and pending_count == 0,
        reject_count=reject_count,
        pending_count=pending_count,
        sample_total=sum(item.sample_size for item in lots),
    )


def draw_indices(lot_size: int, n: int, seed: str) -> list[int]:
    """1-based carton numbers, sorted so the inspector walks the lot in order."""
    if n > lot_size:
        raise ValueError("Sample cannot be larger than the lot")
    rng = random.Random(seed)
    picked = rng.sample(range(1, lot_size + 1), n)
    return sorted(picked)


def switching_advice(severity: str, history: list[str], current: str | None) -> str:
    """Advice for the *next* receipt. Screening, not ISO switching rules.

    - reduced + a reject → return to normal
    - tightened + 5 accepts in a row → return to normal
    - normal + 2 rejects in the last 5 → tighten
    - normal + 10 accepts in a row → reduce
    """
    recent = list(history)
    if current in ("accept", "reject"):
        recent.append(current)
    if not recent:
        return "stay"
    if severity == "reduced":
        if recent[-1] == "reject":
            return "return_to_normal"
        return "stay"
    if severity == "tightened":
        if len(recent) >= 5 and all(item == "accept" for item in recent[-5:]):
            return "return_to_normal"
        return "stay"
    last5 = recent[-5:]
    if last5.count("reject") >= 2:
        return "tighten"
    if len(recent) >= 10 and all(item == "accept" for item in recent[-10:]):
        return "reduce"
    return "stay"


def _plan_lot(receipt: Receipt, lot: Lot) -> LotPlan:
    letter = letter_for(lot.lot_size, receipt.level, receipt.severity)
    n, hundred = sample_size(letter, lot.lot_size)
    seed = f"{receipt.seed}|{lot.sku}|{letter}|{n}"
    drawn = draw_indices(lot.lot_size, n, seed)
    class_plans: list[ClassPlan] = []
    for name, aql in receipt.classes.items():
        ac = accept_number(n, aql)
        re = reject_number(ac)
        found = None if lot.found is None else int(lot.found[name])
        if found is not None and found > n:
            raise ValueError(f"Lot '{lot.sku}' {name} found ({found}) exceeds sample size {n}")
        class_plans.append(
            ClassPlan(
                name=name,
                aql=aql,
                n=n,
                ac=ac,
                re=re,
                found=found,
                verdict=_verdict(found, ac, re),
            )
        )
    return LotPlan(
        sku=lot.sku,
        description=lot.description,
        lot_size=lot.lot_size,
        letter=letter,
        sample_size=n,
        hundred_percent=hundred,
        draw=drawn,
        classes=class_plans,
        verdict=_lot_verdict(class_plans),
    )


def _verdict(found: int | None, ac: int, re: int) -> str:
    if found is None:
        return "pending"
    if found >= re:
        return "reject"
    if found <= ac:
        return "accept"
    return "pending"


def _lot_verdict(classes: list[ClassPlan]) -> str:
    if any(item.verdict == "reject" for item in classes):
        return "reject"
    if any(item.verdict == "pending" for item in classes):
        return "pending"
    return "accept"
