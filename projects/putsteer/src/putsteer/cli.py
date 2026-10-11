"""Command line for PutSteer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Wave
from .policies import PRESETS, STRATEGIES
from .report import text_report
from .steer import steer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="putsteer", description="Assign inbound pallets to warehouse locations."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    put_cmd = sub.add_parser("put", help="Put away a wave JSON file")
    put_cmd.add_argument("path", type=Path)
    put_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")
    put_cmd.add_argument("--strategy", choices=STRATEGIES, help="Override the wave strategy")

    sub.add_parser("presets", help="List putaway policy presets")

    serve = sub.add_parser("serve", help="Open the local putaway board")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8774)

    args = parser.parse_args(argv)

    if args.command == "presets":
        for key in sorted(PRESETS):
            policy = PRESETS[key]
            mix = "mix" if policy.allow_mix_sku else "no-mix"
            loc = policy.location_type or "any"
            print(
                f"{key:<12} {policy.name:<18} "
                f"{loc:<8} {mix:<7}  "
                f"{policy.minutes_per_put} min/put  "
                f"labor {policy.max_labor_min}m"
            )
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if args.strategy:
        payload["strategy"] = args.strategy
    result = steer(Wave.from_dict(payload))
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_clear else 2


if __name__ == "__main__":
    raise SystemExit(main())
