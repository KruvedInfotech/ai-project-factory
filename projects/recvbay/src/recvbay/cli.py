"""Command line for RecvBay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .docks import DOCKS, STRATEGIES
from .model import Board
from .plan import plan
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="recvbay",
        description="Assign inbound ASNs to receiving doors (live vs drop, equipment, dwell).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dock_cmd = sub.add_parser("dock", help="Plan a receiving-board JSON file onto the dock")
    dock_cmd.add_argument("path", type=Path)
    dock_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    dock_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the board strategy")

    sub.add_parser("presets", help="List inbound-dock catalogs")

    serve = sub.add_parser("serve", help="Open the local receiving Gantt")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8785)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(DOCKS):
            dock = DOCKS[key]
            first, last = dock.doors[0], dock.doors[-1]
            print(
                f"{key:<10} {dock.name:<26} "
                f"{first.id}-{last.id}  "
                f"shift {dock.shift_end_min}m  "
                f"{first.temp:<6}  "
                f"labor {dock.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = plan(Board.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
