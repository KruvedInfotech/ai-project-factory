"""Human-readable trailer load reports."""

from __future__ import annotations

from .stack import StackResult


def text_report(result: StackResult) -> str:
    trailer = result.trailer
    stack_label = "2-high" if trailer.stack_levels == 2 else "floor"
    lines = [
        f"StopStack — {trailer.name}",
        (
            f"{result.strategy}  |  {trailer.rows}×{trailer.cols} {stack_label}  |  "
            f"{trailer.temp}  |  labor {result.labor_used_min}/{result.labor_cap_min} min  |  "
            f"{result.weight_used_kg:g}/{trailer.max_weight_kg:g} kg"
        ),
        (
            f"Pallets {result.packed_count}/{result.piece_count}  |  leftover {result.leftover_count}  |  "
            f"cube {result.cube_utilization:.0%}  |  weight {result.weight_utilization:.0%}"
        ),
        "",
        f"{'SEQ':>3} {'PALLET':<12} {'STOP':<10} {'#':>2} {'ROW':>3} {'SIDE':<4} "
        f"{'LV':>2} {'KG':>6} {'MM':>5} {'SKU':<12}",
        "-" * 78,
    ]
    for item in result.placements:
        layer = "FL" if item.level == 0 else "UP"
        lines.append(
            f"{item.seq:>3} {item.pallet_id:<12} {item.stop_id:<10} {item.stop_seq:>2} "
            f"{item.row:>3} {item.side:<4} {layer:>2} {item.weight_kg:>6.0f} "
            f"{item.height_mm:>5} {item.sku:<12}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Left on the dock:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}: {item['sku']} stop {item['stop_id']} "
                f"{item['weight_kg']:g} kg — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
