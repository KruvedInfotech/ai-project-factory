"""Command line for FlowMatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .match import match
from .model import FlowPlan
from .report import text_report
from .yards import PRESETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flowmatch", description="Match inbound receipts to outbound orders on a cross-dock."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    match_cmd = sub.add_parser("match", help="Match a flow-plan JSON file")
    match_cmd.add_argument("path", type=Path)
    match_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    match_cmd.add_argument(
        "--strategy",
        choices=("auto", "cutoff", "lane", "live"),
        help="Override the plan strategy",
    )

    sub.add_parser("presets", help="List yard presets")

    serve = sub.add_parser("serve", help="Open the local flow board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8771)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            yard = PRESETS[key]
            print(
                f"{key:<12} {yard.name:<24} "
                f"{yard.open}–{yard.close}  "
                f"{len(yard.lanes)} lanes  "
                f"{yard.max_matches} matches  "
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
    result = match(FlowPlan.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_clear else 2


if __name__ == "__main__":
    raise SystemExit(main())
