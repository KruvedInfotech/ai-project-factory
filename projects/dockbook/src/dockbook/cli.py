"""Command line for DockBook."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .book import book
from .model import DayPlan
from .report import text_report
from .yards import PRESETS, format_hhmm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dockbook", description="Book trailers onto dock doors."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    book_cmd = sub.add_parser("book", help="Book a day-plan JSON file")
    book_cmd.add_argument("path", type=Path)
    book_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    book_cmd.add_argument(
        "--strategy",
        choices=("auto", "earliest", "preferred", "spread"),
        help="Override the plan strategy",
    )

    sub.add_parser("presets", help="List yard presets")

    serve = sub.add_parser("serve", help="Open the local dock board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8767)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            yard = PRESETS[key]
            print(
                f"{key:<14} {yard.name:<28} "
                f"{format_hhmm(yard.open_min)}–{format_hhmm(yard.close_min)}  "
                f"{len(yard.doors)} doors  turn {yard.turnaround_min} min"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = book(DayPlan.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_booked else 2


if __name__ == "__main__":
    raise SystemExit(main())
