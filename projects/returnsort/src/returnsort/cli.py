"""Command line for ReturnSort."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .floors import PRESETS
from .model import ReturnBatch
from .plan import plan
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="returnsort", description="Park returns into disposition lanes.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Plan a returns JSON file")
    plan_cmd.add_argument("path", type=Path)
    plan_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("floors", help="List returns-floor presets")

    serve = sub.add_parser("serve", help="Open the local returns planner")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.command == "floors":
        for key in sorted(PRESETS):
            floor = PRESETS[key]
            print(f"{key:<16} {floor.name:<28} {len(floor.lanes)} lanes  {floor.slot_count} slots")
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    result = plan(ReturnBatch.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_parked else 2


if __name__ == "__main__":
    raise SystemExit(main())
