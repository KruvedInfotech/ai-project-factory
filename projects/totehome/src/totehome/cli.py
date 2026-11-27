"""Command line for ToteHome."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Floor
from .report import text_report
from .route import plan
from .totes import TOTES, totes_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="totehome",
        description="Plan empty-tote milk runs from pick, pack, and returns stations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Plan milk runs from a floor JSON file")
    plan_cmd.add_argument("path", type=Path)
    plan_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("totes", help="List tote types, nest sizes, and home kinds")

    serve = sub.add_parser("serve", help="Open the local tote-return desk")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8798)

    args = parser.parse_args(argv)

    if args.command == "totes":
        _print_totes()
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        result = plan(Floor.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"totehome: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


def _print_totes() -> None:
    body = totes_payload()
    print("Tote types")
    for item in body["totes"]:
        print(
            f"  {item['id']:<8} {item['name']:<22} "
            f"nest {item['nest_per_stack']:>2}/stack  home {item['home_kind']:<10}  "
            f"{item['blurb']}"
        )
    print("Home kinds")
    for item in body["home_kinds"]:
        print(f"  {item['id']:<10} {item['blurb']}")
    print(body["rule"])
    print("Known ids: " + ", ".join(TOTES))
