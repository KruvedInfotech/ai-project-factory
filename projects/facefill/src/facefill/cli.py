"""Command line for FaceFill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .fill import fill
from .model import FillPlan
from .report import text_report
from .warehouses import PRESETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="facefill", description="Plan pick-face replenishment from reserve."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fill_cmd = sub.add_parser("fill", help="Fill a replenishment-plan JSON file")
    fill_cmd.add_argument("path", type=Path)
    fill_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    fill_cmd.add_argument(
        "--strategy",
        choices=("auto", "urgent", "demand", "cluster"),
        help="Override the plan strategy",
    )

    sub.add_parser("presets", help="List warehouse presets")

    serve = sub.add_parser("serve", help="Open the local face board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8769)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            house = PRESETS[key]
            print(
                f"{key:<14} {house.name:<28} "
                f"{house.aisle_count}×{house.bays_per_aisle}  "
                f"{house.max_tasks} tasks  "
                f"{house.max_labor_min} min  "
                f"{house.minutes_per_task}+{house.aisle_change_min} travel"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = fill(FillPlan.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_filled else 2


if __name__ == "__main__":
    raise SystemExit(main())
