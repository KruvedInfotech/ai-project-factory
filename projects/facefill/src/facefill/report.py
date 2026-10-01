"""Human-readable replenishment reports."""

from __future__ import annotations

from .fill import FillResult


def text_report(result: FillResult) -> str:
    house = result.warehouse
    lines = [
        f"FaceFill — {house.name}",
        (
            f"Layout: {house.aisle_count}×{house.bays_per_aisle}"
            f"  |  strategy {result.strategy}"
            f"  |  cap {house.max_tasks} tasks / {house.max_labor_min} min"
        ),
        (
            f"Tasks {result.task_count}"
            f"  |  cases {result.case_count}"
            f"  |  labor {result.labor_min} min ({result.labor_fill:.1%})"
            f"  |  leftover {result.leftover_count}"
            f"  |  healthy after {result.healthy_after}/{len(result.faces)}"
        ),
        "",
        (
            f"{'Face':<10} {'SKU':<12} {'Loc':<7} {'OH':>4} {'Dem':>4} "
            f"{'Min':>4} {'Max':>4} {'Cs':>3} {'After':>5} {'Trig'}"
        ),
        "-" * 82,
    ]
    for task in result.tasks:
        loc = f"A{task.face.aisle}-{task.face.bay:02d}"
        lines.append(
            f"{task.face.id:<10} {task.face.sku:<12} {loc:<7} "
            f"{task.face.on_hand:>4} {task.demand:>4} "
            f"{task.face.min_qty:>4} {task.face.max_qty:>4} "
            f"{task.cases:>3} {task.after_qty:>5} {task.trigger}"
        )
        for pull in task.pulls:
            lines.append(
                f"           ↳ {pull.cases} case(s) from {pull.reserve_id} (aisle {pull.aisle})"
            )
    if result.leftover:
        lines.append("")
        lines.append("Could not fill:")
        for item in result.leftover:
            lines.append(f"  {item['id']} — {item['reason']}")
    return "\n".join(lines) + "\n"
