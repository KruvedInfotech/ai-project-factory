"""Command line for BoxFit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import PRESETS
from .model import PackJob
from .pack import pack
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="boxfit", description="Fit order items into shipper cartons.")
    sub = parser.add_subparsers(dest="command", required=True)

    pack_cmd = sub.add_parser("pack", help="Cartonize an orders JSON file")
    pack_cmd.add_argument("path", type=Path)
    pack_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("presets", help="List shipper catalog presets")

    serve = sub.add_parser("serve", help="Open the local cartonization planner")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8780)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            catalog = PRESETS[key]
            sizes = ", ".join(carton.id for carton in catalog.cartons)
            print(f"{key:<16} {catalog.name:<24} {len(catalog.cartons)} sizes  {sizes}")
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        result = pack(PackJob.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"boxfit: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
