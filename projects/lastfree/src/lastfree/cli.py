"""Command line for LastFree."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .clock import run_clock
from .model import Job
from .presets import PRESETS
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lastfree",
        description="Last-free-day, demurrage, and detention clock for a container.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    clock_cmd = sub.add_parser("clock", help="Run a container JSON file")
    clock_cmd.add_argument("path", type=Path)
    clock_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("presets", help="List terminal / line free-time presets")

    serve = sub.add_parser("serve", help="Open the local last-free-day board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8791)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            item = PRESETS[key]
            print(
                f"{key:<14} {item.name:<32} "
                f"dem {item.demurrage_free_days} {item.demurrage_day_type:<9} "
                f"det {item.detention_free_days} {item.detention_day_type}"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        result = run_clock(Job.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"lastfree: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.projected_usd == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
