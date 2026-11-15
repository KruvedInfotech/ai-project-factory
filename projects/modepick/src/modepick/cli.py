"""Command line for ModePick."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cards import LTL_BANDS, PARCEL_ZONES, TRUCKS
from .model import Job
from .quote import quote
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="modepick",
        description="Compare parcel, LTL, and FTL for a shipment.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    quote_cmd = sub.add_parser("quote", help="Quote a shipment JSON file")
    quote_cmd.add_argument("path", type=Path)
    quote_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("cards", help="List screening rate cards and trucks")

    serve = sub.add_parser("serve", help="Open the local rate desk")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8792)

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
        result = quote(Job.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"modepick: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.winner else 2


def _print_cards() -> None:
    print("Parcel zones (per billable kg, min per piece)")
    for zone in PARCEL_ZONES:
        cap = "∞" if zone.max_km == float("inf") else f"{zone.max_km:g} km"
        print(f"  {zone.id:<4} ≤ {cap:<8}  ${zone.per_kg_usd:.2f}/kg  min ${zone.min_piece_usd:.2f}")
    print("LTL class-100 CWT (then × class/100, −45%, +18% fuel)")
    for band in LTL_BANDS:
        cap = "∞" if band.max_km == float("inf") else f"{band.max_km:g} km"
        print(f"  {band.id:<10} ≤ {cap:<8}  ${band.class100_per_cwt_usd:.0f}/cwt")
    print("FTL trucks (cube screening at 85% of inner volume)")
    for key in TRUCKS:
        truck = TRUCKS[key]
        print(
            f"  {truck.id:<12} {truck.name:<24} {truck.volume_m3:6.2f} m³  "
            f"{truck.max_weight_kg:g} kg  ${truck.per_km_usd:.2f}/km  min ${truck.minimum_usd:.0f}"
        )
