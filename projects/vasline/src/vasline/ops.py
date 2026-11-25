"""Catalog of warehouse value-added service operations.

Times are dock-side working figures (seconds per unit, changeover seconds),
not a particular WMS labour standard.
"""

from __future__ import annotations

from typing import Any

OPS: dict[str, dict[str, Any]] = {
    "relabel": {
        "id": "relabel",
        "name": "Relabel",
        "blurb": "Print and apply store or GS1 labels",
        "seconds_per_unit": 8,
        "setup_seconds": 90,
    },
    "kit": {
        "id": "kit",
        "name": "Kitting",
        "blurb": "Assemble a bundle from component SKUs",
        "seconds_per_unit": 25,
        "setup_seconds": 180,
    },
    "insert": {
        "id": "insert",
        "name": "Inserts",
        "blurb": "Drop a coupon, manual, or sample",
        "seconds_per_unit": 6,
        "setup_seconds": 60,
    },
    "wrap": {
        "id": "wrap",
        "name": "Gift wrap",
        "blurb": "Gift wrap or tissue a finished pack",
        "seconds_per_unit": 40,
        "setup_seconds": 120,
    },
    "inspect": {
        "id": "inspect",
        "name": "Inspect",
        "blurb": "QA pass for damaged or short units",
        "seconds_per_unit": 12,
        "setup_seconds": 45,
    },
    "shrink": {
        "id": "shrink",
        "name": "Shrink wrap",
        "blurb": "Heat-shrink a multi-pack",
        "seconds_per_unit": 15,
        "setup_seconds": 150,
    },
    "ticket": {
        "id": "ticket",
        "name": "Price ticket",
        "blurb": "Hangtag or shelf-ticket a unit",
        "seconds_per_unit": 5,
        "setup_seconds": 75,
    },
    "rework": {
        "id": "rework",
        "name": "Rework",
        "blurb": "Repair carton, tape, or pack",
        "seconds_per_unit": 30,
        "setup_seconds": 90,
    },
}


def known_ops() -> tuple[str, ...]:
    return tuple(OPS)


def ops_payload() -> dict[str, object]:
    return {
        "ops": [OPS[key] for key in OPS],
        "rule": (
            "A job is a sequence of steps. Each step needs a bench with that skill. "
            "Steps of one job are serial; benches run in parallel. A family change "
            "on a bench pays that step's setup time. A job that cannot finish every "
            "step before shift end is leftover — nothing is left half-kitted."
        ),
    }


def default_seconds_per_unit(op: str) -> float:
    return float(OPS[op]["seconds_per_unit"])


def default_setup_seconds(op: str) -> float:
    return float(OPS[op]["setup_seconds"])
