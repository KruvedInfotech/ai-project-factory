"""Command line for CountSweep."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Wave
from .policies import PRESETS, STRATEGIES
from .report import text_report
from .sweep import sweep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="countsweep", description="Plan ABC cycle-count walks for warehouse locations."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Plan a count-walk JSON file")
    plan_cmd.add_argument("path", type=Path)
    plan_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    plan_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the wave strategy")
    plan_cmd.add_argument("--as-of", dest="as_of", help="Override as-of date (YYYY-MM-DD)")

    sub.add_parser("presets", help="List cycle-count policy presets")

    serve = sub.add_parser("serve", help="Open the local count board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8775)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            policy = PRESETS[key]
            skip = "skip-empty" if policy.skip_empty else "count-zeros"
            freeze = "freeze" if policy.freeze_on_count else "no-freeze"
            print(
                f"{key:<14} {policy.name:<16} "
                f"{policy.cycle_a_days}/{policy.cycle_b_days}/{policy.cycle_c_days}d  "
                f"{skip:<11} {freeze:<9}  "
                f"{policy.minutes_per_count} min/count  "
                f"labor {policy.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    if args.as_of:
        payload["as_of"] = args.as_of
    result = sweep(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_clear else 2


if __name__ == "__main__":
    raise SystemExit(main())
