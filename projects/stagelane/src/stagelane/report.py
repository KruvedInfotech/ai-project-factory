"""Human-readable staging-lane reports."""

from __future__ import annotations

from .seat import SeatResult


def text_report(result: SeatResult) -> str:
    yard = result.yard
    lines = [
        f"StageLane — {yard.name}",
        (
            f"Yard: {'-'.join(yard.lane_ids)}  |  "
            f"{len(yard.lanes)} lane(s)  |  "
            f"max {yard.max_pallets} pallet(s)"
        ),
        f"Seated {result.seated_count} pallet(s)  |  leftover {result.leftover_count}",
        (
            f"Labor: {result.labor_utilization:.1%}  "
            f"({result.labor_used_min}/{result.labor_cap_min} min)  |  "
            f"length {result.length_utilization:.1%}  |  "
            f"strategy {result.strategy}"
        ),
        "",
        f"{'Pallet':<12} {'Carr':<6} {'Lane':<4} {'Door':>4} {'Xmm':>6} {'Len':>6} {'Stk':>3}  T",
        "-" * 72,
    ]
    for item in result.seats:
        door = "-" if item.door is None else str(item.door)
        lines.append(
            f"{item.pallet_id:<12} {item.carrier:<6} {item.lane:<4} {door:>4} "
            f"{item.x_mm:>6} {item.length_mm:>6} {item.stack_level:>3}  {item.temp}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not seat:")
        for item in result.leftover:
            door = item.get("door") or "-"
            lines.append(
                f"  {item['id']}  {item['carrier']}  door {door}  {item['temp']}  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
