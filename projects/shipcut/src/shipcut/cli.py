"""Command line for ShipCut."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cards import CARRIERS, ZONES
from .model import Job
from .plan import plan
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shipcut",
        description="Which carrier cutoff still makes the delivery promise.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check_cmd = sub.add_parser("check", help="Check an order JSON file")
    check_cmd.add_argument("path", type=Path)
    check_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("cards", help="List screening carriers and zones")

    serve = sub.add_parser("serve", help="Open the local cutoff clock")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8793)

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
        result = plan(Job.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"shipcut: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.winner else 2


def _print_cards() -> None:
    print("Zones (from road km when zone is omitted)")
    for zone in ZONES:
        cap = "∞" if zone.max_km == float("inf") else f"{zone.max_km:g} km"
        print(f"  {zone.id:<4} {zone.name:<10} ≤ {cap}")
    print("Carriers (local warehouse cutoff, transit in calendar days, then weekend roll)")
    for key in CARRIERS:
        card = CARRIERS[key]
        print(
            f"  {card.id:<12} {card.name:<18} cutoff {card.cutoff.strftime('%H:%M')}  "
            f"{card.pickup_label():<8}  {card.transit_label()}  "
            f"{card.max_weight_kg:g} kg / {card.max_side_cm:g} cm"
        )
