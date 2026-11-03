"""Command line for AisleLock."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .floors import FLOORS, STRATEGIES
from .lock import lock
from .model import Wave
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aislelock",
        description="Lock pick carts into aisle time windows (capacity, bulky exclusive, cutoff).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    lock_cmd = sub.add_parser("lock", help="Lock a wave JSON file onto the floor")
    lock_cmd.add_argument("path", type=Path)
    lock_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    lock_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the wave strategy")

    sub.add_parser("presets", help="List warehouse floor catalogs")

    serve = sub.add_parser("serve", help="Open the local aisle / Gantt map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8783)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(FLOORS):
            floor = FLOORS[key]
            print(
                f"{key:<10} {floor.name:<22} "
                f"{floor.aisle_ids[0]}-{floor.aisle_ids[-1]}  "
                f"cap {min(aisle.capacity for aisle in floor.aisles)}  "
                f"{floor.aisles[0].temp:<6}  "
                f"{floor.max_carts} carts  labor {floor.max_labor_min}m  "
                f"horizon {floor.horizon_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = lock(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
