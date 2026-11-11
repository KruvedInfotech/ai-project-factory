"""Command line for CrewCut."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Board
from .report import text_report
from .sites import PRESETS, STRATEGIES, shift_label
from .staff import staff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crewcut",
        description="Seat a warehouse crew onto a demand curve (skills, OT, breaks, labor cap).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    staff_cmd = sub.add_parser("staff", help="Plan a staffing-board JSON file")
    staff_cmd.add_argument("path", type=Path)
    staff_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    staff_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the board strategy")

    sub.add_parser("presets", help="List shift-site catalogs")

    serve = sub.add_parser("serve", help="Open the local roster board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            site = PRESETS[key]
            print(
                f"{key:<10} {site.name:<28} "
                f"{shift_label(site.shift_start, site.shift_end):<13}  "
                f"${site.labor_dollars:<7g}  "
                f"{site.head_cap:>2} heads  "
                f"break {site.break_after}h"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = staff(Board.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
