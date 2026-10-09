"""Command line for LotDraw."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .draw import draw
from .model import Wave
from .policies import PRESETS, STRATEGIES
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lotdraw", description="Allocate warehouse lots to outbound orders (FEFO/FIFO)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    draw_cmd = sub.add_parser("draw", help="Allocate a wave JSON file")
    draw_cmd.add_argument("path", type=Path)
    draw_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    draw_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the wave strategy")

    sub.add_parser("presets", help="List allocation policy presets")

    serve = sub.add_parser("serve", help="Open the local lot board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8773)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            policy = PRESETS[key]
            split = "split" if policy.allow_split else "no-split"
            print(
                f"{key:<14} {policy.name:<18} "
                f"life {policy.min_remaining_days:>3}d  "
                f"{split:<8}  "
                f"max {policy.max_lots_per_line} lot(s)"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = draw(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_clear else 2


if __name__ == "__main__":
    raise SystemExit(main())
