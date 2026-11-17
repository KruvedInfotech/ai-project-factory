"""Human-readable cutoff reports."""

from __future__ import annotations

from .plan import PlanResult


def text_report(result: PlanResult) -> str:
    winner = result.winner_name.upper() if result.winner_name else "NONE"
    clock = (
        f"{result.soonest_cutoff_minutes} min to soonest making cutoff"
        if result.soonest_cutoff_minutes is not None
        else "no same-day cutoff still open"
    )
    lines = [
        f"ShipCut — {result.origin} → {result.destination}",
        f"Ready: {result.ready_at.replace('T', ' ')}  |  promised {result.promised_on}  |  "
        f"zone {result.zone} ({result.zone_name})",
        f"{result.piece_count} piece(s)  |  {result.weight_kg:.1f} kg  |  longest {result.longest_cm:g} cm",
        f"Winner: {winner}  |  {result.makes_sla_count} carrier(s) make the promise  |  {clock}",
        "",
        f"{'':1}{'Carrier':<18} {'Status':<14} {'Pickup':<20} {'Delivers':<12}  Note",
        "-" * 88,
    ]
    for item in result.plans:
        mark = "*" if item.carrier == result.winner else " "
        pickup = (item.pickup_at or "—").replace("T", " ")
        delivers = item.delivery_on or "—"
        note = item.reason or (f"{item.minutes_remaining} min left" if item.minutes_remaining is not None else "")
        lines.append(
            f"{mark}{item.name:<18} {item.status:<14} {pickup:<20} {delivers:<12}  {note}"
        )
    return "\n".join(lines) + "\n"
