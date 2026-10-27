"""Human-readable fold reports."""

from __future__ import annotations

from .fold import FoldResult


def text_report(result: FoldResult) -> str:
    w = result.warehouse
    lines = [
        f"SlotFold — {w.name}",
        f"Rack room: {len(w.aisles)} aisles × {w.bays} bays × {w.levels} levels",
        f"Moves {result.move_count}  |  units {result.units_moved}  |  freed {result.freed_count}  |  leftover {result.leftover_count}",
        f"Labor: {result.labor_used}/{result.labor_cap} min  ({result.labor_utilization:.1%})",
        "",
        f"{'FROM':<10} {'TO':<10} {'SKU':<12} {'QTY':>5} {'MIN':>4}",
        "-" * 46,
    ]
    for move in result.moves:
        lines.append(
            f"{move.from_id:<10} {move.to_id:<10} {move.sku:<12} {move.qty:>5} {move.minutes:>4}"
        )
    if result.freed:
        lines.append("")
        lines.append("Freed slots:")
        for item in result.freed:
            lines.append(f"  {item['id']}  {item['sku']}  ({item['kind']})")
    if result.leftover:
        lines.append("")
        lines.append("Could not fold:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}  {item['qty']} × {item['sku']}  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
