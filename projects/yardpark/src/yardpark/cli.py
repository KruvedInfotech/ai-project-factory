"""Command line for YardPark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import YardPlan
from .park import park
from .report import text_report
from .yards import PRESETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yardpark", description="Park trailers on a yard and sequence pull-to-door moves."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    park_cmd = sub.add_parser("park", help="Park a yard-plan JSON file")
    park_cmd.add_argument("path", type=Path)
    park_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    park_cmd.add_argument(
        "--strategy",
        choices=("auto", "door", "dwell", "pull"),
        help="Override the plan strategy",
    )

    sub.add_parser("presets", help="List yard presets")

    serve = sub.add_parser("serve", help="Open the local yard board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8772)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            yard = PRESETS[key]
            reefer = sum(1 for spot in yard.spots if spot.kind in {"reefer", "power"})
            print(
                f"{key:<10} {yard.name:<22} "
                f"{yard.open}–{yard.close}  "
                f"{len(yard.spots)} spots  "
                f"{reefer} plug  "
                f"{yard.max_moves} moves  "
                f"{yard.max_labor_min} min"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = park(YardPlan.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_clear else 2


if __name__ == "__main__":
    raise SystemExit(main())
