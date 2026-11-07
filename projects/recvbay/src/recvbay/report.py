"""Human-readable inbound dock reports."""

from __future__ import annotations

from .plan import PlanResult


def text_report(result: PlanResult) -> str:
    dock = result.dock
    lines = [
        f"RecvBay — {dock.name}",
        (
            f"Dock: {'-'.join(dock.door_ids)}  |  "
            f"{len(dock.doors)} door(s)  |  "
            f"shift {dock.shift_end_min} min"
        ),
        f"Docked {result.docked_count} load(s)  |  leftover {result.leftover_count}",
        (
            f"Labor: {result.labor_utilization:.1%}  "
            f"({result.labor_used_min}/{result.labor_cap_min} min)  |  "
            f"door time {result.door_time_utilization:.1%}  |  "
            f"strategy {result.strategy}"
        ),
        "",
        f"{'ASN':<12} {'Vendor':<10} {'Door':<4} {'Start':>5} {'End':>5} {'Pal':>4}  Unload  T",
        "-" * 72,
    ]
    for item in result.slots:
        lines.append(
            f"{item.load_id:<12} {item.vendor:<10} {item.door:<4} "
            f"{item.start_min:>5} {item.end_min:>5} {item.pallets:>4}  "
            f"{item.unload:<6}  {item.temp}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not dock:")
        for item in result.leftover:
            door = item.get("door") or "-"
            lines.append(
                f"  {item['id']}  {item['vendor']}  door {door}  {item['temp']}  "
                f"{item['unload']}  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
