"""Human-readable mode quotes."""

from __future__ import annotations

from .quote import QuoteResult


def text_report(result: QuoteResult) -> str:
    stats = result.stats
    winner = result.winner or "none"
    lines = [
        f"ModePick — {result.origin} → {result.destination}",
        f"Distance: {result.distance_km:.0f} km  |  "
        f"{stats.piece_count} piece(s)  |  {stats.weight_kg:.1f} kg  |  {stats.cube_m3:.3f} m³",
        f"Density: {stats.pcf:.1f} lb/ft³  →  class {stats.freight_class:g}",
        f"Winner: {winner.upper() if result.winner else 'NONE'}"
        + (f"  ${result.winner_usd:.2f}" if result.winner_usd is not None else "")
        + (f"  (saves ${result.savings_usd:.2f} vs next)" if result.savings_usd else ""),
        "",
        f"{'Mode':<8} {'Total':>10}  Detail",
        "-" * 72,
    ]
    for quote in result.quotes:
        if quote.feasible and quote.total_usd is not None:
            mark = "*" if quote.mode == result.winner else " "
            lines.append(f"{mark}{quote.name:<7} ${quote.total_usd:>8.2f}  {_detail_line(quote)}")
            for item in quote.lines:
                lines.append(f"         {item.label:<40} {item.amount_usd:>8.2f}")
        else:
            lines.append(f" {quote.name:<7} {'—':>9}  {quote.reason}")
    return "\n".join(lines) + "\n"


def _detail_line(quote) -> str:
    d = quote.detail
    if quote.mode == "parcel":
        return f"zone {d.get('zone')}  billable {d.get('billable_kg')} kg"
    if quote.mode == "ltl":
        return f"class {d.get('freight_class')}  {d.get('band')}  {d.get('cwt')} cwt"
    if quote.mode == "ftl":
        return str(d.get("truck_name") or d.get("truck") or "")
    return ""
