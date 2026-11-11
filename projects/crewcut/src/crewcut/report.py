"""Human-readable staffing reports."""

from __future__ import annotations

from .sites import fmt_hour, shift_label
from .staff import StaffResult


def text_report(result: StaffResult) -> str:
    site = result.site
    lines = [
        f"CrewCut — {site.name}",
        (
            f"Shift {shift_label(site.shift_start, site.shift_end)}  |  "
            f"labor ${result.labor_used:.0f} / ${result.labor_cap:.0f}  |  "
            f"heads {result.punched_count} / {result.head_cap}"
        ),
        (
            f"Covered {result.seated_count} slot(s)  |  leftover {result.leftover_heads}  |  "
            f"fill {result.fill_ratio:.0%}  |  OT {result.ot_count}"
        ),
        "",
        f"{'Hour':<6} {'Skill':<10} {'Who':<36} {'OT':<4} {'$':>7}",
        "-" * 68,
    ]
    seats = sorted(result.seats, key=lambda seat: (site.hour_index(seat.hour), seat.skill, seat.associate_id))
    for seat in seats:
        flag = "OT" if seat.ot else ""
        who = f"{seat.associate_id} {seat.name}"
        lines.append(
            f"{fmt_hour(seat.hour):<6} {seat.skill:<10} {who:<36} {flag:<4} {seat.cost:>7.2f}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not cover:")
        for item in result.leftover:
            equip = f" {item['equipment']}" if item.get("equipment") else ""
            lines.append(
                f"  {item['heads']} × {fmt_hour(int(item['hour']))} {item['skill']}{equip} "
                f"({item['temp']}) — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
