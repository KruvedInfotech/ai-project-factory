"""Command line for WallSort."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Batch
from .report import text_report
from .sort import sort_wall
from .walls import PRESETS, STRATEGIES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wallsort",
        description="Assign batch-picked orders to put-wall cubbies (one order per cubby).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sort_cmd = sub.add_parser("sort", help="Sort a batch JSON file onto a wall")
    sort_cmd.add_argument("path", type=Path)
    sort_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    sort_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the batch strategy")

    sub.add_parser("presets", help="List put-wall presets")

    serve = sub.add_parser("serve", help="Open the local wall map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8777)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            wall = PRESETS[key]
            print(
                f"{key:<12} {wall.name:<18} "
                f"{wall.rows}×{wall.cols}  "
                f"{wall.length_mm}×{wall.width_mm}×{wall.height_mm} mm  "
                f"{wall.temp:<8}  {wall.max_weight_kg:g} kg  "
                f"{wall.minutes_per_unit} min/unit  labor {wall.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = sort_wall(Batch.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
