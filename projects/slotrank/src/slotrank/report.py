"""Human-readable slotting reports."""

from __future__ import annotations

from .slot import SlotResult


def text_report(result: SlotResult) -> str:
    house = result.warehouse
    lines = [
        f"SlotRank — {house.name}",
        (
            f"Layout: {house.aisle_count}×{house.bays_per_aisle}  |  "
            f"golden A1–A{house.golden_aisles} bays 1–{house.golden_bays}  |  "
            f"{result.strategy}"
        ),
        (
            f"ABC: {sum(1 for value in result.abc.values() if value == 'A')} A · "
            f"{sum(1 for value in result.abc.values() if value == 'B')} B · "
            f"{sum(1 for value in result.abc.values() if value == 'C')} C"
        ),
        (
            f"A in golden: {result.a_golden_before:.0%} → {result.a_golden_after:.0%}  |  "
            f"travel {result.travel_before:.2f} → {result.travel_after:.2f}"
        ),
        (
            f"Moves this wave: {result.move_count}  |  later {result.later_count}  |  "
            f"kept {result.keep_count}  |  leftover {result.leftover_count}"
        ),
        f"Labor: {result.labor_min} min of {house.max_labor_min}",
        "",
        f"{'SKU':<12} {'ABC':<3} {'FROM':<10} {'TO':<10} {'WAVE':<6} {'min':>4}",
        "-" * 52,
    ]
    for move in result.moves:
        lines.append(
            f"{move.sku:<12} {move.abc:<3} {move.from_id:<10} {move.to_id:<10} "
            f"{move.wave:<6} {move.labor_min:>4}"
        )
    keeps = [item for item in result.placements if item.status == "keep"]
    if keeps:
        lines.append("")
        lines.append("Already home:")
        for item in keeps:
            loc = item.location.id if item.location else "?"
            lines.append(f"  {item.sku.sku} {item.abc} @ {loc}")
    if result.leftover:
        lines.append("")
        lines.append("Could not finish:")
        for item in result.leftover:
            lines.append(f"  {item['id']}: {item['reason']}")
    return "\n".join(lines) + "\n"
