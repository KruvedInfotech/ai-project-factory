"""Command line for StageLane."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Wave
from .report import text_report
from .seat import seat
from .yards import STRATEGIES, YARDS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stagelane",
        description="Seat outbound pallets into staging lanes (carrier, door, cutoff).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    seat_cmd = sub.add_parser("seat", help="Seat a wave JSON file onto the yard")
    seat_cmd.add_argument("path", type=Path)
    seat_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    seat_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the wave strategy")

    sub.add_parser("presets", help="List staging-yard catalogs")

    serve = sub.add_parser("serve", help="Open the local dock / lane map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8784)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(YARDS):
            yard = YARDS[key]
            first, last = yard.lanes[0], yard.lanes[-1]
            print(
                f"{key:<10} {yard.name:<22} "
                f"{first.id}-{last.id}  "
                f"{first.length_mm}mm  "
                f"{first.temp:<6}  "
                f"{yard.max_pallets} pallets  labor {yard.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = seat(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
