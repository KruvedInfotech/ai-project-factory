"""Human-readable pad reports."""

from __future__ import annotations

from .place import PlanResult


def text_report(result: PlanResult) -> str:
    pad = result.pad
    lines = [
        f"HazPad — {pad.id}",
        (
            f"Bays {pad.bays}  |  compartments {pad.compartments}  |  "
            f"away {pad.away_bays}  |  empty-as-partition {str(pad.empty_as_partition).lower()}"
        ),
        (
            f"Placed {len(result.placements)} lot(s)  {result.placed_kg:g} kg  |  "
            f"leftover {len(result.leftover)}  {result.leftover_kg:g} kg  |  "
            f"worst {result.worst_code}"
        ),
        "",
        _bay_line(result),
        _label_line(result),
        "",
        f"{'LOT':<16} {'UN':<8} {'CLS':<5} {'BAY':>4} {'CMP':>3} {'kg':>8}",
        "-" * 52,
    ]
    for item in result.placements:
        lines.append(
            f"{item.lot:<16} {item.un or '—':<8} {item.clazz:<5} {item.bay:>4} "
            f"{item.compartment:>3} {item.kg:>8.1f}"
        )
    if result.pairs:
        lines.append("")
        lines.append("Pairs")
        for pair in result.pairs:
            eased = " LQ-eased" if pair.eased else ""
            lines.append(
                f"  {pair.lot_a} × {pair.lot_b}  {pair.class_a}×{pair.class_b}  "
                f"{pair.code}{eased}  {pair.share}  {pair.note}"
            )
    if result.leftover:
        lines.append("")
        lines.append("Could not stage:")
        for item in result.leftover:
            lines.append(
                f"  {item['lot']}  class {item['class']}  {item['kg']} kg  — {item['reason']}"
            )
    return "\n".join(lines) + "\n"


def _bay_line(result: PlanResult) -> str:
    cells = []
    for slot in result.as_dict()["bays"]:
        lot = slot["lot"]
        if lot is None:
            cells.append("[  . ]")
        else:
            cells.append(f"[{lot['class']:>4}]")
    return "Bay " + " ".join(f"{i:>6}" for i in range(result.pad.bays)) + "\n    " + " ".join(cells)


def _label_line(result: PlanResult) -> str:
    cells = []
    for slot in result.as_dict()["bays"]:
        lot = slot["lot"]
        cells.append(f"{(lot['lot'][:6] if lot else ''):>6}")
    return "    " + " ".join(cells)
