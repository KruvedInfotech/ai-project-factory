"""Command line for SlotRank."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import SlotPlan
from .report import text_report
from .slot import slot
from .warehouses import PRESETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slotrank", description="Rank pick-face homes by velocity and golden zone."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    slot_cmd = sub.add_parser("slot", help="Slot a SKU-plan JSON file")
    slot_cmd.add_argument("path", type=Path)
    slot_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    slot_cmd.add_argument(
        "--strategy",
        choices=("auto", "velocity", "affinity", "heavy"),
        help="Override the plan strategy",
    )

    sub.add_parser("presets", help="List warehouse presets")

    serve = sub.add_parser("serve", help="Open the local slot board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8770)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            house = PRESETS[key]
            print(
                f"{key:<14} {house.name:<28} "
                f"{house.aisle_count}×{house.bays_per_aisle}  "
                f"gold A1–A{house.golden_aisles}/B{house.golden_bays}  "
                f"{house.max_moves} moves  "
                f"{house.max_labor_min} min"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = slot(SlotPlan.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_slotted else 2


if __name__ == "__main__":
    raise SystemExit(main())
