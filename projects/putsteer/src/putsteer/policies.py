"""Putaway policies: mix rules, location type, and labor.

Figures are typical desk-side values, not a particular WMS configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STRATEGIES = ("priority", "heavy", "tall", "fifo")
TEMPS = ("dry", "cool", "frozen")
LOCATION_TYPES = ("reserve", "pick")
VELOCITIES = ("A", "B", "C")
TYPE_FILTERS = ("", "reserve", "pick")


@dataclass(frozen=True)
class Policy:
    id: str
    name: str
    allow_mix_sku: bool
    prefer_topoff: bool
    location_type: str
    minutes_per_put: int
    aisle_change_min: int
    max_labor_min: int

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Policy needs a name")
        if self.location_type not in TYPE_FILTERS:
            raise ValueError("location_type must be empty, reserve, or pick")
        if self.minutes_per_put < 1:
            raise ValueError("minutes_per_put must be at least 1")
        if self.aisle_change_min < 0:
            raise ValueError("aisle_change_min cannot be negative")
        if self.max_labor_min < 1:
            raise ValueError("max_labor_min must be at least 1")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["mix"] = "yes" if self.allow_mix_sku else "no"
        data["topoff"] = "yes" if self.prefer_topoff else "no"
        return data


PRESETS: dict[str, Policy] = {
    "reserve_dc": Policy(
        id="reserve_dc",
        name="Reserve DC",
        allow_mix_sku=False,
        prefer_topoff=True,
        location_type="reserve",
        minutes_per_put=4,
        aisle_change_min=2,
        max_labor_min=40,
    ),
    "pick_fc": Policy(
        id="pick_fc",
        name="Forward pick FC",
        allow_mix_sku=False,
        prefer_topoff=True,
        location_type="pick",
        minutes_per_put=3,
        aisle_change_min=1,
        max_labor_min=24,
    ),
    "cold_vault": Policy(
        id="cold_vault",
        name="Cold vault",
        allow_mix_sku=False,
        prefer_topoff=True,
        location_type="",
        minutes_per_put=5,
        aisle_change_min=2,
        max_labor_min=16,
    ),
    "bulk_floor": Policy(
        id="bulk_floor",
        name="Bulk floor",
        allow_mix_sku=True,
        prefer_topoff=False,
        location_type="reserve",
        minutes_per_put=6,
        aisle_change_min=3,
        max_labor_min=60,
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
    location_type = str(
        raw.get("location_type", default.location_type if default else "reserve")
    ).strip()
    return Policy(
        id=str(raw.get("id") or (default.id if default else "custom")),
        name=str(raw.get("name") or (default.name if default else "Custom policy")),
        allow_mix_sku=_bool_or(raw, "allow_mix_sku", default.allow_mix_sku if default else False),
        prefer_topoff=_bool_or(raw, "prefer_topoff", default.prefer_topoff if default else True),
        location_type=location_type,
        minutes_per_put=_int_or(
            raw, "minutes_per_put", default.minutes_per_put if default else 4
        ),
        aisle_change_min=_int_or(
            raw, "aisle_change_min", default.aisle_change_min if default else 2
        ),
        max_labor_min=_int_or(raw, "max_labor_min", default.max_labor_min if default else 40),
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
                allow_mix_sku=policy.allow_mix_sku,
                prefer_topoff=policy.prefer_topoff,
                location_type=policy.location_type,
                minutes_per_put=policy.minutes_per_put,
                aisle_change_min=policy.aisle_change_min,
                max_labor_min=policy.max_labor_min,
            )
        return policy
    return _policy_from_parts(payload)
