"""Human-readable returns plans."""

from __future__ import annotations

from .plan import PlanResult


def text_report(result: PlanResult) -> str:
    counts = result.disposition_counts()
    mix = ", ".join(f"{name} {counts.get(name, 0)}" for name in ("restock", "refurb", "scrap", "rma", "hold"))
    lines = [
        f"ReturnSort — {result.floor.name}",
        f"Lanes: {len(result.floor.lanes)}  |  slots {result.floor.slot_count}",
        f"Parked {result.assigned_count} unit(s)  |  leftover {result.leftover_count}",
        f"Labor: {result.labor_used}/{result.labor_cap} min  ({result.labor_utilization:.1%})",
        f"Mix: {mix}",
        "",
        f"{'TICKET':<12} {'SKU':<14} {'DISP':<8} {'LANE':<10} {'SLOT':>4} {'MIN':>4}",
        "-" * 60,
    ]
    for item in result.assignments:
        lines.append(
            f"{item.ticket:<12} {item.sku:<14} {item.disposition:<8} {item.lane_id:<10} {item.slot:>4} {item.minutes:>4}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not park:")
        for item in result.leftover:
            lines.append(
                f"  {item['quantity']} x {item['ticket']} {item['sku']} "
                f"({item['disposition']}) — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
