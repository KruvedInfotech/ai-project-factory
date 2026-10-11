"""Human-readable putaway reports."""

from __future__ import annotations

from .steer import SteerResult


def text_report(result: SteerResult) -> str:
    policy = result.policy
    loc_type = policy.location_type or "any"
    mix = "mix" if policy.allow_mix_sku else "no-mix"
    topoff = "top-off" if policy.prefer_topoff else "open-slot"
    lines = [
        f"PutSteer — {policy.name}",
        (
            f"{result.strategy}  |  {loc_type}  |  {mix}  |  {topoff}  |  "
            f"labor {result.labor_used_min}/{result.labor_cap_min} min"
        ),
        (
            f"Put {result.placed_pallets} of {result.asked_pallets} pallet(s)  |  "
            f"lines {result.put_count}  |  leftover {result.leftover_count}  |  "
            f"fill {result.fill_rate:.0%}"
        ),
        "",
        f"{'LPN':<10} {'SKU':<12} {'LOC':<12} {'A':>2} {'B':>2} {'L':>2} "
        f"{'ZN':<2} {'MIN':>3} {'NOTE':<8}",
        "-" * 68,
    ]
    for item in result.puts:
        note = "top-off" if item.topoff else ""
        lines.append(
            f"{item.pallet_id:<10} {item.sku:<12} {item.location_id:<12} "
            f"{item.aisle:>2} {item.bay:>2} {item.level:>2} "
            f"{item.zone:<2} {item.minutes:>3} {note:<8}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not put:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}: {item['sku']} {item['pallets']} pal "
                f"{item['temp']} — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
