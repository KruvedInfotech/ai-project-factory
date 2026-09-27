"""Human-readable booking reports."""

from __future__ import annotations

from .book import BookResult
from .yards import format_hhmm


def text_report(result: BookResult) -> str:
    yard = result.yard
    lines = [
        f"DockBook — {yard.name}",
        (
            f"Hours: {format_hhmm(yard.open_min)}–{format_hhmm(yard.close_min)}"
            f"  |  turnaround {yard.turnaround_min} min"
            f"  |  strategy {result.strategy}"
        ),
        (
            f"Booked {len(result.bookings)} trailer(s)  |  leftover {len(result.leftover)}"
            f"  |  door fill {result.utilization:.1%}"
        ),
        "",
        f"{'Door':<6} {'Start':>5} {'End':>5} {'Id':<12} {'Carrier':<14} {'Dir':<9} {'Temp':<6} {'min':>4}",
        "-" * 72,
    ]
    for item in sorted(result.bookings, key=lambda row: (row.door_id, row.start_min)):
        trailer = item.trailer
        lines.append(
            f"{item.door_id:<6} {format_hhmm(item.start_min):>5} {format_hhmm(item.end_min):>5} "
            f"{trailer.id:<12} {trailer.carrier:<14} {trailer.direction:<9} {trailer.temp:<6} "
            f"{trailer.duration_min:>4}"
        )
    lines.append("")
    lines.append("Door fill:")
    used = result.door_minutes
    for door in yard.doors:
        share = used[door.id] / yard.span_min if yard.span_min else 0.0
        lines.append(
            f"  {door.id:<4} {door.name:<28} {used[door.id]:>4} min  {share:5.1%}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not book:")
        for item in result.leftover:
            lines.append(f"  {item['id']} — {item['reason']}")
    return "\n".join(lines) + "\n"
