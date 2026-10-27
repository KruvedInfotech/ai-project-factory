"""Command line for SlotFold."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .fold import fold
from .model import FoldPlan
from .report import text_report
from .warehouse import PRESETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="slotfold", description="Fold partial locations of the same SKU.")
    sub = parser.add_subparsers(dest="command", required=True)

    fold_cmd = sub.add_parser("fold", help="Fold a locations JSON file")
    fold_cmd.add_argument("path", type=Path)
    fold_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("presets", help="List warehouse rack-room presets")

    serve = sub.add_parser("serve", help="Open the local slot-fold planner")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8779)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            room = PRESETS[key]
            print(
                f"{key:<16} {room.name:<24} {len(room.aisles)}×{room.bays}×{room.levels}  {room.slot_count} slots"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    result = fold(FoldPlan.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_folded else 2


if __name__ == "__main__":
    raise SystemExit(main())
