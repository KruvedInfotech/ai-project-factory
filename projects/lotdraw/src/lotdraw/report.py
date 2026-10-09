"""Human-readable lot-draw reports."""

from __future__ import annotations

from .draw import DrawResult


def text_report(result: DrawResult) -> str:
    policy = result.policy
    split = "split" if policy.allow_split else "no-split"
    lines = [
        f"LotDraw — {policy.name}",
        (
            f"Today: {result.today}  |  {result.strategy}  |  "
            f"life {policy.min_remaining_days}d  |  {split}  |  "
            f"max {policy.max_lots_per_line} lot(s)"
        ),
        (
            f"Filled {result.filled_qty} of {result.asked_qty} unit(s)  |  "
            f"lines {result.allocation_count}  |  leftover {result.leftover_count}  |  "
            f"fill {result.fill_rate:.0%}"
        ),
        "",
        f"{'ORDER':<10} {'SKU':<12} {'LOT':<8} {'QTY':>5} {'EXPIRY':<12} {'LIFE':>5} {'LOC':<10}",
        "-" * 68,
    ]
    for item in result.allocations:
        loc = item.location or "—"
        lines.append(
            f"{item.order_id:<10} {item.sku:<12} {item.lot_id:<8} {item.qty:>5} "
            f"{item.expiry:<12} {item.life_at_ship:>5} {loc:<10}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not fill:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}: {item['sku']} short {item['short']} of {item['qty']} — {item['reason']}"
            )
    if result.held:
        lines.append("")
        lines.append("On hold:")
        for item in result.held:
            hold = item.get("hold") or "hold"
            lines.append(f"  {item['id']}: {item['sku']} {item['remaining']} {hold}")
    if result.unused:
        lines.append("")
        lines.append("Still on hand:")
        for item in result.unused:
            lines.append(
                f"  {item['id']}: {item['sku']} {item['remaining']} exp {item['expiry']}"
            )
    return "\n".join(lines) + "\n"
