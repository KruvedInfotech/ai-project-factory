"""Human-readable allocation reports."""

from __future__ import annotations

from .push import PlanResult, SkuPlan


def text_report(result: PlanResult) -> str:
    pack_word = "inner" if result.break_case else "case"
    lines = [
        f"AllocPush — {result.wave}  {result.dc}",
        (
            f"Policy {result.policy.replace('_', ' ')} · holdback {result.holdback_pct:g}% · "
            f"packs {pack_word}"
        ),
        (
            f"SKUs {result.sku_count}  |  stores {result.store_count}  |  "
            f"push {result.push_units}  |  short {result.short_units}  |  "
            f"DC left {result.dc_remaining}"
        ),
        "",
        f"{'SKU':<12} {'DC':>6} {'pack':>5} {'need':>6} {'push':>6} {'short':>6} {'left':>6}  fill",
        "-" * 64,
    ]
    for sku in result.skus:
        lines.append(
            f"{sku.sku:<12} {sku.dc_on_hand:>6} {sku.pack:>5} {sku.need_units:>6} "
            f"{sku.push_units:>6} {sku.short_units:>6} {sku.dc_remaining:>6}  "
            f"{sku.fill_pct:.0%}"
        )
    for sku in result.skus:
        lines.append("")
        lines.extend(_sku_block(sku))
    return "\n".join(lines) + "\n"


def _sku_block(sku: SkuPlan) -> list[str]:
    hold = f"  holdback {sku.holdback_units}" if sku.holdback_units else ""
    lines = [
        f"{sku.sku}  {sku.description}  pack {sku.pack}{hold}".rstrip(),
        (
            f"{'store':<8} {'grd':<3} {'onh':>5} {'tgt':>5} "
            f"{'need':>5} {'push':>5} {'short':>5} {'cases':>5}"
        ),
        "-" * 50,
    ]
    for line in sku.lines:
        lines.append(
            f"{line.store_id:<8} {line.grade:<3} {line.on_hand:>5} {line.target:>5} "
            f"{line.need_units:>5} {line.push_units:>5} {line.short_units:>5} "
            f"{line.push_packs:>5}"
        )
    return lines
