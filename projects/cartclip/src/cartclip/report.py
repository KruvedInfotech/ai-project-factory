"""Human-readable cluster reports."""

from __future__ import annotations

from .plan import PlanResult


def text_report(result: PlanResult) -> str:
    floor = result.warehouse
    cart = result.cart
    lines = [
        f"CartClip — {floor.name} / {cart.name}",
        (
            f"Floor: {'-'.join(floor.aisles)} × {floor.bays} bays  |  "
            f"cart {cart.tote_slots} totes · {cart.max_weight_kg:g} kg · "
            f"{cart.max_volume_l:g} L · {cart.temp} · span {cart.max_aisle_span}"
        ),
        (
            f"Clipped {result.clipped_count} order(s) onto {result.cart_count} cart(s)  |  "
            f"leftover {result.leftover_count}"
        ),
        (
            f"Labor: {result.labor_utilization:.1%}  "
            f"({result.labor_used_min}/{result.labor_cap_min} min)  |  "
            f"totes {result.tote_utilization:.1%}  |  strategy {result.strategy}"
        ),
        "",
        f"{'Cart':<6} {'Slot':<5} {'Order':<12} {'Pri':>3} {'Temp':<6} {'Aisles':<12} {'Lines':>5} {'kg':>7}",
        "-" * 70,
    ]
    for item in result.placements:
        aisles = ",".join(item.aisles)
        lines.append(
            f"{item.cart_id:<6} {item.slot:<5} {item.order_id:<12} {item.priority:>3} "
            f"{item.temp:<6} {aisles:<12} {item.line_count:>5} {item.weight_kg:>7.1f}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not clip:")
        for item in result.leftover:
            aisles = ",".join(str(a) for a in item["aisles"])
            lines.append(
                f"  {item['id']}  {item['temp']}  {aisles}  "
                f"{item['weight_kg']} kg  ({item['reason']})"
            )
    return "\n".join(lines) + "\n"
