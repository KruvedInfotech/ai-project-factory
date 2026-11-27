"""Tote types and the homes they return to.

Counts nest into stacks. A cart holds a handful of stacks and only one
tote type per trip, because each type drops at a different home.
"""

from __future__ import annotations

TOTES: dict[str, dict[str, object]] = {
    "std": {
        "id": "std",
        "name": "Standard nestable",
        "home_kind": "induction",
        "nest_per_stack": 20,
        "blurb": "Pick/pack totes nested back to induction",
    },
    "cold": {
        "id": "cold",
        "name": "Cold-chain / wash",
        "home_kind": "wash",
        "nest_per_stack": 16,
        "blurb": "Food-grade; must go through tote wash",
    },
    "oversize": {
        "id": "oversize",
        "name": "Oversize / non-nest",
        "home_kind": "buffer",
        "nest_per_stack": 4,
        "blurb": "Awkward totes; stack to the buffer bay",
    },
}

HOME_KINDS: dict[str, str] = {
    "induction": "Where empty totes get filled again",
    "wash": "Tote washer for food-grade / soiled tubs",
    "buffer": "Overflow nest storage",
}

STATION_KINDS = ("pick", "pack", "returns")


def totes_payload() -> dict[str, object]:
    return {
        "totes": [dict(item) for item in TOTES.values()],
        "home_kinds": [{"id": key, "blurb": blurb} for key, blurb in HOME_KINDS.items()],
        "station_kinds": list(STATION_KINDS),
        "rule": (
            "One tote type per trip. Nested stacks fill the cart; leftover "
            "below the station threshold is residual, not a failed run."
        ),
    }


def nest_per_stack(tote: str) -> int:
    if tote not in TOTES:
        known = ", ".join(sorted(TOTES))
        raise ValueError(f"Unknown tote type '{tote}'. Known: {known}")
    return int(TOTES[tote]["nest_per_stack"])


def default_accepts(home_kind: str) -> list[str]:
    return [key for key, meta in TOTES.items() if meta["home_kind"] == home_kind]
