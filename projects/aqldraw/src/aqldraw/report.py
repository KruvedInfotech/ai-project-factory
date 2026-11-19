"""Human-readable sampling reports."""

from __future__ import annotations

from .draw import LotPlan, PlanResult


def text_report(result: PlanResult) -> str:
    lines = [
        f"AqlDraw — {result.receipt}  {result.supplier}  {result.dock}",
        (
            f"Level {result.level} · severity {result.severity} · "
            f"switching {result.switching.replace('_', ' ')}"
        ),
        (
            f"Lots {len(result.lots)}  |  sample {result.sample_total}  |  "
            f"reject {result.reject_count}  |  pending {result.pending_count}"
        ),
        "",
        f"{'SKU':<12} {'N':>6} {'ltr':<4} {'n':>4}  classes (Ac/found)  verdict",
        "-" * 72,
    ]
    for lot in result.lots:
        classes = "  ".join(_class_cell(item) for item in lot.classes)
        flag = "  100%" if lot.hundred_percent else ""
        lines.append(
            f"{lot.sku:<12} {lot.lot_size:>6} {lot.letter:<4} {lot.sample_size:>4}  "
            f"{classes}  {lot.verdict.upper()}{flag}"
        )
    for lot in result.lots:
        lines.append("")
        lines.append(_draw_line(lot))
    return "\n".join(lines) + "\n"


def _class_cell(item) -> str:
    found = "—" if item.found is None else str(item.found)
    short = {"critical": "crit", "major": "maj", "minor": "min"}.get(item.name, item.name[:4])
    return f"{short} {item.ac}/{found}"


def _draw_line(lot: LotPlan) -> str:
    shown = lot.draw
    extra = ""
    if len(shown) > 80:
        extra = f" … +{len(shown) - 40} more"
        shown = lot.draw[:40]
    numbers = ", ".join(str(n) for n in shown)
    return f"Draw {lot.sku} ({lot.sample_size} of {lot.lot_size}): {numbers}{extra}"
