"""Command line for WaveCut."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cut import cut
from .model import WavePlan
from .report import text_report
from .shifts import PRESETS, format_hhmm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wavecut", description="Cut outbound orders into timed pick waves."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cut_cmd = sub.add_parser("cut", help="Cut a wave-plan JSON file")
    cut_cmd.add_argument("path", type=Path)
    cut_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    cut_cmd.add_argument(
        "--strategy",
        choices=("auto", "cutoff", "zone", "cube"),
        help="Override the plan strategy",
    )

    sub.add_parser("presets", help="List shift presets")

    serve = sub.add_parser("serve", help="Open the local wave board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8768)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            shift = PRESETS[key]
            print(
                f"{key:<14} {shift.name:<28} "
                f"{format_hhmm(shift.open_min)}–{format_hhmm(shift.close_min)}  "
                f"wave {shift.wave_min:>3} min  "
                f"{len(shift.slots())} slots  "
                f"{'pure' if shift.zone_pure else 'mix'}"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = cut(WavePlan.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_cut else 2


if __name__ == "__main__":
    raise SystemExit(main())
