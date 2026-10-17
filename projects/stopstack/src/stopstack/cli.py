"""Command line for StopStack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Load
from .report import text_report
from .stack import stack
from .trailers import PRESETS, STRATEGIES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stopstack",
        description="Stack a multi-stop trailer last-delivery-first (LIFO).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    stack_cmd = sub.add_parser("stack", help="Stack a milk-run JSON file")
    stack_cmd.add_argument("path", type=Path)
    stack_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    stack_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the load strategy")

    sub.add_parser("presets", help="List trailer deck presets")

    serve = sub.add_parser("serve", help="Open the local trailer map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8776)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            trailer = PRESETS[key]
            stack_label = "2-high" if trailer.stack_levels == 2 else "floor"
            print(
                f"{key:<14} {trailer.name:<20} "
                f"{trailer.rows}×{trailer.cols} {stack_label:<6}  "
                f"{trailer.temp:<6}  {trailer.max_weight_kg:g} kg  "
                f"{trailer.minutes_per_pallet} min/pal  labor {trailer.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = stack(Load.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
