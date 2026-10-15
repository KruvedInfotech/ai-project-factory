"""Human-readable cycle-count reports."""

from __future__ import annotations

from .sweep import SweepResult


def _overdue_label(days_since: int | None, overdue: int | None) -> str:
    if days_since is None:
        return "never"
    return str(overdue if overdue is not None else 0)


def _notes(item) -> str:
    parts: list[str] = []
    if item.high_shrink:
        parts.append("shrink")
    if item.flag:
        parts.append("flag")
    if item.freeze:
        parts.append("freeze")
    return ",".join(parts)


def text_report(result: SweepResult) -> str:
    policy = result.policy
    skip = "skip-empty" if policy.skip_empty else "count-zeros"
    freeze = "freeze" if policy.freeze_on_count else "no-freeze"
    lines = [
        f"CountSweep — {policy.name}",
        (
            f"{result.strategy}  |  {policy.cycle_a_days}/{policy.cycle_b_days}/{policy.cycle_c_days}d  |  "
            f"{skip}  |  {freeze}  |  labor {result.labor_used_min}/{result.labor_cap_min} min"
        ),
        (
            f"Due {result.due_count}  |  walk {result.scheduled_count}  |  leftover {result.leftover_count}  |  "
            f"flags {result.flag_count}  |  cover {result.cover_rate:.0%}"
        ),
        "",
        f"{'SEQ':>3} {'LOC':<12} {'SKU':<12} {'ABC':<3} {'A':>2} {'B':>2} {'L':>2} "
        f"{'BOOK':>5} {'OVER':>5} {'MIN':>3} {'NOTE':<12}",
        "-" * 78,
    ]
    for item in result.counts:
        overdue = _overdue_label(item.days_since, None if item.days_since is None else item.overdue_days)
        lines.append(
            f"{item.seq:>3} {item.location_id:<12} {item.sku:<12} {item.abc:<3} "
            f"{item.aisle:>2} {item.bay:>2} {item.level:>2} "
            f"{item.book_qty:>5} {overdue:>5} {item.minutes:>3} {_notes(item):<12}"
        )
    if result.leftover:
        lines.append("")
        lines.append("Could not count:")
        for item in result.leftover:
            overdue = _overdue_label(item.get("days_since"), item.get("overdue_days"))
            sku = item["sku"] or "empty"
            lines.append(
                f"  {item['id']}: {sku} {item['abc']} aisle {item['aisle']} "
                f"over {overdue} — {item['reason']}"
            )
    return "\n".join(lines) + "\n"
