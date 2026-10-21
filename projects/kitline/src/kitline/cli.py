"""Command line for KitLine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .lines import PRESETS, STRATEGIES
from .model import Wave
from .plan import plan_line
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kitline",
        description="Assign kit builds to workbenches (one build per bench, BOM inventory).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Plan a wave JSON file onto a kitting line")
    plan_cmd.add_argument("path", type=Path)
    plan_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    plan_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the wave strategy")

    sub.add_parser("presets", help="List kitting-line presets")

    serve = sub.add_parser("serve", help="Open the local line map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8778)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            line = PRESETS[key]
            print(
                f"{key:<12} {line.name:<20} "
                f"{line.rows}×{line.cols}  "
                f"{line.length_mm}×{line.width_mm}×{line.height_mm} mm  "
                f"{line.temp:<8}  {line.max_weight_kg:g} kg  "
                f"run {line.max_run}  {line.minutes_per_kit} min/kit  labor {line.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = plan_line(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
