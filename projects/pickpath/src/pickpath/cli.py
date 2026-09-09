"""Command line for PickPath."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Wave
from .report import text_report
from .route import route
from .warehouse import PRESETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pickpath", description="Plan a warehouse pick path.")
    sub = parser.add_subparsers(dest="command", required=True)

    route_cmd = sub.add_parser("route", help="Route a pick-wave JSON file")
    route_cmd.add_argument("path", type=Path)
    route_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    route_cmd.add_argument(
        "--strategy",
        choices=("auto", "s_shape", "return", "nearest"),
        help="Override the strategy in the file",
    )

    sub.add_parser("presets", help="List warehouse layout presets")

    serve = sub.add_parser("serve", help="Open the local pick-path planner")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8766)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            item = PRESETS[key]
            rear = "rear" if item.has_rear else "front-only"
            print(
                f"{key:<18} {item.name:<24} {item.aisle_count}×{item.bays_per_aisle}  "
                f"pitch {item.aisle_pitch_m:g} m  {rear}"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = route(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_routed else 2


if __name__ == "__main__":
    raise SystemExit(main())
