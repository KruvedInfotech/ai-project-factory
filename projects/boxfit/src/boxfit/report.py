"""Human-readable cartonization reports."""

from __future__ import annotations

from .pack import PackResult


def text_report(result: PackResult) -> str:
    catalog = result.catalog
    lines = [
        f"BoxFit — {catalog.name}",
        f"Catalog: {len(catalog.cartons)} shippers  |  cartons {result.carton_count}  |  packed {result.packed_count}/{result.piece_count}  |  leftover {result.leftover_count}",
        f"Labor: {result.labor_used}/{result.labor_cap} min  ({result.labor_utilization:.1%})  |  mean void {result.mean_void:.1%}",
        "",
        f"{'CARTON':<10} {'ORDER':<10} {'SHIPPER':<12} {'PCS':>4} {'KG':>7} {'CUBE':>6} {'TEMP':<6}",
        "-" * 62,
    ]
    for carton in result.cartons:
        lines.append(
            f"{carton.id:<10} {carton.order_id:<10} {carton.shipper.id:<12} {len(carton.placements):>4} "
            f"{carton.weight_kg:>7.2f} {carton.fill:>5.0%} {carton.temp:<6}"
        )
        for placement in carton.placements:
            lines.append(
                f"  {placement.sku}  {placement.length_mm}×{placement.width_mm}×{placement.height_mm} mm  "
                f"@ {placement.x},{placement.y},{placement.z}"
            )
    if result.leftover:
        lines.append("")
        lines.append("Could not pack:")
        for item in result.leftover:
            lines.append(
                f"  {item['order_id']}  {item['quantity']} × {item['sku']}  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
