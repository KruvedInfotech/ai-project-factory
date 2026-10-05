"""Human-readable cross-dock reports."""

from __future__ import annotations

from .match import FlowResult


def text_report(result: FlowResult) -> str:
    yard = result.yard
    lines = [
        f"FlowMatch — {yard.name}",
        (
            f"Hours: {yard.open}–{yard.close}  |  "
            f"{len(yard.lanes)} lanes  |  {result.strategy}"
        ),
        (
            f"Matched {result.matched_pallets} pallet(s)  |  "
            f"live {result.live_pallets}  |  staged {result.stage_pallets}  |  "
            f"fill {result.fill_rate:.0%}"
        ),
        (
            f"Allocations: {len(result.allocations)}  |  "
            f"leftover in {len(result.leftover_in)} / out {len(result.leftover_out)}"
        ),
        f"Labor: {result.labor_min} min of {yard.max_labor_min}",
        "",
        f"{'IN':<10} {'OUT':<10} {'SKU':<12} {'plt':>3} {'MODE':<5} {'LANE':<4} {'READY':>5} {'min':>4}",
        "-" * 64,
    ]
    for item in result.allocations:
        lane = item.lane_id or "—"
        lines.append(
            f"{item.receipt_id:<10} {item.order_id:<10} {item.sku:<12} "
            f"{item.pallets:>3} {item.mode:<5} {lane:<4} {item.ready:>5} {item.labor_min:>4}"
        )
    if result.leftover_in:
        lines.append("")
        lines.append("Inbound leftover (putaway):")
        for item in result.leftover_in:
            lines.append(f"  {item['id']}: {item['pallets']} × {item['sku']} — {item['reason']}")
    if result.leftover_out:
        lines.append("")
        lines.append("Outbound leftover (short):")
        for item in result.leftover_out:
            lines.append(f"  {item['id']}: {item['pallets']} × {item['sku']} — {item['reason']}")
    return "\n".join(lines) + "\n"
