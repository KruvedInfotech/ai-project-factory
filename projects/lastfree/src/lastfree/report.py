"""Human-readable clock reports."""

from __future__ import annotations

from .clock import ClockResult

STATUS_LABEL = {
    "not_yet_available": "not yet available",
    "inside_free": "inside free time",
    "demurrage_running": "demurrage running",
    "on_street_free": "on street, free time",
    "detention_running": "detention running",
    "closed": "returned / closed",
}


def money(value: float) -> str:
    return f"${value:,.2f}"


def text_report(result: ClockResult) -> str:
    job = result.job
    preset = job.preset
    lines = [
        f"LastFree — {job.container}  {job.size}'",
        f"Clock: {preset.name}  |  as of {job.as_of.isoformat()}  |  {STATUS_LABEL.get(result.status, result.status)}",
        f"Available {job.available_on.isoformat()}  |  gate-out {job.gate_out_on or '—'}  |  empty {job.empty_return_on or '—'}",
        "",
        f"Demurrage LFD  {result.demurrage_lfd.isoformat()}   ({preset.demurrage_free_days} {preset.demurrage_day_type} free)",
        f"  charge days {result.demurrage_days:<4}  projected {money(result.demurrage_usd):>12}  accrued {money(result.accrued_demurrage_usd)}",
    ]
    if result.detention_lfd is None:
        lines.append("Detention LFD   —  (needs gate-out)")
    else:
        lines.append(
            f"Detention LFD   {result.detention_lfd.isoformat()}   ({preset.detention_free_days} {preset.detention_day_type} free)"
        )
    lines.append(
        f"  charge days {result.detention_days:<4}  projected {money(result.detention_usd):>12}  accrued {money(result.accrued_detention_usd)}"
    )
    lines.append("")
    lines.append(f"Projected total {money(result.projected_usd)}   |   accrued through as-of {money(result.accrued_usd)}")
    if result.days_until_lfd is not None:
        if result.days_until_lfd > 0:
            lines.append(f"Calendar days until demurrage LFD: {result.days_until_lfd}")
        elif result.days_until_lfd == 0:
            lines.append("Today is demurrage last free day — pickup today is still free.")
        else:
            lines.append(f"Demurrage LFD was {-result.days_until_lfd} calendar day(s) ago.")
    lines.append("")
    lines.append(f"{'Date':<12} {'Day':<4} {'Flags':<28} {'Demurrage':>10} {'Detention':>10}")
    lines.append("-" * 68)
    for cell in result.calendar:
        flags = ",".join(cell.flags) if cell.flags else ("holiday" if cell.holiday else ("skip" if cell.skipped else ""))
        lines.append(
            f"{cell.date.isoformat():<12} {cell.weekday:<4} {flags:<28} "
            f"{money(cell.demurrage_usd):>10} {money(cell.detention_usd):>10}"
        )
    return "\n".join(lines) + "\n"
