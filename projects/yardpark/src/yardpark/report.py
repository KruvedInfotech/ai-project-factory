"""Human-readable yard reports."""

from __future__ import annotations

from .park import YardResult


def text_report(result: YardResult) -> str:
    yard = result.yard
    lines = [
        f"YardPark — {yard.name}",
        (
            f"Hours: {yard.open}–{yard.close}  |  "
            f"{len(yard.spots)} spots  |  {result.strategy}"
        ),
        (
            f"Parked {result.parked_count} trailer(s)  |  "
            f"pulls {result.pull_count}  |  leftover {result.leftover_count}  |  "
            f"fill {result.fill_rate:.0%}"
        ),
        f"Labor: {result.labor_min} min of {yard.max_labor_min}",
        "",
        f"{'TRAILER':<10} {'SPOT':<6} {'ROW':<4} {'KIND':<8} {'TEMP':<6} "
        f"{'DOOR':<4} {'AVAIL':>5} {'PULL':<5}",
        "-" * 64,
    ]
    pulled = {item.trailer_id: item for item in result.pulls}
    for item in result.parked:
        pull = pulled.get(item.trailer_id)
        pull_clock = pull.start if pull else "—"
        lines.append(
            f"{item.trailer_id:<10} {item.spot_id:<6} {item.row:<4} {item.kind:<8} "
            f"{item.temp:<6} {(item.door or '—'):<4} {item.available:>5} {pull_clock:<5}"
        )
    if result.pulls:
        lines.append("")
        lines.append("Pull sequence:")
        for item in result.pulls:
            lines.append(
                f"  {item.start}–{item.ready}  {item.trailer_id}  "
                f"{item.spot_id} → {item.door}  ({item.labor_min} min)"
            )
    if result.held:
        lines.append("")
        lines.append("Parked, not pulled:")
        for item in result.held:
            lines.append(f"  {item['id']}: {item.get('spot_id', '—')} — {item['reason']}")
    if result.leftover:
        lines.append("")
        lines.append("Could not park:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}: {item['kind']} {item['temp']} "
                f"{item['length_ft']}ft — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
