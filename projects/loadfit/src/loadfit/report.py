"""Human-readable packing reports."""

from __future__ import annotations

from .pack import PackResult


def text_report(result: PackResult) -> str:
    c = result.container
    lines = [
        f"LoadFit — {c.name}",
        f"Cargo box: {c.length_mm} x {c.width_mm} x {c.height_mm} mm  |  payload {c.max_weight_kg:g} kg",
        f"Packed {len(result.placements)} carton(s)  |  leftover {sum(int(item['quantity']) for item in result.unpacked)}",
        f"Cube: {result.volume_utilization:.1%}  ({result.volume_used_mm3 / 1_000_000_000:.3f} m³)",
        f"Weight: {result.weight_utilization:.1%}  ({result.weight_used_kg:.1f} kg)",
        "",
        f"{'SKU':<12} {'X':>6} {'Y':>6} {'Z':>6} {'L':>6} {'W':>6} {'H':>6} {'kg':>7}",
        "-" * 64,
    ]
    for p in result.placements:
        lines.append(
            f"{p.sku:<12} {p.x:>6} {p.y:>6} {p.z:>6} {p.length_mm:>6} {p.width_mm:>6} {p.height_mm:>6} {p.weight_kg:>7.1f}"
        )
    if result.unpacked:
        lines.append("")
        lines.append("Could not load:")
        for item in result.unpacked:
            lines.append(
                f"  {item['quantity']} x {item['sku']} "
                f"({item['length_mm']}x{item['width_mm']}x{item['height_mm']} mm, {item['weight_kg']} kg)"
            )
    return "\n".join(lines) + "\n"
