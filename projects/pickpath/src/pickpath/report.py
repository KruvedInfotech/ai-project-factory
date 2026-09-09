"""Human-readable pick-path reports."""

from __future__ import annotations

from .route import RouteResult


def text_report(result: RouteResult) -> str:
    w = result.warehouse
    chosen = result.chosen_strategy.replace("_", "-")
    strategy_label = result.strategy.replace("_", "-")
    if result.strategy == "auto":
        strategy_label = f"auto → {chosen}"
    lines = [
        f"PickPath — {w.name}",
        f"Floor: {w.aisle_count} aisles × {w.bays_per_aisle} bays  |  rear cross-aisle {'yes' if w.has_rear else 'no'}",
        f"Strategy: {strategy_label}",
        f"Stops: {len(result.stops)} routed  |  skipped {len(result.skipped)}",
        f"Walk: {result.distance_m:.1f} m  ({result.walk_min:.1f} min @ {w.walk_speed_m_per_min:g} m/min)",
        f"Pick time: {result.pick_min:.1f} min  |  total {result.total_min:.1f} min",
        "",
        f"{'#':<4} {'SKU':<14} {'Aisle':>5} {'Bay':>4} {'Side':>4} {'Qty':>4}",
        "-" * 42,
    ]
    for stop in result.stops:
        p = stop.pick
        lines.append(
            f"{stop.seq:<4} {p.sku:<14} {p.aisle:>5} {p.bay:>4} {p.side:>4} {p.qty:>4}"
        )
    if result.skipped:
        lines.append("")
        lines.append("Skipped:")
        for item in result.skipped:
            lines.append(f"  {item['sku']}  {item['reason']}")
    lines.append("")
    lines.append("Strategy comparison (walk metres):")
    for name in ("s_shape", "return", "nearest"):
        marker = " ←" if name == result.chosen_strategy else ""
        lines.append(f"  {name.replace('_', '-'):<10} {result.comparison[name]:7.1f}{marker}")
    return "\n".join(lines) + "\n"
