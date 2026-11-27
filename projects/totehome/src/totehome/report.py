"""Human-readable milk-run reports."""

from __future__ import annotations

from .route import PlanResult, Trip


def text_report(result: PlanResult) -> str:
    lines = [
        f"ToteHome — {len(result.floor.carts)} cart(s), {len(result.floor.stations)} station(s)",
        (
            f"Trips {len(result.trips)}  |  collected {result.collected}  |  "
            f"leftover {len(result.leftover)}  |  residual {len(result.residual)}"
        ),
        f"Makespan {_clock(result.makespan_sec)}",
        "",
        f"{'CART':<6} {'TOTE':<8} {'HOME':<8} {'START':>8} {'FINISH':>8} {'TOTES':>6} {'STOPS'}",
        "-" * 68,
    ]
    for trip in result.trips:
        lines.append(_trip_line(trip))
        for stop in trip.stops:
            lines.append(
                f"       {stop.station:<8} {stop.totes:>4} totes  "
                f"{_clock(stop.arrive_sec):>8}–{_clock(stop.leave_sec):<8}  "
                f"{stop.stacks} stack(s)"
            )
    if result.leftover:
        lines.append("")
        lines.append("Could not clear:")
        for item in result.leftover:
            lines.append(
                f"  {item['station']}  {item['remaining']} × {item['tote']}  — {item['reason']}"
            )
    if result.residual:
        lines.append("")
        lines.append("Residual (below threshold):")
        for item in result.residual:
            lines.append(f"  {item['station']}  {item['remaining']} × {item['tote']}")
    return "\n".join(lines) + "\n"


def _trip_line(trip: Trip) -> str:
    stops = ",".join(stop.station for stop in trip.stops)
    return (
        f"{trip.cart:<6} {trip.tote:<8} {trip.home:<8} "
        f"{_clock(trip.start_sec):>8} {_clock(trip.finish_sec):>8} "
        f"{trip.collected:>6} {stops}"
    )


def _clock(sec: int) -> str:
    hours, rem = divmod(int(sec), 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
