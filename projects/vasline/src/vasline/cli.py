"""Command line for VasLine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Workbook
from .ops import OPS, ops_payload
from .report import text_report
from .schedule import plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vasline",
        description="Schedule value-added service jobs across warehouse benches.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Schedule jobs from a workbook JSON file")
    plan_cmd.add_argument("path", type=Path)
    plan_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("ops", help="List VAS operations and default times")

    serve = sub.add_parser("serve", help="Open the local VAS workbench")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8797)

    args = parser.parse_args(argv)

    if args.command == "ops":
        _print_ops()
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        result = plan(Workbook.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"vasline: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


def _print_ops() -> None:
    body = ops_payload()
    print("VAS operations")
    for item in body["ops"]:
        print(
            f"  {item['id']:<8} {item['name']:<14} "
            f"{item['seconds_per_unit']:>4g} s/unit  setup {item['setup_seconds']:>3} s  "
            f"{item['blurb']}"
        )
    print(body["rule"])
    print("Known ids: " + ", ".join(OPS))
