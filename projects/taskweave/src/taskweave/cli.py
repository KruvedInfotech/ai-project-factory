"""Command line for TaskWeave."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .floors import FLOORS, STRATEGIES
from .model import Board
from .report import text_report
from .weave import weave


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="taskweave",
        description="Interleave putaway, replen, and pick tasks onto forklifts (dual-cycle, deadhead).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    weave_cmd = sub.add_parser("weave", help="Plan a task-board JSON file onto the fleet")
    weave_cmd.add_argument("path", type=Path)
    weave_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    weave_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the board strategy")

    sub.add_parser("presets", help="List warehouse-floor catalogs")

    serve = sub.add_parser("serve", help="Open the local floor map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8786)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(FLOORS):
            floor = FLOORS[key]
            trucks = ",".join(truck.id for truck in floor.trucks)
            print(
                f"{key:<10} {floor.name:<28} "
                f"{len(floor.locations):>3} loc  "
                f"{trucks:<22}  "
                f"shift {floor.shift_end_min}m  "
                f"labor {floor.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = weave(Board.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
