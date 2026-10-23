"""Human-readable sortation assignment reports."""

from __future__ import annotations

from .plan import PlanResult


def text_report(result: PlanResult) -> str:
    bank = result.bank
    lines = [
        f"ChuteDrop — {bank.name}",
        (
            f"{result.strategy}  |  {bank.rows}×{bank.cols} chutes  |  "
            f"{bank.temp}  |  labor {result.labor_used_min}/{result.labor_cap_min} min  |  "
            f"cap {bank.max_cartons}/chute"
        ),
        (
            f"Cartons {result.packed_cartons}/{result.carton_count}  |  "
            f"dests {result.dest_count}  |  "
            f"leftover {result.leftover_count}  |  chutes {result.chute_utilization:.0%}"
        ),
        "",
        f"{'SEQ':>3} {'CARTON':<10} {'DEST':<12} {'CARRIER':<8} "
        f"{'CHUTE':<6} {'ZONE':<10} {'PRIO':>4}",
        "-" * 64,
    ]
    for item in result.placements:
        lines.append(
            f"{item.seq:>3} {item.carton_id:<10} {item.dest:<12} {item.carrier:<8} "
            f"{item.chute:<6} {item.zone:<10} {item.priority:>4}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Left on the recirculation loop:")
        for item in result.leftover:
            lines.append(
                f"  {item['id']}: {item['dest']} via {item['carrier']} — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
