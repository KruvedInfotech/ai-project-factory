"""Human-readable put-wall assignment reports."""

from __future__ import annotations

from .sort import SortResult


def text_report(result: SortResult) -> str:
    wall = result.wall
    lines = [
        f"WallSort — {wall.name}",
        (
            f"{result.strategy}  |  {wall.rows}×{wall.cols} cubbies  |  "
            f"{wall.temp}  |  labor {result.labor_used_min}/{result.labor_cap_min} min  |  "
            f"{result.weight_used_kg:g} kg"
        ),
        (
            f"Units {result.packed_count}/{result.piece_count}  |  "
            f"orders {result.packed_orders}/{result.order_count}  |  "
            f"leftover {result.leftover_count}  |  cubbies {result.cubby_utilization:.0%}"
        ),
        "",
        f"{'SEQ':>3} {'PIECE':<16} {'ORDER':<10} {'CARRIER':<8} "
        f"{'CUBBY':<6} {'ZONE':<8} {'KG':>6} {'SKU':<12}",
        "-" * 82,
    ]
    for item in result.placements:
        lines.append(
            f"{item.seq:>3} {item.piece_id:<16} {item.order_id:<10} {item.carrier:<8} "
            f"{item.cubby:<6} {item.zone:<8} {item.weight_kg:>6.2f} {item.sku:<12}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Left on the pack bench:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}: {item['sku']} order {item['order_id']} "
                f"{item['carrier']} — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
