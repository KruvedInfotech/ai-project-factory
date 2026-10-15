"""Cycle-count policies: ABC cadence, labor, and variance.

Figures are typical desk-side values, not a particular WMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STRATEGIES = ("overdue", "abc", "aisle", "shrink")
ABC_CLASSES = ("A", "B", "C")
LOCATION_TYPES = ("pick", "reserve")

NEVER_COUNTED = 10**9


@dataclass(frozen=True)
class Policy:
    id: str
    name: str
    cycle_a_days: int
    cycle_b_days: int
    cycle_c_days: int
    shrink_cycle_days: int
    skip_empty: bool
    freeze_on_count: bool
    minutes_per_count: int
    aisle_change_min: int
    max_labor_min: int
    variance_pct: float
    variance_units: int

    def cycle_days(self, abc: str) -> int:
        mapping = {"A": self.cycle_a_days, "B": self.cycle_b_days, "C": self.cycle_c_days}
        return mapping[abc]

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Policy needs a name")
        for label, value in (
            ("cycle_a_days", self.cycle_a_days),
            ("cycle_b_days", self.cycle_b_days),
            ("cycle_c_days", self.cycle_c_days),
            ("shrink_cycle_days", self.shrink_cycle_days),
        ):
            if value < 1:
                raise ValueError(f"{label} must be at least 1")
        if self.minutes_per_count < 1:
            raise ValueError("minutes_per_count must be at least 1")
        if self.aisle_change_min < 0:
            raise ValueError("aisle_change_min cannot be negative")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")
        if self.variance_pct < 0:
            raise ValueError("variance_pct cannot be negative")
        if self.variance_units < 0:
            raise ValueError("variance_units cannot be negative")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["skip"] = "empty" if self.skip_empty else "zeros"
        data["freeze"] = "yes" if self.freeze_on_count else "no"
        data["cadence"] = f"{self.cycle_a_days}/{self.cycle_b_days}/{self.cycle_c_days}"
        return data


PRESETS: dict[str, Policy] = {
    "grocery_dc": Policy(
        id="grocery_dc",
        name="Grocery DC",
        cycle_a_days=7,
        cycle_b_days=30,
        cycle_c_days=90,
        shrink_cycle_days=7,
        skip_empty=True,
        freeze_on_count=False,
        minutes_per_count=2,
        aisle_change_min=1,
        max_labor_min=40,
        variance_pct=0.05,
        variance_units=2,
    ),
    "pharma_vault": Policy(
        id="pharma_vault",
        name="Pharma vault",
        cycle_a_days=1,
        cycle_b_days=7,
        cycle_c_days=30,
        shrink_cycle_days=1,
        skip_empty=False,
        freeze_on_count=True,
        minutes_per_count=3,
        aisle_change_min=1,
        max_labor_min=24,
        variance_pct=0.02,
        variance_units=1,
    ),
    "ecom_fc": Policy(
        id="ecom_fc",
        name="E-com FC",
        cycle_a_days=14,
        cycle_b_days=45,
        cycle_c_days=180,
        shrink_cycle_days=14,
        skip_empty=True,
        freeze_on_count=False,
        minutes_per_count=1,
        aisle_change_min=1,
        max_labor_min=60,
        variance_pct=0.05,
        variance_units=3,
    ),
    "bulk_reserve": Policy(
        id="bulk_reserve",
        name="Bulk reserve",
        cycle_a_days=30,
        cycle_b_days=90,
        cycle_c_days=180,
        shrink_cycle_days=14,
        skip_empty=False,
        freeze_on_count=False,
        minutes_per_count=4,
        aisle_change_min=2,
        max_labor_min=90,
        variance_pct=0.10,
        variance_units=5,
    ),
}


def _bool_or(raw: dict[str, Any], key: str, default: bool) -> bool:
    if key not in raw:
        return default
    value = raw[key]
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be true or false")


def _int_or(raw: dict[str, Any], key: str, default: int) -> int:
    return int(raw[key]) if key in raw else default


def _float_or(raw: dict[str, Any], key: str, default: float) -> float:
    return float(raw[key]) if key in raw else default


def _policy_from_parts(raw: dict[str, Any], default: Policy | None = None) -> Policy:
    return Policy(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom policy")),
        cycle_a_days=_int_or(raw, "cycle_a_days", default.cycle_a_days if default else 7),
        cycle_b_days=_int_or(raw, "cycle_b_days", default.cycle_b_days if default else 30),
        cycle_c_days=_int_or(raw, "cycle_c_days", default.cycle_c_days if default else 90),
        shrink_cycle_days=_int_or(
            raw, "shrink_cycle_days", default.shrink_cycle_days if default else 7
        ),
        skip_empty=_bool_or(raw, "skip_empty", default.skip_empty if default else True),
        freeze_on_count=_bool_or(
            raw, "freeze_on_count", default.freeze_on_count if default else False
        ),
        minutes_per_count=_int_or(
            raw, "minutes_per_count", default.minutes_per_count if default else 2
        ),
        aisle_change_min=_int_or(
            raw, "aisle_change_min", default.aisle_change_min if default else 1
        ),
        max_labor_min=_int_or(raw, "max_labor_min", default.max_labor_min if default else 40),
        variance_pct=_float_or(raw, "variance_pct", default.variance_pct if default else 0.05),
        variance_units=_int_or(raw, "variance_units", default.variance_units if default else 2),
    )


def get_policy(raw: dict[str, Any] | None) -> Policy:
    payload = dict(raw or {})
    preset = payload.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown policy preset '{preset}'")
        policy = _policy_from_parts(payload, PRESETS[preset])
        if "id" not in payload:
            policy = Policy(
                id=str(preset),
                name=policy.name,
                cycle_a_days=policy.cycle_a_days,
                cycle_b_days=policy.cycle_b_days,
                cycle_c_days=policy.cycle_c_days,
                shrink_cycle_days=policy.shrink_cycle_days,
                skip_empty=policy.skip_empty,
                freeze_on_count=policy.freeze_on_count,
                minutes_per_count=policy.minutes_per_count,
                aisle_change_min=policy.aisle_change_min,
                max_labor_min=policy.max_labor_min,
                variance_pct=policy.variance_pct,
                variance_units=policy.variance_units,
            )
        return policy
    return _policy_from_parts(payload)
