"""Command line for AqlDraw."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cards import AQL_PRESETS, LETTERS, LEVELS, SAMPLE_N, cards_payload
from .draw import plan
from .model import Receipt
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aqldraw",
        description="How many inbound cartons to open, and at what defect count the lot fails.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    draw_cmd = sub.add_parser("draw", help="Draw a sample from a receipt JSON file")
    draw_cmd.add_argument("path", type=Path)
    draw_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("cards", help="List inspection levels, letters, and AQL presets")

    serve = sub.add_parser("serve", help="Open the local QC desk")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8794)

    args = parser.parse_args(argv)

    if args.command == "cards":
        _print_cards()
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        result = plan(Receipt.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"aqldraw: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 2 if result.reject_count else 0


def _print_cards() -> None:
    body = cards_payload()
    print("Inspection levels (letter slides one step for I / III)")
    for key, name in LEVELS.items():
        print(f"  {key:<4} {name}")
    print("Severity: reduced (−1 letter) · normal · tightened (+1 letter)")
    print("AQL presets (%): " + ", ".join(f"{item:g}" for item in AQL_PRESETS))
    print("Default classes: critical 0.65 · major 2.5 · minor 6.5")
    print("Letters (sample size, then cap at lot size)")
    row = "  ".join(f"{letter}:{SAMPLE_N[letter]}" for letter in LETTERS)
    print(f"  {row}")
    print(body["rule"])
