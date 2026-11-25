"""Human-readable VAS board reports."""

from __future__ import annotations

from .schedule import PlanResult, Task


def text_report(result: PlanResult) -> str:
    lines = [
        f"VasLine — {len(result.benches)} bench(es)",
        (
            f"Scheduled {len(result.scheduled)} job(s)  |  leftover {len(result.leftover)}  |  "
            f"tardy {result.tardy_count}"
        ),
        (
            f"Makespan {_clock(result.makespan_sec)}  |  "
            f"bench use {result.bench_utilization:.1%}"
        ),
        "",
        f"{'BENCH':<8} {'JOB':<12} {'OP':<8} {'SETUP':>5} {'START':>8} {'FINISH':>8} {'UNITS':>6}",
        "-" * 64,
    ]
    for task in result.tasks:
        lines.append(_task_line(task))
    if result.scheduled:
        tardy = [item for item in result.scheduled if item.tardy]
        if tardy:
            lines.append("")
            lines.append("Tardy:")
            for item in tardy:
                due = "—" if item.due_min is None else _clock(item.due_min * 60)
                lines.append(
                    f"  {item.job}  finished {_clock(item.finish_sec)}  due {due}  "
                    f"+{_clock(item.tardy_sec)}"
                )
    if result.leftover:
        lines.append("")
        lines.append("Could not stage:")
        for item in result.leftover:
            lines.append(
                f"  {item['job']}  {item['units']} × {item['sku']}  — {item['reason']}"
            )
    return "\n".join(lines) + "\n"


def _task_line(task: Task) -> str:
    setup = f"{task.setup_sec:>4}s" if task.setup_sec else "    —"
    return (
        f"{task.bench:<8} {task.job:<12} {task.op:<8} {setup:>5} "
        f"{_clock(task.start_sec):>8} {_clock(task.finish_sec):>8} {task.units:>6}"
    )


def _clock(sec: int) -> str:
    hours, rem = divmod(int(sec), 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
