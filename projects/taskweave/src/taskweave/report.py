"""Human-readable task-interleave reports."""

from __future__ import annotations

from .weave import WeaveResult


def text_report(result: WeaveResult) -> str:
    floor = result.floor
    truck_ids = " ".join(truck.id for truck in floor.trucks)
    lines = [
        f"TaskWeave — {floor.name}",
        (
            f"Fleet: {truck_ids}  |  "
            f"{len(floor.trucks)} truck(s)  |  "
            f"shift {floor.shift_end_min} min"
        ),
        f"Weaved {result.weaved_count} task(s)  |  leftover {result.leftover_count}  |  dual {result.dual_count}",
        (
            f"Labor: {result.labor_utilization:.1%}  "
            f"({result.labor_used_min}/{result.labor_cap_min} min)  |  "
            f"deadhead {result.deadhead_ratio:.1%}  |  "
            f"strategy {result.strategy}"
        ),
        "",
        f"{'Task':<10} {'Kind':<8} {'Truck':<6} {'From':<6} {'To':<6} {'Start':>5} {'End':>5}  Dual",
        "-" * 72,
    ]
    for item in result.legs:
        dual = "yes" if item.dual else "no"
        lines.append(
            f"{item.task_id:<10} {item.kind:<8} {item.truck_id:<6} "
            f"{item.pickup:<6} {item.drop:<6} "
            f"{item.start_min:>5} {item.end_min:>5}  {dual}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not weave:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}  {item['kind']}  {item['from']}→{item['to']}  "
                f"{item['temp']}  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
