"""Command line for LoadFit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .containers import PRESETS
from .model import Shipment
from .pack import pack
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loadfit", description="Pack cartons into a cargo box.")
    sub = parser.add_subparsers(dest="command", required=True)

    pack_cmd = sub.add_parser("pack", help="Pack a shipment JSON file")
    pack_cmd.add_argument("path", type=Path)
    pack_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("presets", help="List vehicle / container presets")

    serve = sub.add_parser("serve", help="Open the local load planner")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            item = PRESETS[key]
            print(
                f"{key:<16} {item.name:<24} {item.length_mm}x{item.width_mm}x{item.height_mm} mm  {item.max_weight_kg:g} kg"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    result = pack(Shipment.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
