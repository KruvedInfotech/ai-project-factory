"""Command line for CartClip."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .floor import CARTS, STRATEGIES, WAREHOUSES
from .model import Wave
from .plan import plan_wave
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cartclip",
        description="Clip warehouse orders onto pick carts (one tote per order).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    clip_cmd = sub.add_parser("clip", help="Clip a wave JSON file onto pick carts")
    clip_cmd.add_argument("path", type=Path)
    clip_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    clip_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the wave strategy")

    sub.add_parser("presets", help="List warehouse floors and cart catalogs")

    serve = sub.add_parser("serve", help="Open the local cart / aisle map")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8781)

    args = parser.parse_args(argv)

    if args.command == "presets":
        print("Warehouses")
        for key in sorted(WAREHOUSES):
            floor = WAREHOUSES[key]
            print(f"  {key:<12} {floor.name:<22} {'-'.join(floor.aisles)} × {floor.bays} bays")
        print("Carts")
        for key in sorted(CARTS):
            cart = CARTS[key]
            print(
                f"  {key:<12} {cart.name:<24} {cart.tote_slots} totes  "
                f"{cart.max_weight_kg:g} kg  {cart.max_volume_l:g} L  "
                f"{cart.temp:<6} span {cart.max_aisle_span}  labor {cart.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = plan_wave(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


if __name__ == "__main__":
    raise SystemExit(main())
