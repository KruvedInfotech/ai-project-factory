"""Human-readable aisle-lock reports."""

from __future__ import annotations

from .lock import LockResult


def text_report(result: LockResult) -> str:
    floor = result.floor
    lines = [
        f"AisleLock — {floor.name}",
        (
            f"Floor: {'-'.join(floor.aisle_ids)}  |  "
            f"horizon {floor.horizon_min} min  |  "
            f"max {floor.max_carts} cart(s)"
        ),
        (
            f"Locked {result.locked_count} cart(s)  |  leftover {result.leftover_count}"
        ),
        (
            f"Labor: {result.labor_utilization:.1%}  "
            f"({result.labor_used_min}/{result.labor_cap_min} min)  |  "
            f"horizon {result.horizon_utilization:.1%}  |  "
            f"strategy {result.strategy}"
        ),
        "",
        f"{'Cart':<12} {'Pri':>3} {'T':<6} {'Start':>5} {'End':>5} {'Min':>5}  Walk",
        "-" * 72,
    ]
    for item in result.locks:
        walk = ", ".join(f"{visit.aisle} {visit.start_min}-{visit.end_min}" for visit in item.visits)
        bulky = "B" if item.bulky else " "
        lines.append(
            f"{item.cart_id:<12} {item.priority:>3} {item.temp:<5}{bulky} "
            f"{item.start_min:>5} {item.end_min:>5} {item.labor_min:>5}  {walk}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not lock:")
        for item in result.leftover:
            walk = ", ".join(step["aisle"] for step in item["walk"])
            lines.append(
                f"  {item['id']}  {item['temp']}  walk {walk}  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
