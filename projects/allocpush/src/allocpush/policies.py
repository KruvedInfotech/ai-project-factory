"""Allocation policies, store grades, and desk cards."""

from __future__ import annotations

POLICIES: dict[str, str] = {
    "fair_share": "Split short stock by weighted need (A=3, B=2, C=1), largest remainder",
    "need_fill": "Fill the hungriest store first until the DC is empty",
    "grade_first": "Fill every A store, then B, then C",
}

DEFAULT_POLICY = "fair_share"

GRADES: tuple[str, ...] = ("A", "B", "C")
GRADE_WEIGHT: dict[str, int] = {"A": 3, "B": 2, "C": 1}

DEFAULT_PORT = 8795


def get_policy(raw: object) -> str:
    key = str(raw or DEFAULT_POLICY).strip().lower()
    if key not in POLICIES:
        raise ValueError(f"Unknown policy '{raw}'. Use fair_share, need_fill, or grade_first")
    return key


def get_grade(raw: object) -> str:
    key = str(raw or "B").strip().upper()
    if key not in GRADE_WEIGHT:
        raise ValueError(f"Unknown store grade '{raw}'. Use A, B, or C")
    return key


def policies_payload() -> dict[str, object]:
    return {
        "policies": [{"id": key, "name": name} for key, name in POLICIES.items()],
        "grades": [{"id": key, "weight": GRADE_WEIGHT[key]} for key in GRADES],
        "default_policy": DEFAULT_POLICY,
        "rule": (
            "Need is max(0, min(max_cap, max(min_face, forecast)) − on_hand). "
            "Ship whole packs (case, or inner if break_case). "
            "Holdback stays at the DC. Short stock uses the chosen policy."
        ),
    }
