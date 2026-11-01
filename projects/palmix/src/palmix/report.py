"""Human-readable pallet-build reports."""

from __future__ import annotations

from .pack import PackResult


def text_report(result: PackResult) -> str:
    deck = result.deck
    lines = [
        f"PalMix — {deck.name}",
        (
            f"Deck: {deck.length_mm} x {deck.width_mm} x {deck.height_mm} mm  |  "
            f"payload {deck.max_weight_kg:g} kg  |  {deck.temp}  |  "
            f"max {deck.max_pallets} pallet(s)"
        ),
        (
            f"Packed {result.packed_count} case(s) onto {result.pallet_count} pallet(s)  |  "
            f"leftover {result.leftover_count}"
        ),
        (
            f"Labor: {result.labor_utilization:.1%}  "
            f"({result.labor_used_min}/{result.labor_cap_min} min)  |  "
            f"cube {result.volume_utilization:.1%}  |  "
            f"weight {result.weight_utilization:.1%}  |  "
            f"strategy {result.strategy}"
        ),
        "",
        f"{'Pal':<5} {'Store':<8} {'SKU':<12} {'Fam':<10} {'X':>5} {'Y':>5} {'Z':>5} "
        f"{'L':>5} {'W':>5} {'H':>5} {'kg':>6}",
        "-" * 80,
    ]
    for item in result.placements:
        lines.append(
            f"{item.pallet_id:<5} {item.store:<8} {item.sku:<12} {item.family:<10} "
            f"{item.x:>5} {item.y:>5} {item.z:>5} "
            f"{item.length_mm:>5} {item.width_mm:>5} {item.height_mm:>5} "
            f"{item.weight_kg:>6.1f}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not mix:")
        for item in result.leftover:
            lines.append(
                f"  {item['quantity']} x {item['sku']}  store {item['store']}  "
                f"{item['temp']}  {item['weight_kg']} kg  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
