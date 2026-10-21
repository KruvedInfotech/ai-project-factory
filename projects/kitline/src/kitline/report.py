"""Human-readable kitting-line assignment reports."""

from __future__ import annotations

from .plan import PlanResult


def text_report(result: PlanResult) -> str:
    line = result.line
    lines = [
        f"KitLine — {line.name}",
        (
            f"{result.strategy}  |  {line.rows}×{line.cols} benches  |  "
            f"{line.temp}  |  labor {result.labor_used_min}/{result.labor_cap_min} min  |  "
            f"run cap {line.max_run}"
        ),
        (
            f"Kits {result.packed_kits}/{result.kit_count}  |  "
            f"builds {result.packed_builds}/{result.build_count}  |  "
            f"leftover {result.leftover_count}  |  benches {result.bench_utilization:.0%}"
        ),
        "",
        f"{'SEQ':>3} {'BUILD':<10} {'KIT':<12} {'QTY':>4} "
        f"{'BENCH':<6} {'ZONE':<6} {'MIN':>4} {'PRIO':>4}",
        "-" * 62,
    ]
    for item in result.placements:
        lines.append(
            f"{item.seq:>3} {item.build_id:<10} {item.kit_sku:<12} {item.quantity:>4} "
            f"{item.bench:<6} {item.zone:<6} {item.minutes:>4} {item.priority:>4}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Left on the kit cart:")
        for item in result.leftover:
            extra = ""
            if item["reason"] == "short":
                extra = f" ({item.get('missing_sku')} need {item.get('need')} have {item.get('on_hand')})"
            lines.append(
                f"  {item['id']}: {item['quantity']}× {item['kit_sku']} — {item['reason']}{extra}"
            )
    return "\n".join(lines) + "\n"
