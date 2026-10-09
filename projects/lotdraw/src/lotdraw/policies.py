"""Allocation policies: remaining shelf life, split rules, lot caps.

Figures are typical desk-side values, not a particular WMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STRATEGIES = ("fefo", "fifo", "fewest")
HOLD_STATES = ("", "none", "quality", "recall", "damage")


def is_held(hold: str) -> bool:
    return hold not in {"", "none"}


def normalize_hold(hold: str) -> str:
    text = str(hold).strip().lower()
    if text in {"", "none"}:
        return ""
    return text


@dataclass(frozen=True)
class Policy:
    id: str
    name: str
    min_remaining_days: int
    allow_split: bool
    max_lots_per_line: int

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Policy needs a name")
        if self.min_remaining_days < 0:
            raise ValueError("min_remaining_days cannot be negative")
        if self.max_lots_per_line < 1:
            raise ValueError("max_lots_per_line must be at least 1")
        if not self.allow_split and self.max_lots_per_line != 1:
            raise ValueError("A no-split policy must set max_lots_per_line to 1")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["split"] = "yes" if self.allow_split else "no"
        return data


PRESETS: dict[str, Policy] = {
    "grocery_dc": Policy(
        id="grocery_dc",
        name="Grocery DC",
        min_remaining_days=7,
        allow_split=True,
        max_lots_per_line=4,
    ),
    "pharma_vault": Policy(
        id="pharma_vault",
        name="Pharma vault",
        min_remaining_days=90,
        allow_split=True,
        max_lots_per_line=2,
    ),
    "cosmetics_fc": Policy(
        id="cosmetics_fc",
        name="Cosmetics FC",
        min_remaining_days=30,
        allow_split=False,
        max_lots_per_line=1,
    ),
    "fresh_cold": Policy(
        id="fresh_cold",
        name="Fresh cold room",
        min_remaining_days=3,
        allow_split=True,
        max_lots_per_line=6,
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


def _policy_from_parts(raw: dict[str, Any], default: Policy | None = None) -> Policy:
    allow_split = _bool_or(raw, "allow_split", default.allow_split if default else True)
    max_lots = _int_or(raw, "max_lots_per_line", default.max_lots_per_line if default else 4)
    if not allow_split:
        max_lots = 1
    return Policy(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom policy")),
        min_remaining_days=_int_or(
            raw, "min_remaining_days", default.min_remaining_days if default else 7
        ),
        allow_split=allow_split,
        max_lots_per_line=max_lots,
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
                min_remaining_days=policy.min_remaining_days,
                allow_split=policy.allow_split,
                max_lots_per_line=policy.max_lots_per_line,
            )
        return policy
    return _policy_from_parts(payload)
