"""Command line for PalMix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .decks import DECKS, STRATEGIES
from .model import Build
from .pack import pack
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="palmix",
        description="Mix store cases onto pallets (one store per deck, crush on top).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    mix_cmd = sub.add_parser("mix", help="Mix a build JSON file onto pallets")
    mix_cmd.add_argument("path", type=Path)
    mix_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    mix_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the build strategy")

    sub.add_parser("presets", help="List pallet deck catalogs")

    serve = sub.add_parser("serve", help="Open the local pallet / deck map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8782)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(DECKS):
            deck = DECKS[key]
            print(
                f"{key:<12} {deck.name:<22} "
                f"{deck.length_mm}x{deck.width_mm}x{deck.height_mm} mm  "
                f"{deck.max_weight_kg:g} kg  {deck.temp:<6}  "
                f"{deck.max_pallets} pals  labor {deck.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = pack(Build.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
