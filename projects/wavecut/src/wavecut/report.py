"""Human-readable wave reports."""

from __future__ import annotations

from .cut import CutResult
from .shifts import format_hhmm


def text_report(result: CutResult) -> str:
    shift = result.shift
    lines = [
        f"WaveCut — {shift.name}",
        (
            f"Hours: {format_hhmm(shift.open_min)}–{format_hhmm(shift.close_min)}"
            f"  |  wave {shift.wave_min} min"
            f"  |  strategy {result.strategy}"
            f"  |  zone-pure {'yes' if shift.zone_pure else 'no'}"
        ),
        (
            f"Assigned {result.assigned_count} order(s)  |  leftover {result.leftover_count}"
            f"  |  pick fill {result.utilization:.1%}"
            f"  |  cube fill {result.cube_utilization:.1%}"
        ),
        "",
        (
            f"{'Wave':<5} {'Start':>5} {'End':>5} {'Zone':<8} "
            f"{'Id':<12} {'Chan':<10} {'Ln':>3} {'m³':>6} {'pick':>4} {'Cut':>5}"
        ),
        "-" * 78,
    ]
    for item in result.assignments:
        order = item.order
        lines.append(
            f"{item.wave.id:<5} {format_hhmm(item.wave.start_min):>5} "
            f"{format_hhmm(item.wave.end_min):>5} {(item.wave.zone or '-'):<8} "
            f"{order.id:<12} {order.channel:<10} {order.lines:>3} "
            f"{order.cube_m3:>6.2f} {order.pick_min:>4} {order.cutoff:>5}"
        )
    lines.append("")
    lines.append("Wave fill:")
    for wave in result.waves:
        if not wave.orders and not any(
            later.orders for later in result.waves if later.start_min > wave.start_min
        ):
            continue
        lines.append(
            f"  {wave.id:<4} {format_hhmm(wave.start_min)}–{format_hhmm(wave.end_min)}  "
            f"{(wave.zone or '-'):<8} "
            f"{len(wave.orders):>2} ord  {wave.lines:>3} ln  "
            f"{wave.cube_m3:>5.2f} m³  {wave.pick_min:>3} min"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not cut:")
        for item in result.leftover:
            lines.append(f"  {item['id']} — {item['reason']}")
    return "\n".join(lines) + "\n"
